from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from .database import Database
from .dsp import NFMChannel
from .recording import AudioChunk, FinishRecording, RecordingWorker, StartRecording
from .sdr import MockSource, PlutoSource
from .settings import Settings

LOG = logging.getLogger(__name__)


class ReceiverEngine:
    def __init__(self, settings: Settings, database: Database,
                 event_callback: Callable[[str, dict], None] | None = None):
        self.settings = settings
        self.database = database
        self.event_callback = event_callback
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._reload = threading.Event()
        self._lock = threading.RLock()
        self._source = None
        self._sample_index = 0
        self._channels: dict[int, NFMChannel] = {}
        self._frequency_rows: dict[int, dict] = {}
        self._sessions: dict[int, dict] = {}
        self._last_spectrum = 0.0
        self.status = {
            "running": False, "connected": False, "source": settings.source,
            "description": "", "error": "", "center_frequency_hz": settings.center_frequency_hz,
            "sample_rate_hz": settings.sample_rate_hz, "gain_db": settings.gain_db,
            "active_frequency_hz": None, "signal_dbfs": -120.0, "channels": [],
            "spectrum": [], "spectrum_start_hz": 0, "spectrum_bin_hz": 0,
            "waveform": [], "recording": False,
        }
        self.writer = RecordingWorker(
            database, Path(settings.recordings_path), settings.audio_sample_rate_hz,
            self._recording_complete,
        )
        self.writer.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sdr-receiver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._finish_all()
        self._set_status(running=False, connected=False, recording=False)

    def shutdown(self) -> None:
        self.stop()
        self.writer.stop()

    def reload_frequencies(self) -> None:
        self._reload.set()

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.status)

    def _set_status(self, **changes) -> None:
        with self._lock:
            self.status.update(changes)

    def _make_source(self):
        if self.settings.source == "mock":
            frequencies = [row["frequency_hz"] for row in self.database.frequencies(True)]
            return MockSource(self.settings.center_frequency_hz, self.settings.sample_rate_hz,
                              self.settings.gain_db, frequencies)
        return PlutoSource(
            self.settings.uri, self.settings.center_frequency_hz, self.settings.sample_rate_hz,
            self.settings.rf_bandwidth_hz, self.settings.gain_mode, self.settings.gain_db,
        )

    def _load_channels(self) -> None:
        rows = self.database.frequencies(enabled_only=True)
        half_span = self.settings.sample_rate_hz / 2 - 10_000
        valid = [row for row in rows if abs(row["frequency_hz"] - self.settings.center_frequency_hz) <= half_span]
        ignored = len(rows) - len(valid)
        if ignored:
            LOG.warning("%d enabled frequencies are outside the captured spectrum", ignored)
        self._finish_all()
        self._frequency_rows = {row["id"]: row for row in valid}
        self._channels = {
            row["id"]: NFMChannel(
                row["frequency_hz"], self.settings.center_frequency_hz,
                self.settings.sample_rate_hz, self.settings.audio_sample_rate_hz,
                row["squelch_dbfs"], self.settings.audio_gain,
            ) for row in valid
        }
        chunks_per_pre_roll = round(
            self.settings.pre_roll_seconds / (65_536 / self.settings.sample_rate_hz)
        )
        self._sessions = {
            row["id"]: {"open": False, "post": 0.0, "pre": deque(maxlen=max(0, chunks_per_pre_roll)),
                        "levels": [], "started": None, "gap": 0.0, "pending": []}
            for row in valid
        }
        LOG.info("Monitoring %d frequencies from one %.3f MS/s IQ stream", len(valid),
                 self.settings.sample_rate_hz / 1e6)

    def _run(self) -> None:
        self._set_status(
            running=True, error="", center_frequency_hz=self.settings.center_frequency_hz,
            sample_rate_hz=self.settings.sample_rate_hz, gain_db=self.settings.gain_db,
        )
        retry = 1.0
        while not self._stop.is_set():
            try:
                self._source = self._make_source()
                self._source.open()
                self._sample_index = 0
                self._load_channels()
                self._set_status(connected=True, description=self._source.info.description, error="")
                self._event("sdr_connected", {})
                retry = 1.0
                self._receive_loop()
            except Exception as exc:
                LOG.exception("Receiver error")
                self._set_status(connected=False, error=str(exc), recording=False)
                self._event("sdr_disconnected", {"error": str(exc)})
            finally:
                self._finish_all()
                if self._source:
                    try: self._source.close()
                    except Exception: LOG.exception("Source close failed")
            if not self._stop.wait(retry):
                retry = min(retry * 2, 30)
        self._set_status(running=False, connected=False)

    def _receive_loop(self) -> None:
        while not self._stop.is_set():
            if self._reload.is_set():
                self._reload.clear(); self._load_channels()
            raw = self._source.read()
            self._update_spectrum(raw)
            channels_status = []
            strongest = None
            for key, processor in self._channels.items():
                result = processor.process(raw, self._sample_index)
                row = self._frequency_rows[key]
                session = self._sessions[key]
                self._handle_channel(key, row, session, result)
                item = {
                    "id": key, "frequency_hz": row["frequency_hz"], "name": row["name"],
                    "category": row["category"], "signal_dbfs": round(result.signal_dbfs, 2),
                    "squelch_open": session["open"], "recording": session["open"] and bool(row["record_enabled"]),
                    "last_heard_at": row.get("last_heard_at"),
                }
                channels_status.append(item)
                if result.carrier and (strongest is None or result.signal_dbfs > strongest[0]):
                    strongest = (result.signal_dbfs, row, result.waveform)
            self._sample_index += len(raw)
            self._set_status(
                channels=channels_status,
                active_frequency_hz=strongest[1]["frequency_hz"] if strongest else None,
                signal_dbfs=round(strongest[0], 2) if strongest else -120.0,
                waveform=strongest[2] if strongest else [],
                recording=any(session["open"] and self._frequency_rows[key]["record_enabled"]
                              for key, session in self._sessions.items()),
            )

    def _handle_channel(self, key: int, row: dict, session: dict, result) -> None:
        seconds = len(result.audio) / self.settings.audio_sample_rate_hz
        if result.carrier:
            session["post"] = self.settings.post_roll_seconds
            if not session["open"]:
                session["open"] = True
                session["started"] = datetime.now(timezone.utc)
                session["levels"] = []
                self.database.heard(key, session["started"].isoformat())
                self._event("transmission_started", {"frequency_hz": row["frequency_hz"], "name": row["name"]})
                if row["record_enabled"]:
                    self.writer.submit(StartRecording(key, row, session["started"], list(session["pre"])))
                session["pre"].clear()
            elif row["record_enabled"] and session["pending"]:
                # A brief detector dropout was not a real end of carrier. Keep
                # the buffered speech instead of chopping a hole in the WAV.
                for pending in session["pending"]:
                    self.writer.submit(AudioChunk(key, pending))
            session["pending"] = []
            session["gap"] = 0.0
            session["levels"].append(result.signal_dbfs)

        if session["open"]:
            if row["record_enabled"] and result.audio.size:
                if result.carrier:
                    self.writer.submit(AudioChunk(key, result.audio.copy()))
                else:
                    session["pending"].append(result.audio.copy())
                    session["gap"] += seconds
                    if session["gap"] >= self.settings.squelch_grace_seconds:
                        # Confirmed carrier loss: preserve timing but gate noise.
                        for pending in session["pending"]:
                            self.writer.submit(AudioChunk(key, np.zeros_like(pending)))
                        session["pending"] = []
            if not result.carrier:
                session["post"] -= seconds
                if session["post"] <= 0:
                    self._close_session(key, row, session)
        elif session["pre"].maxlen and result.audio.size:
            # Closed-squelch pre-roll represents elapsed time, not audible RF
            # noise. The opening chunk still contains the speech onset.
            session["pre"].append(np.zeros_like(result.audio))

    def _close_session(self, key: int, row: dict, session: dict) -> None:
        if not session["open"]:
            return
        finished = datetime.now(timezone.utc)
        if row["record_enabled"]:
            for pending in session["pending"]:
                self.writer.submit(AudioChunk(key, np.zeros_like(pending)))
            self.writer.submit(FinishRecording(key, finished, session["levels"][:]))
        self._event("transmission_ended", {"frequency_hz": row["frequency_hz"], "name": row["name"]})
        session.update(open=False, post=0.0, levels=[], started=None, gap=0.0, pending=[])

    def _finish_all(self) -> None:
        for key, session in list(self._sessions.items()):
            row = self._frequency_rows.get(key)
            if row: self._close_session(key, row, session)

    def _update_spectrum(self, raw: np.ndarray) -> None:
        now = time.monotonic()
        if now - self._last_spectrum < 0.5 or len(raw) < 2048:
            return
        self._last_spectrum = now
        block = raw[-2048:]
        spectrum = np.fft.fftshift(np.fft.fft(block * np.hanning(len(block))))
        power = 20 * np.log10(np.maximum(np.abs(spectrum) / (len(block) * 2048), 1e-9))
        bins = power.reshape(256, -1).max(axis=1)
        self._set_status(
            spectrum=np.round(bins, 1).tolist(),
            spectrum_start_hz=self.settings.center_frequency_hz - self.settings.sample_rate_hz // 2,
            spectrum_bin_hz=self.settings.sample_rate_hz / 256,
        )

    def _event(self, name: str, data: dict) -> None:
        if self.event_callback:
            try: self.event_callback(name, data)
            except Exception: LOG.exception("Event callback failed")

    def _recording_complete(self, recording_id: int, values: dict) -> None:
        self._event("recording_completed", {"recording_id": recording_id, **values})
