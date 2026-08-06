from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import FrequencyBase


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialise(self) -> None:
        with self._lock, self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS frequencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frequency_hz INTEGER NOT NULL UNIQUE,
                    name TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    squelch_dbfs REAL NOT NULL DEFAULT -45,
                    record_enabled INTEGER NOT NULL DEFAULT 1,
                    retention_days INTEGER NOT NULL DEFAULT 0,
                    last_heard_at TEXT,
                    activity_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recordings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frequency_id INTEGER,
                    frequency_hz INTEGER NOT NULL,
                    friendly_name TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    label TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    peak_dbfs REAL NOT NULL,
                    average_dbfs REAL NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_path TEXT NOT NULL UNIQUE,
                    detected_tone TEXT,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    protected INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(frequency_id) REFERENCES frequencies(id) ON DELETE SET NULL
                );
                CREATE INDEX IF NOT EXISTS idx_recordings_started ON recordings(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_recordings_frequency ON recordings(frequency_hz);
                CREATE INDEX IF NOT EXISTS idx_recordings_category ON recordings(category);
                """
            )
            count = db.execute("SELECT COUNT(*) FROM frequencies").fetchone()[0]
            if count == 0:
                now = datetime.now(timezone.utc).isoformat()
                rows = [
                    (446_006_250 + index * 12_500, f"PMR446 Ch{index + 1}", "PMR446",
                     1 if index == 12 else 0, now, now)
                    for index in range(16)
                ]
                db.executemany(
                    """INSERT INTO frequencies
                    (frequency_hz,name,category,enabled,created_at,updated_at)
                    VALUES (?,?,?,?,?,?)""",
                    rows,
                )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def frequencies(self, enabled_only: bool = False) -> list[dict]:
        query = "SELECT * FROM frequencies"
        if enabled_only:
            query += " WHERE enabled=1"
        query += " ORDER BY category,frequency_hz,name"
        with self.connect() as db:
            return [dict(row) for row in db.execute(query)]

    def frequency(self, frequency_id: int) -> dict | None:
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM frequencies WHERE id=?", (frequency_id,)).fetchone())

    def add_frequency(self, item: FrequencyBase) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as db:
            cursor = db.execute(
                """INSERT INTO frequencies
                (frequency_hz,name,category,enabled,squelch_dbfs,record_enabled,retention_days,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (item.frequency_hz, item.name, item.category, item.enabled, item.squelch_dbfs,
                 item.record_enabled, item.retention_days, now, now),
            )
            frequency_id = cursor.lastrowid
        return self.frequency(frequency_id) or {}

    def update_frequency(self, frequency_id: int, item: FrequencyBase) -> dict | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self.connect() as db:
            db.execute(
                """UPDATE frequencies SET frequency_hz=?,name=?,category=?,enabled=?,squelch_dbfs=?,
                record_enabled=?,retention_days=?,updated_at=? WHERE id=?""",
                (item.frequency_hz, item.name, item.category, item.enabled, item.squelch_dbfs,
                 item.record_enabled, item.retention_days, now, frequency_id),
            )
        return self.frequency(frequency_id)

    def delete_frequency(self, frequency_id: int) -> bool:
        with self._lock, self.connect() as db:
            return db.execute("DELETE FROM frequencies WHERE id=?", (frequency_id,)).rowcount > 0

    def heard(self, frequency_id: int, when: str) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE frequencies SET last_heard_at=?,activity_count=activity_count+1 WHERE id=?",
                (when, frequency_id),
            )

    def add_recording(self, values: dict) -> int:
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        with self._lock, self.connect() as db:
            cursor = db.execute(
                f"INSERT INTO recordings ({columns}) VALUES ({placeholders})", tuple(values.values())
            )
            return int(cursor.lastrowid)

    def recordings(self, *, page: int = 1, page_size: int = 50, search: str = "",
                   category: str = "", frequency_hz: int | None = None,
                   date_from: str = "", date_to: str = "") -> dict:
        clauses: list[str] = []
        values: list[Any] = []
        if search:
            clauses.append("(friendly_name LIKE ? OR label LIKE ? OR CAST(frequency_hz AS TEXT) LIKE ?)")
            term = f"%{search}%"
            values.extend((term, term, term))
        if category:
            clauses.append("category=?")
            values.append(category)
        if frequency_hz:
            clauses.append("frequency_hz=?")
            values.append(frequency_hz)
        if date_from:
            clauses.append("started_at>=?")
            values.append(date_from)
        if date_to:
            clauses.append("started_at<?")
            values.append(f"{date_to}T23:59:59.999999+00:00")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        page_size = min(max(page_size, 1), 200)
        offset = (max(page, 1) - 1) * page_size
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM recordings{where}", values).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM recordings{where} ORDER BY started_at DESC LIMIT ? OFFSET ?",
                (*values, page_size, offset),
            )
            return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}

    def recording(self, recording_id: int) -> dict | None:
        with self.connect() as db:
            return self._row(db.execute("SELECT * FROM recordings WHERE id=?", (recording_id,)).fetchone())

    def patch_recording(self, recording_id: int, changes: dict) -> dict | None:
        allowed = {key: value for key, value in changes.items() if value is not None and key in {"label", "favorite", "protected"}}
        if allowed:
            assignments = ",".join(f"{key}=?" for key in allowed)
            with self.connect() as db:
                db.execute(f"UPDATE recordings SET {assignments} WHERE id=?", (*allowed.values(), recording_id))
        return self.recording(recording_id)

    def delete_recording_row(self, recording_id: int) -> dict | None:
        row = self.recording(recording_id)
        if row:
            with self.connect() as db:
                db.execute("DELETE FROM recordings WHERE id=?", (recording_id,))
        return row

    def stats(self) -> dict:
        today = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM recordings WHERE started_at>=?", (today,)).fetchone()[0]
            size = db.execute("SELECT COALESCE(SUM(file_size),0) FROM recordings").fetchone()[0]
        return {"recordings_today": count, "storage_used_bytes": size}
