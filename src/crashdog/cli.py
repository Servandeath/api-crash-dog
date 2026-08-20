"""CLI-оркестратор: прогоняет проверку всех площадок из конфига разом.

Логика одного прогона: конфиг → снэпшот → сравнение с предыдущим (из БД) →
запись находки и снэпшота обратно в БД. Сравнение маршрутизируется по
track площадки: structured → diff.structured, textual → diff.textual.
Сбой снятия снэпшота для одной площадки не останавливает остальные.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from crashdog.config import ConfigError, Platform, load_platforms
from crashdog.diff import structured as diff_structured
from crashdog.diff import textual as diff_textual
from crashdog.snapshot import SnapshotError, take_snapshot
from crashdog.storage import connect, get_latest_snapshot, save_finding, save_snapshot

COMPARERS = {
    "structured": diff_structured.compare,
    "textual": diff_textual.compare,
}


@dataclass(frozen=True)
class RunOutcome:
    """Итог проверки одной площадки за один прогон."""

    platform_id: str
    status: str  # "changed" | "unchanged" | "skipped" | "error"
    detail: str


def run(config_path: str = "platforms.yaml", db_path: str = "crashdog.sqlite3") -> list[RunOutcome]:
    """Проверяет все площадки из конфига, пишет снэпшоты и находки в БД.

    Бросает ConfigError, если сам platforms.yaml не читается — это
    останавливает прогон целиком, поскольку без конфига нечего проверять.
    Ошибки отдельных площадок (сеть, HTTP) в это не входят и в список
    результатов попадают как status="error".
    """
    platforms = load_platforms(config_path)
    return [_check_platform(platform, db_path) for platform in platforms]


def _check_platform(platform: Platform, db_path: str) -> RunOutcome:
    compare = COMPARERS.get(platform.track)
    if compare is None:
        return RunOutcome(platform.id, "skipped", f"track='{platform.track}' пока не реализован")

    try:
        current = take_snapshot(platform)
    except SnapshotError as exc:
        return RunOutcome(platform.id, "error", str(exc))

    with connect(db_path) as conn:
        previous = get_latest_snapshot(conn, platform.id)
        result = compare(platform, previous, current)
        save_finding(conn, result)
        save_snapshot(conn, current)

    status = "changed" if result.changed else "unchanged"
    return RunOutcome(platform.id, status, result.summary)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI. Возвращает код возврата процесса (0 — всё ок)."""
    parser = argparse.ArgumentParser(
        prog="crashdog", description="Проверка изменений в контрактах внешних API"
    )
    parser.add_argument("--config", default="platforms.yaml", help="Путь к platforms.yaml")
    parser.add_argument("--db", default="crashdog.sqlite3", help="Путь к файлу базы SQLite")
    args = parser.parse_args(argv)

    try:
        outcomes = run(args.config, args.db)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    had_error = False
    for outcome in outcomes:
        if outcome.status == "changed":
            print(f"[ИЗМЕНЕНИЕ] {outcome.platform_id}: {outcome.detail}")
        elif outcome.status == "unchanged":
            print(f"[без изменений] {outcome.platform_id}: {outcome.detail}")
        elif outcome.status == "skipped":
            print(f"[пропущено] {outcome.platform_id}: {outcome.detail}")
        elif outcome.status == "error":
            print(f"[ОШИБКА] {outcome.platform_id}: {outcome.detail}", file=sys.stderr)
            had_error = True

    return 1 if had_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
