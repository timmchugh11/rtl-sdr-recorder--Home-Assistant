from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Settings:
    source: str = "mock"
    uri: str = "ip:192.168.2.1"
    center_frequency_hz: int = 447_700_000
    sample_rate_hz: int = 4_000_000
    rf_bandwidth_hz: int = 4_000_000
    gain_mode: str = "manual"
    gain_db: float = 0.0
    audio_sample_rate_hz: int = 10_000
    audio_gain: float = 0.08
    squelch_grace_seconds: float = 0.35
    pre_roll_seconds: float = 0.25
    post_roll_seconds: float = 2.0
    recordings_path: str = "/media/sdr_recorder"
    retention_days: int = 0
    max_storage_mb: int = 0
    auto_start: bool = True
    debug: bool = False
    data_path: str = "/data"

    DEVICE_FIELDS = ("source", "uri")
    EDITABLE_FIELDS = (
        "center_frequency_hz", "sample_rate_hz", "rf_bandwidth_hz", "gain_mode",
        "gain_db", "audio_sample_rate_hz", "audio_gain", "pre_roll_seconds",
        "post_roll_seconds", "retention_days", "max_storage_mb", "auto_start", "debug",
    )

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        options_path = Path(path or os.getenv("SDR_OPTIONS_PATH", "/data/options.json"))
        values: dict[str, Any] = {}
        if options_path.exists():
            options = json.loads(options_path.read_text(encoding="utf-8"))
            # Supervisor owns only device selection. Receiver tuning is owned
            # by the Ingress UI and persisted independently under /data.
            values.update({key: options[key] for key in cls.DEVICE_FIELDS if key in options})
            if "data_path" in options:
                values["data_path"] = options["data_path"]
        data_path = Path(values.get("data_path", "/data"))
        saved_path = data_path / "receiver_settings.json"
        if saved_path.exists():
            saved = json.loads(saved_path.read_text(encoding="utf-8"))
            values.update({key: saved[key] for key in cls.EDITABLE_FIELDS if key in saved})
        # Local development defaults to writable project paths and mock input.
        if not Path("/data").exists():
            values.setdefault("data_path", str(Path("./dev-data").resolve()))
            values.setdefault("recordings_path", str(Path("./dev-media").resolve()))
            values.setdefault("source", "mock")
        known = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in values.items() if key in known})

    def public_dict(self) -> dict:
        result = asdict(self)
        result.pop("data_path", None)
        return result

    def editable_dict(self) -> dict:
        values = asdict(self)
        return {key: values[key] for key in self.EDITABLE_FIELDS}

    def save_editable(self) -> None:
        target = Path(self.data_path) / "receiver_settings.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.editable_dict(), indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
