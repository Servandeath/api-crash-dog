"""Загрузка и валидация конфигурации площадок из platforms.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

VALID_TRACKS = {"structured", "textual"}


class ConfigError(Exception):
    """Ошибка в конфигурации площадок: отсутствует поле, неверное значение и т.п."""


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    docs_url: str
    track: str
    spec_url: str | None = None
    spec_source: str | None = None
    spec_repo: str | None = None


def load_platforms(path: str | Path = "platforms.yaml") -> list[Platform]:
    """Читает и валидирует список площадок из YAML-файла.

    Бросает ConfigError, если файл не найден, повреждён, у площадки
    отсутствуют обязательные поля, указан недопустимый track,
    повторяется id, или для structured-трека не указано ни spec_url,
    ни пара spec_source+spec_repo.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise ConfigError(f"Файл конфигурации не найден: {file_path}")

    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Не удалось разобрать YAML: {exc}") from exc

    if not raw or "platforms" not in raw:
        raise ConfigError("В конфигурации отсутствует ключ 'platforms'")

    entries = raw["platforms"]
    if not isinstance(entries, list) or not entries:
        raise ConfigError("Список 'platforms' пуст или имеет неверный формат")

    platforms: list[Platform] = []
    seen_ids: set[str] = set()

    for index, entry in enumerate(entries):
        platform = _parse_entry(entry, index)
        if platform.id in seen_ids:
            raise ConfigError(f"Повторяющийся id площадки: {platform.id}")
        seen_ids.add(platform.id)
        platforms.append(platform)

    return platforms


def _parse_entry(entry: dict, index: int) -> Platform:
    required = ("id", "name", "docs_url", "track")
    missing = [field for field in required if field not in entry]
    if missing:
        raise ConfigError(f"Площадка #{index}: отсутствуют обязательные поля {missing}")

    track = entry["track"]
    if track not in VALID_TRACKS:
        raise ConfigError(
            f"Площадка '{entry['id']}': недопустимый track '{track}', "
            f"ожидается одно из {sorted(VALID_TRACKS)}"
        )

    docs_url = entry["docs_url"]
    if not docs_url.startswith(("http://", "https://")):
        raise ConfigError(f"Площадка '{entry['id']}': docs_url должен начинаться с http(s)://")

    spec_url = entry.get("spec_url")
    spec_source = entry.get("spec_source")
    spec_repo = entry.get("spec_repo")

    if track == "structured" and not spec_url and not (spec_source and spec_repo):
        raise ConfigError(
            f"Площадка '{entry['id']}': track=structured требует "
            "spec_url либо пару spec_source+spec_repo"
        )

    return Platform(
        id=entry["id"],
        name=entry["name"],
        docs_url=docs_url,
        track=track,
        spec_url=spec_url,
        spec_source=spec_source,
        spec_repo=spec_repo,
    )


def get_platform(platforms: list[Platform], platform_id: str) -> Platform:
    """Находит площадку по id, бросает ConfigError, если её нет в списке."""
    for platform in platforms:
        if platform.id == platform_id:
            return platform
    raise ConfigError(f"Площадка с id '{platform_id}' не найдена")