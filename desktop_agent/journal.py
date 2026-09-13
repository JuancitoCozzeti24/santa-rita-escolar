from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import hashlib
import json
import sqlite3


FINAL_STATES = {"completed", "blocked", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def operation_key(kind: str, target: dict[str, object], payload: dict[str, object]) -> str:
    """Identidad estable: el mismo efecto nunca obtiene dos claves distintas."""
    canonical = json.dumps(
        {"kind": kind, "target": target, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Operation:
    key: str
    kind: str
    status: str
    target: dict[str, object]
    payload: dict[str, object]
    result: dict[str, object] | None


class OperationJournal:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS operations (
                    operation_key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def reserve(
        self, kind: str, target: dict[str, object], payload: dict[str, object]
    ) -> tuple[Operation, bool]:
        key = operation_key(kind, target, payload)
        target_json = json.dumps(target, ensure_ascii=False, sort_keys=True)
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        now = _now()
        with self._connection() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO operations VALUES (?, ?, 'reserved', ?, ?, NULL, ?, ?)",
                (key, kind, target_json, payload_json, now, now),
            ).rowcount == 1
            row = db.execute(
                "SELECT * FROM operations WHERE operation_key = ?", (key,)
            ).fetchone()
        return self._row(row), inserted

    def transition(self, key: str, status: str, result: dict[str, object] | None = None) -> Operation:
        allowed = {"reserved", "executing", "verifying", "completed", "failed", "blocked", "cancelled"}
        if status not in allowed:
            raise ValueError(f"Estado de operación inválido: {status}")
        with self._connection() as db:
            current = db.execute(
                "SELECT status FROM operations WHERE operation_key = ?", (key,)
            ).fetchone()
            if current is None:
                raise KeyError(key)
            if current["status"] in FINAL_STATES and current["status"] != status:
                raise RuntimeError(f"La operación {key} ya terminó como {current['status']}")
            db.execute(
                "UPDATE operations SET status=?, result_json=?, updated_at=? WHERE operation_key=?",
                (status, json.dumps(result, ensure_ascii=False) if result is not None else None, _now(), key),
            )
            row = db.execute(
                "SELECT * FROM operations WHERE operation_key = ?", (key,)
            ).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> Operation:
        return Operation(
            key=row["operation_key"],
            kind=row["kind"],
            status=row["status"],
            target=json.loads(row["target_json"]),
            payload=json.loads(row["payload_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
        )
