"""Загрузка и валидация конфигурации площадок из platforms.yaml."""

from dataclasses import dataclass
from pathlib import Path

import yaml

VALID_TRACKS = {"structured", "textual"}
VALID_SPEC_SOURCES = {"github", "local"}


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
    spec_path: str | None = None


def load_platforms(path: str | Path = "platforms.yaml") -> list[Platform]:
    """Читает и валидирует список площадок из YAML-файла.

    Бросает ConfigError, если файл не найден, повреждён, у площадки
    отсутствуют обязательные поля, указан недопустимый track или
    spec_source, повторяется id, или для structured-трека не указан
    ни один из способов получить контракт: spec_url, spec_source=github
    (+spec_repo) или spec_source=local (+spec_path).
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
    spec_path = entry.get("spec_path")

    if spec_source is not None and spec_source not in VALID_SPEC_SOURCES:
        raise ConfigError(
            f"Площадка '{entry['id']}': недопустимый spec_source '{spec_source}', "
            f"ожидается одно из {sorted(VALID_SPEC_SOURCES)}"
        )
    if spec_source == "github" and not spec_repo:
        raise ConfigError(f"Площадка '{entry['id']}': spec_source=github требует spec_repo")
    if spec_source == "local" and not spec_path:
        raise ConfigError(f"Площадка '{entry['id']}': spec_source=local требует spec_path")

    has_spec_source = spec_source == "github" and spec_repo or spec_source == "local" and spec_path
    if track == "structured" and not spec_url and not has_spec_source:
        raise ConfigError(
            f"Площадка '{entry['id']}': track=structured требует spec_url, "
            "либо spec_source=github+spec_repo, либо spec_source=local+spec_path"
        )

    return Platform(
        id=entry["id"],
        name=entry["name"],
        docs_url=docs_url,
        track=track,
        spec_url=spec_url,
        spec_source=spec_source,
        spec_repo=spec_repo,
        spec_path=spec_path,
    )


def get_platform(platforms: list[Platform], platform_id: str) -> Platform:
    """Находит площадку по id, бросает ConfigError, если её нет в списке."""
    for platform in platforms:
        if platform.id == platform_id:
            return platform
    raise ConfigError(f"Площадка с id '{platform_id}' не найдена")