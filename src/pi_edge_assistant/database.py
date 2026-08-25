from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .models import InteractionRecord


SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    input_mode TEXT NOT NULL,
    transcript TEXT NOT NULL,
    response TEXT NOT NULL,
    model TEXT NOT NULL,
    include_image INTEGER NOT NULL,
    timings_json TEXT NOT NULL,
    peak_memory_mb REAL,
    temperature_c REAL,
    error_code TEXT
);
CREATE INDEX IF NOT EXISTS idx_interactions_created_at
ON interactions(created_at DESC);
"""


class HistoryStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._connection:
            self._connection.executescript(SCHEMA)

    def add(self, record: InteractionRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR REPLACE INTO interactions (
                    id, created_at, input_mode, transcript, response, model,
                    include_image, timings_json, peak_memory_mb,
                    temperature_c, error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.created_at,
                    record.input_mode,
                    record.transcript,
                    record.response,
                    record.model,
                    int(record.include_image),
                    json.dumps(record.timings, ensure_ascii=False),
                    record.peak_memory_mb,
                    record.temperature_c,
                    record.error_code,
                ),
            )

    def list(self, limit: int = 100) -> list[InteractionRecord]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM interactions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            InteractionRecord(
                id=row["id"],
                created_at=row["created_at"],
                input_mode=row["input_mode"],
                transcript=row["transcript"],
                response=row["response"],
                model=row["model"],
                include_image=bool(row["include_image"]),
                timings=json.loads(row["timings_json"]),
                peak_memory_mb=row["peak_memory_mb"],
                temperature_c=row["temperature_c"],
                error_code=row["error_code"],
            )
            for row in rows
        ]

    def clear(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM interactions")

    def close(self) -> None:
        with self._lock:
            self._connection.close()
