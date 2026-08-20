"""SQLite-хранилище снэпшотов и находок: сюда пишет и отсюда читает оркестратор.

Снэпшоты копятся по каждой площадке — храним всю историю, а не только
последний, чтобы позже можно было посмотреть, когда что менялось.
Находки (DiffResult) пишутся при каждом прогоне, включая "изменений нет" —
это даёт полную историю проверок, а не только моменты поломок.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from crashdog.diff import DiffResult
from crashdog.snapshot import Snapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id TEXT NOT NULL,
    content TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_platform_fetched
    ON snapshots (platform_id, fetched_at DESC);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id TEXT NOT NULL,
    changed INTEGER NOT NULL,
    summary TEXT NOT NULL,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_platform_detected
    ON findings (platform_id, detected_at DESC);
"""


class StorageError(Exception):
    """Ошибка при работе с хранилищем снэпшотов и находок."""


@contextmanager
def connect(path: str | Path = "crashdog.sqlite3") -> Iterator[sqlite3.Connection]:
    """Открывает соединение с базой, создаёт схему при первом обращении.

    Коммитит транзакцию при успешном выходе из блока `with`, откатывает
    и оборачивает исключение в StorageError при ошибке.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise StorageError(f"Ошибка при работе с базой {path}: {exc}") from exc
    finally:
        conn.close()


def save_snapshot(conn: sqlite3.Connection, snapshot: Snapshot) -> None:
    """Добавляет снэпшот в историю площадки."""
    conn.execute(
        "INSERT INTO snapshots (platform_id, content, fetched_at) VALUES (?, ?, ?)",
        (snapshot.platform_id, snapshot.content, snapshot.fetched_at.isoformat()),
    )


def get_latest_snapshot(conn: sqlite3.Connection, platform_id: str) -> Snapshot | None:
    """Возвращает последний по времени снэпшот площадки или None, если ещё не снимался."""
    row = conn.execute(
        "SELECT content, fetched_at FROM snapshots "
        "WHERE platform_id = ? ORDER BY fetched_at DESC LIMIT 1",
        (platform_id,),
    ).fetchone()
    if row is None:
        return None
    return Snapshot(
        platform_id=platform_id,
        content=row["content"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
    )


def save_finding(conn: sqlite3.Connection, result: DiffResult) -> None:
    """Записывает результат сравнения (включая случай 'изменений нет')."""
    conn.execute(
        "INSERT INTO findings (platform_id, changed, summary, detected_at) VALUES (?, ?, ?, ?)",
        (result.platform_id, int(result.changed), result.summary, result.detected_at.isoformat()),
    )


def get_findings(
    conn: sqlite3.Connection,
    platform_id: str | None = None,
    only_changed: bool = False,
    limit: int = 50,
) -> list[DiffResult]:
    """Возвращает находки, самые новые первыми.

    platform_id фильтрует по площадке (None — все площадки), only_changed
    оставляет только записи с реальным изменением, limit ограничивает
    количество возвращаемых строк.
    """
    query = "SELECT platform_id, changed, summary, detected_at FROM findings WHERE 1 = 1"
    params: list[object] = []

    if platform_id is not None:
        query += " AND platform_id = ?"
        params.append(platform_id)
    if only_changed:
        query += " AND changed = 1"

    query += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        DiffResult(
            platform_id=row["platform_id"],
            changed=bool(row["changed"]),
            summary=row["summary"],
            detected_at=datetime.fromisoformat(row["detected_at"]),
        )
        for row in rows
    ]
