"""Снятие сырого снэпшота с площадки: URL или GitHub-репозиторий."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from crashdog.config import Platform


class SnapshotError(Exception):
    """Ошибка при получении снэпшота: сеть, HTTP-статус, неверный формат ответа."""


@dataclass(frozen=True)
class Snapshot:
    platform_id: str
    content: str
    fetched_at: datetime


def take_snapshot(platform: Platform, timeout: float = 15.0) -> Snapshot:
    """Возвращает сырое содержимое площадки — не важно, откуда оно взято.

    Для structured-площадок со spec_url — скачивает файл спеки.
    Для structured-площадок с spec_source=github — берёт SHA последнего
    коммита в репозитории.
    Для textual-площадок — скачивает страницу документации как есть,
    без интерпретации содержимого.
    """
    if platform.spec_source == "github":
        content = _fetch_github_latest_commit(platform, timeout)
    elif platform.spec_url:
        content = _fetch_url(platform.spec_url, timeout)
    else:
        content = _fetch_url(platform.docs_url, timeout)

    return Snapshot(
        platform_id=platform.id,
        content=content,
        fetched_at=datetime.now(timezone.utc),
    )


def _fetch_url(url: str, timeout: float) -> str:
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SnapshotError(f"Не удалось получить {url}: {exc}") from exc
    return response.text


def _fetch_github_latest_commit(platform: Platform, timeout: float) -> str:
    if not platform.spec_repo:
        raise SnapshotError(f"Площадка '{platform.id}': не указан spec_repo для GitHub-трека")

    api_url = f"https://api.github.com/repos/{platform.spec_repo}/commits"
    try:
        response = httpx.get(
            api_url,
            params={"per_page": 1},
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SnapshotError(f"Не удалось получить коммиты {platform.spec_repo}: {exc}") from exc

    commits = response.json()
    if not commits:
        raise SnapshotError(f"У репозитория {platform.spec_repo} нет коммитов")

    return commits[0]["sha"]