"""Снятие сырого снэпшота с площадки: URL или GitHub-репозиторий."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from crashdog.config import Platform

# Многие площадки отдают 403 (или обрывают TLS-хендшейк) клиентам без
# браузероподобного User-Agent — стандартный "python-httpx/x.x" под это
# попадает. Заголовок ничего не подделывает по содержанию ответа, только
# снижает шанс попасть под антибот-фильтр по одному этому признаку.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


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
    Для structured-площадок с spec_source=local — читает файл с диска
    (spec_path): для площадок за антибот-защитой, которую нельзя обойти
    простым HTTP-запросом, файл обновляется вручную, а не по сети.
    Для textual-площадок — скачивает страницу документации как есть,
    без интерпретации содержимого.
    """
    if platform.spec_source == "github":
        content = _fetch_github_latest_commit(platform, timeout)
    elif platform.spec_source == "local":
        content = _read_local_spec(platform)
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
        response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SnapshotError(f"Не удалось получить {url}: {exc}") from exc
    return response.text


def _read_local_spec(platform: Platform) -> str:
    if not platform.spec_path:
        raise SnapshotError(f"Площадка '{platform.id}': не указан spec_path для local-источника")

    path = Path(platform.spec_path)
    if not path.exists():
        raise SnapshotError(
            f"Площадка '{platform.id}': локальный файл спеки не найден: {path}. "
            "Скачайте актуальную версию через браузер и сохраните по этому пути."
        )
    return path.read_text(encoding="utf-8")


def _fetch_github_latest_commit(platform: Platform, timeout: float) -> str:
    if not platform.spec_repo:
        raise SnapshotError(f"Площадка '{platform.id}': не указан spec_repo для GitHub-трека")

    api_url = f"https://api.github.com/repos/{platform.spec_repo}/commits"
    try:
        response = httpx.get(
            api_url,
            params={"per_page": 1},
            timeout=timeout,
            headers={**DEFAULT_HEADERS, "Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise SnapshotError(f"Не удалось получить коммиты {platform.spec_repo}: {exc}") from exc

    commits = response.json()
    if not commits:
        raise SnapshotError(f"У репозитория {platform.spec_repo} нет коммитов")

    return commits[0]["sha"]