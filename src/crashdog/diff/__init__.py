"""Общие типы для сравнения снэпшотов — по обоим трекам, structured и textual."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DiffResult:
    """Результат сравнения двух снэпшотов одной площадки, независимо от трека."""

    platform_id: str
    changed: bool
    summary: str
    detected_at: datetime
