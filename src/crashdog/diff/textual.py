"""Сравнение снэпшотов для текстового трека (Ozon, Lamoda, Деловые Линии).

Формального контракта нет — сравнивается содержимое страницы документации
построчно. Пустые строки и различия в отступах по краям строки не
считаются изменением: сайты документации часто перевёрстывают разметку,
не меняя сути текста.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone

from crashdog.config import Platform
from crashdog.diff import DiffResult
from crashdog.snapshot import Snapshot

MAX_SHOWN = 5
LINE_LIMIT = 80


def compare(platform: Platform, previous: Snapshot | None, current: Snapshot) -> DiffResult:
    """Сравнивает текущий снэпшот с предыдущим для площадки текстового трека.

    Если previous is None — это первый прогон, база для сравнения только
    закладывается, изменений по определению нет.
    """
    if previous is None:
        return _result(platform.id, changed=False, summary="Первый снэпшот, база для сравнения заложена")

    if previous.content == current.content:
        return _result(platform.id, changed=False, summary="Содержимое страницы не изменилось")

    changed_lines = _diff_lines(previous.content, current.content)
    if not changed_lines:
        return _result(
            platform.id, changed=False,
            summary="Различия только в пробелах и пустых строках, текст не менялся",
        )

    shown = changed_lines[:MAX_SHOWN]
    more = f" и ещё {len(changed_lines) - MAX_SHOWN}" if len(changed_lines) > MAX_SHOWN else ""
    summary = f"Изменились строки: {'; '.join(shown)}{more}"
    return _result(platform.id, changed=True, summary=summary)


def _diff_lines(old: str, new: str) -> list[str]:
    """Построчный дифф без учёта пустых строк и краевых пробелов.

    Возвращает список аннотированных строк вида "+добавлено" / "−удалено".
    Для replace-блока сначала идут удалённые, затем добавленные строки —
    без попытки сматчить их между собой построчно.
    """
    old_lines = [line.strip() for line in old.splitlines() if line.strip()]
    new_lines = [line.strip() for line in new.splitlines() if line.strip()]

    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changes: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            changes.extend(f"−{_short(line)}" for line in old_lines[i1:i2])
        if tag in ("insert", "replace"):
            changes.extend(f"+{_short(line)}" for line in new_lines[j1:j2])

    return changes


def _short(line: str, limit: int = LINE_LIMIT) -> str:
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _result(platform_id: str, *, changed: bool, summary: str) -> DiffResult:
    return DiffResult(
        platform_id=platform_id,
        changed=changed,
        summary=summary,
        detected_at=datetime.now(timezone.utc),
    )
