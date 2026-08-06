from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from .database import Database
from .engine import ReceiverEngine
from .ha import HomeAssistantPublisher
from .logs import RingLogHandler
from .retention import apply_retention
from .settings import Settings
from .web import create_app


@dataclass
class Context:
    settings: Settings
    database: Database
    ha: HomeAssistantPublisher
    engine: ReceiverEngine
    log_handler: RingLogHandler


async def serve() -> None:
    settings = Settings.load()
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ring = RingLogHandler(); logging.getLogger().addHandler(ring)
    data = Path(settings.data_path); data.mkdir(parents=True, exist_ok=True)
    database = Database(data / "sdr_recorder.sqlite3"); database.initialise()
    ha = HomeAssistantPublisher(); ha.start()
    engine = ReceiverEngine(settings, database, ha.event)
    context = Context(settings, database, ha, engine, ring)
    app = create_app(context)
    if settings.auto_start: engine.start()
    retention_result = apply_retention(database, settings)
    logging.getLogger(__name__).info("Retention startup result: %s", retention_result)

    async def publish_states():
        while True:
            ha.states(engine.snapshot(), database.stats())
            await asyncio.sleep(5)

    publisher = asyncio.create_task(publish_states())
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8099, log_level="debug" if settings.debug else "info"))
    try:
        await server.serve()
    finally:
        publisher.cancel(); engine.shutdown(); ha.stop()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
