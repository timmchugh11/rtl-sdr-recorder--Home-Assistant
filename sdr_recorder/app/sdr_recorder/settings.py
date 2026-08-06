from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


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
    pre_roll_seconds: float = 0.25
    post_roll_seconds: float = 2.0
    recordings_path: str = "/media/sdr_recorder"
    retention_days: int = 0
    max_storage_mb: int = 0
    auto_start: bool = True
    debug: bool = False
    data_path: str = "/data"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        options_path = Path(path or os.getenv("SDR_OPTIONS_PATH", "/data/options.json"))
        values: dict = {}
        if options_path.exists():
            values = json.loads(options_path.read_text(encoding="utf-8"))
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
