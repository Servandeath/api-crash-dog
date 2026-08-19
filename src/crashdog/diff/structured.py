"""Сравнение снэпшотов для структурированного трека (WB, МойСклад, MOEX)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import yaml

from crashdog.config import Platform
from crashdog.snapshot import Snapshot


@dataclass(frozen=True)
class DiffResult:
    platform_id: str
    changed: bool
    summary: str
    detected_at: datetime


def compare(platform: Platform, previous: Snapshot | None, current: Snapshot) -> DiffResult:
    """Сравнивает текущий снэпшот с предыдущим для площадки структурированного трека.

    Если previous is None — это первый прогон, база для сравнения только
    закладывается, изменений по определению нет.
    """
    if previous is None:
        return _result(platform.id, changed=False, summary="Первый снэпшот, база для сравнения заложена")

    if platform.spec_source == "github":
        return _compare_commit_sha(platform, previous, current)

    return _compare_structured_content(platform, previous, current)


def _compare_commit_sha(platform: Platform, previous: Snapshot, current: Snapshot) -> DiffResult:
    if previous.content == current.content:
        return _result(platform.id, changed=False, summary="Новых коммитов нет")

    repo_url = f"https://github.com/{platform.spec_repo}/commits"
    summary = f"Новый коммит {current.content[:7]} (было {previous.content[:7]}), смотри {repo_url}"
    return _result(platform.id, changed=True, summary=summary)


def _compare_structured_content(platform: Platform, previous: Snapshot, current: Snapshot) -> DiffResult:
    if previous.content == current.content:
        return _result(platform.id, changed=False, summary="Содержимое не изменилось")

    try:
        old_data = yaml.safe_load(previous.content)
        new_data = yaml.safe_load(current.content)
    except yaml.YAMLError:
        return _result(
            platform.id, changed=True,
            summary="Содержимое изменилось, но не удалось разобрать как YAML/JSON для детализации",
        )

    if not isinstance(old_data, dict) or not isinstance(new_data, dict):
        return _result(platform.id, changed=True, summary="Содержимое изменилось (не словарь верхнего уровня)")

    changed_paths = _diff_paths(old_data, new_data)
    if not changed_paths:
        return _result(platform.id, changed=False, summary="Различия только в форматировании, структура не менялась")

    shown = changed_paths[:5]
    more = f" и ещё {len(changed_paths) - 5}" if len(changed_paths) > 5 else ""
    summary = f"Изменились пути: {', '.join(shown)}{more}"
    return _result(platform.id, changed=True, summary=summary)


def _diff_paths(old: Any, new: Any, prefix: str = "") -> list[str]:
    """Рекурсивно находит изменённые/добавленные/удалённые ключи, возвращает dotted-пути.

    Ограничение: спускается только внутрь dict. Списки сравниваются как есть
    (изменился хоть один элемент — путь считается изменённым целиком, без
    детализации, что именно внутри списка поменялось).
    """
    paths: list[str] = []

    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in old:
                paths.append(f"{path} (добавлено)")
            elif key not in new:
                paths.append(f"{path} (удалено)")
            elif old[key] != new[key]:
                paths.extend(_diff_paths(old[key], new[key], path))
        return paths

    if old != new:
        return [prefix or "(корень)"]
    return []


def _result(platform_id: str, *, changed: bool, summary: str) -> DiffResult:
    return DiffResult(
        platform_id=platform_id,
        changed=changed,
        summary=summary,
        detected_at=datetime.now(timezone.utc),
    )