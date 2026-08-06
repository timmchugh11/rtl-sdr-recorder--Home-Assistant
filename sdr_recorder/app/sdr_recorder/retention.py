from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .database import Database
from .settings import Settings
from .util import within

LOG = logging.getLogger(__name__)


def apply_retention(database: Database, settings: Settings) -> dict:
    """Delete only unprotected recordings when an explicit limit is enabled."""
    if settings.retention_days <= 0 and settings.max_storage_mb <= 0:
        return {"enabled": False, "deleted": 0, "freed_bytes": 0}
    root = Path(settings.recordings_path)
    library = database.recordings(page=1, page_size=200)["items"]
    # Walk all pages without loading audio data.
    total = database.recordings(page=1, page_size=1)["total"]
    if total > 200:
        library = database.recordings(page=1, page_size=min(total, 100000))["items"]
    candidates: list[dict] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days) if settings.retention_days else None
    for row in reversed(library):
        if row["protected"]:
            continue
        own_days = 0
        frequency = database.frequency(row["frequency_id"]) if row["frequency_id"] else None
        if frequency: own_days = frequency["retention_days"]
        own_cutoff = datetime.now(timezone.utc) - timedelta(days=own_days) if own_days else cutoff
        if own_cutoff and datetime.fromisoformat(row["started_at"]) < own_cutoff:
            candidates.append(row)
    current_size = sum(row["file_size"] for row in library)
    maximum = settings.max_storage_mb * 1048576
    if maximum and current_size > maximum:
        for row in reversed(library):
            if not row["protected"] and row not in candidates:
                candidates.append(row)
                current_size -= row["file_size"]
                if current_size <= maximum: break
    deleted = freed = 0
    for row in candidates:
        path = Path(row["file_path"])
        if not within(path, root):
            LOG.error("Refusing retention path outside recording root: %s", path); continue
        try:
            if path.exists(): path.unlink()
            database.delete_recording_row(row["id"])
            deleted += 1; freed += row["file_size"]
        except OSError:
            LOG.exception("Retention failed for %s", path)
    return {"enabled": True, "deleted": deleted, "freed_bytes": freed}
