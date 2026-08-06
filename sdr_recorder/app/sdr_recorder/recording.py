from __future__ import annotations

import logging
import queue
import threading
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .database import Database
from .util import recording_path

LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class StartRecording:
    key: int
    frequency: dict
    started: datetime
    initial_audio: list[np.ndarray]


@dataclass(slots=True)
class AudioChunk:
    key: int
    audio: np.ndarray


@dataclass(slots=True)
class FinishRecording:
    key: int
    finished: datetime
    levels: list[float]


class RecordingWorker:
    def __init__(self, database: Database, root: Path, audio_rate: int, on_complete=None):
        self.database = database
        self.root = root
        self.audio_rate = audio_rate
        self.on_complete = on_complete
        self.queue: queue.Queue = queue.Queue(maxsize=512)
        self._thread = threading.Thread(target=self._run, name="recording-writer", daemon=True)
        self._stop = object()
        self._open: dict[int, dict] = {}

    def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.recover_partials()
        self._thread.start()

    def submit(self, command) -> None:
        self.queue.put(command, timeout=2)

    def stop(self) -> None:
        self.queue.put(self._stop)
        self._thread.join(timeout=10)

    def recover_partials(self) -> None:
        for path in self.root.rglob("*.partial.wav"):
            recovered = path.with_name(path.name.replace(".partial.wav", ".recovered.wav"))
            try:
                path.replace(recovered)
                LOG.warning("Recovered interrupted recording as %s", recovered)
            except OSError:
                LOG.exception("Unable to recover %s", path)

    @staticmethod
    def _pcm(audio: np.ndarray) -> bytes:
        return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()

    def _run(self) -> None:
        while True:
            command = self.queue.get()
            if command is self._stop:
                break
            try:
                if isinstance(command, StartRecording):
                    self._start(command)
                elif isinstance(command, AudioChunk):
                    state = self._open.get(command.key)
                    if state:
                        state["wav"].writeframesraw(self._pcm(command.audio))
                        state["samples"] += len(command.audio)
                elif isinstance(command, FinishRecording):
                    self._finish(command)
            except Exception:
                LOG.exception("Recording worker command failed")
        for key in list(self._open):
            self._finish(FinishRecording(key, datetime.now(timezone.utc), []))

    def _start(self, command: StartRecording) -> None:
        final_path = recording_path(self.root, command.started, command.frequency["name"],
                                    command.frequency["frequency_hz"])
        partial = final_path.with_suffix(".partial.wav")
        wav = wave.open(str(partial), "wb")
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(self.audio_rate)
        samples = 0
        for chunk in command.initial_audio:
            wav.writeframesraw(self._pcm(chunk)); samples += len(chunk)
        self._open[command.key] = {"wav": wav, "partial": partial, "final": final_path,
                                   "frequency": command.frequency, "started": command.started,
                                   "samples": samples}

    def _finish(self, command: FinishRecording) -> None:
        state = self._open.pop(command.key, None)
        if not state:
            return
        state["wav"].close()
        state["partial"].replace(state["final"])
        frequency = state["frequency"]
        levels = command.levels or [-120.0]
        values = {
            "frequency_id": frequency["id"], "frequency_hz": frequency["frequency_hz"],
            "friendly_name": frequency["name"], "category": frequency["category"], "label": "",
            "started_at": state["started"].isoformat(), "finished_at": command.finished.isoformat(),
            "duration_seconds": state["samples"] / self.audio_rate,
            "peak_dbfs": max(levels), "average_dbfs": sum(levels) / len(levels),
            "file_size": state["final"].stat().st_size, "file_path": str(state["final"]),
            "detected_tone": None, "favorite": 0, "protected": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        recording_id = self.database.add_recording(values)
        if self.on_complete:
            self.on_complete(recording_id, values)
