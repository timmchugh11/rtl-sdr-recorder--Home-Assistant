from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def safe_name(value: str, fallback: str = "recording") -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return value[:80] or fallback


def recording_path(root: Path, started: datetime, name: str, frequency_hz: int) -> Path:
    directory = root / started.strftime("%Y") / started.strftime("%m") / started.strftime("%d")
    directory.mkdir(parents=True, exist_ok=True)
    mhz = f"{frequency_hz / 1e6:.5f}MHz"
    prefix = started.strftime("%Y-%m-%d_%H-%M-%S")
    label = f"_{safe_name(name)}" if name else ""
    candidate = directory / f"{prefix}{label}_{mhz}.wav"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{prefix}{label}_{mhz}_{counter}.wav"
        counter += 1
    return candidate


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
