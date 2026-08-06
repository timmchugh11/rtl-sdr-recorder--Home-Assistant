from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .models import BulkDelete, FrequencyCreate, FrequencyUpdate, ReceiverSettingsUpdate, RecordingPatch
from .retention import apply_retention
from .util import within


def create_app(context) -> FastAPI:
    app = FastAPI(title="SDR Radio Recorder", version=__version__, root_path_in_servers=False)
    app.state.context = context
    api = APIRouter(prefix="/api")

    @app.get("/health")
    def health():
        return {"ok": True, "receiver_thread": context.engine.snapshot()["running"]}

    @api.get("/status")
    def status():
        return {"receiver": context.engine.snapshot(), "storage": context.database.stats(), "version": __version__}

    @api.post("/receiver/start")
    def start_receiver():
        context.engine.start(); return {"ok": True}

    @api.post("/receiver/stop")
    def stop_receiver():
        context.engine.stop(); return {"ok": True}

    @api.post("/receiver/reconnect")
    def reconnect_receiver():
        context.engine.stop(); context.engine.start(); return {"ok": True}

    @api.get("/frequencies")
    def frequencies(): return context.database.frequencies()

    @api.post("/frequencies", status_code=201)
    def add_frequency(item: FrequencyCreate):
        try: row = context.database.add_frequency(item)
        except Exception as exc: raise HTTPException(409, "Frequency already exists") from exc
        context.engine.reload_frequencies(); return row

    @api.put("/frequencies/{frequency_id}")
    def edit_frequency(frequency_id: int, item: FrequencyUpdate):
        try: row = context.database.update_frequency(frequency_id, item)
        except Exception as exc: raise HTTPException(409, "Frequency already exists") from exc
        if not row: raise HTTPException(404, "Frequency not found")
        context.engine.reload_frequencies(); return row

    @api.delete("/frequencies/{frequency_id}")
    def delete_frequency(frequency_id: int):
        if not context.database.delete_frequency(frequency_id): raise HTTPException(404, "Frequency not found")
        context.engine.reload_frequencies(); return {"ok": True}

    @api.get("/recordings")
    def recordings(page: int = 1, page_size: int = Query(50, le=200), search: str = "",
                   category: str = "", frequency_hz: int | None = None,
                   date_from: str = "", date_to: str = ""):
        return context.database.recordings(page=page, page_size=page_size, search=search,
            category=category, frequency_hz=frequency_hz, date_from=date_from, date_to=date_to)

    def recording_file(recording_id: int) -> tuple[dict, Path]:
        row = context.database.recording(recording_id)
        if not row: raise HTTPException(404, "Recording not found")
        path = Path(row["file_path"])
        if not within(path, Path(context.settings.recordings_path)): raise HTTPException(403, "Invalid recording path")
        if not path.is_file(): raise HTTPException(404, "Audio file missing")
        return row, path

    @api.get("/recordings/{recording_id}/audio")
    def audio(recording_id: int):
        _, path = recording_file(recording_id)
        return FileResponse(path, media_type=mimetypes.guess_type(path)[0] or "audio/wav")

    @api.get("/recordings/{recording_id}/download")
    def download(recording_id: int):
        _, path = recording_file(recording_id)
        return FileResponse(path, media_type="audio/wav", filename=path.name)

    @api.patch("/recordings/{recording_id}")
    def patch_recording(recording_id: int, item: RecordingPatch):
        row = context.database.patch_recording(recording_id, item.model_dump())
        if not row: raise HTTPException(404, "Recording not found")
        return row

    def remove_recording(recording_id: int) -> None:
        row, path = recording_file(recording_id)
        if row["protected"]: raise HTTPException(409, "Protected recordings cannot be deleted")
        path.unlink()
        context.database.delete_recording_row(recording_id)

    @api.delete("/recordings/{recording_id}")
    def delete_recording(recording_id: int):
        remove_recording(recording_id); return {"ok": True}

    @api.post("/recordings/bulk-delete")
    def bulk_delete(item: BulkDelete):
        deleted = []; errors = []
        for recording_id in item.ids:
            try: remove_recording(recording_id); deleted.append(recording_id)
            except HTTPException as exc: errors.append({"id": recording_id, "error": exc.detail})
        return {"deleted": deleted, "errors": errors}

    @api.get("/settings")
    def settings():
        return {"settings": context.settings.public_dict(), "version": __version__,
                "logs": list(context.log_handler.lines)[-100:]}

    @api.put("/settings")
    def update_settings(item: ReceiverSettingsUpdate):
        was_running = context.engine.snapshot()["running"]
        if was_running:
            context.engine.stop()
        for key, value in item.model_dump().items():
            setattr(context.settings, key, value)
        try:
            context.settings.save_editable()
        except Exception:
            if was_running:
                context.engine.start()
            raise
        if was_running:
            context.engine.start()
        return {"ok": True, "settings": context.settings.public_dict(),
                "receiver_restarted": was_running}

    @api.post("/retention/run")
    def retention(): return apply_retention(context.database, context.settings)

    @app.websocket("/ws/live")
    async def live(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                await websocket.send_json({"receiver": context.engine.snapshot(), "storage": context.database.stats()})
                await asyncio.sleep(0.25)
        except (WebSocketDisconnect, RuntimeError):
            pass

    app.include_router(api)
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/{path:path}")
    def frontend(request: Request, path: str):
        if path.startswith("api/") or path.startswith("ws/"): raise HTTPException(404)
        return FileResponse(static / "index.html")

    return app
