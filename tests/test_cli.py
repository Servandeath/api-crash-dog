"""Тесты CLI-оркестратора: конфиг → снэпшот → сравнение → запись в БД."""

from datetime import datetime, timezone

import pytest

import crashdog.cli as cli
from crashdog.config import ConfigError
from crashdog.snapshot import Snapshot, SnapshotError
from crashdog.storage import connect, get_findings, get_latest_snapshot

CONFIG_TEXT = """\
platforms:
  - id: wildberries
    name: Wildberries
    docs_url: https://openapi.wildberries.ru
    spec_url: https://openapi.wildberries.ru/spec.yaml
    track: structured
  - id: ozon
    name: Ozon Seller
    docs_url: https://docs.ozon.ru/api/seller
    track: textual
  - id: broken
    name: Broken
    docs_url: https://example.com/broken
    spec_url: https://example.com/broken/spec.yaml
    track: structured
"""


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "platforms.yaml"
    path.write_text(CONFIG_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "crashdog.sqlite3"


DEFAULT_CONTENT = {"wildberries": "openapi: 3.0.0", "ozon": "<html>docs</html>"}


def _fake_take_snapshot(content_by_id: dict[str, str] | None = None, fail_ids: set[str] = frozenset()):
    content_by_id = {**DEFAULT_CONTENT, **(content_by_id or {})}
    def _take(platform, timeout=15.0):
        if platform.id in fail_ids:
            raise SnapshotError(f"мок-сбой для {platform.id}")
        return Snapshot(
            platform_id=platform.id,
            content=content_by_id[platform.id],
            fetched_at=datetime.now(timezone.utc),
        )

    return _take


def test_run_checks_both_tracks_and_reports_error_for_broken(monkeypatch, config_path, db_path):
    monkeypatch.setattr(cli, "take_snapshot", _fake_take_snapshot(fail_ids={"broken"}))

    outcomes = cli.run(config_path, db_path)
    by_id = {o.platform_id: o for o in outcomes}

    assert by_id["wildberries"].status == "unchanged"  # первый прогон — базовый снэпшот
    assert by_id["ozon"].status == "unchanged"  # тоже первый прогон, но по textual-треку
    assert by_id["broken"].status == "error"
    assert "мок-сбой" in by_id["broken"].detail


def test_check_platform_skips_unimplemented_track():
    from crashdog.config import Platform

    platform = Platform(
        id="mystery", name="Mystery", docs_url="https://example.com", track="carrier-pigeon",
    )

    outcome = cli._check_platform(platform, "unused.sqlite3")

    assert outcome.status == "skipped"
    assert "carrier-pigeon" in outcome.detail


def test_run_persists_snapshot_and_finding_for_structured_platform(monkeypatch, config_path, db_path):
    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "openapi: 3.0.0"}, fail_ids={"broken"}),
    )

    cli.run(config_path, db_path)

    with connect(db_path) as conn:
        snapshot = get_latest_snapshot(conn, "wildberries")
        findings = get_findings(conn, platform_id="wildberries")

    assert snapshot is not None
    assert snapshot.content == "openapi: 3.0.0"
    assert len(findings) == 1
    assert findings[0].changed is False


def test_run_persists_textual_platform_but_not_failed_one(monkeypatch, config_path, db_path):
    monkeypatch.setattr(cli, "take_snapshot", _fake_take_snapshot(fail_ids={"broken"}))

    cli.run(config_path, db_path)

    with connect(db_path) as conn:
        assert get_latest_snapshot(conn, "ozon") is not None
        assert get_latest_snapshot(conn, "broken") is None
        assert len(get_findings(conn, platform_id="ozon")) == 1
        assert get_findings(conn, platform_id="broken") == []


def test_second_run_detects_change_against_stored_snapshot(monkeypatch, config_path, db_path):
    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "paths:\n  /orders: {}\n"}, fail_ids={"broken"}),
    )
    cli.run(config_path, db_path)  # первый прогон — закладывает базу

    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "paths:\n  /orders: {}\n  /stocks: {}\n"}, fail_ids={"broken"}),
    )
    outcomes = cli.run(config_path, db_path)

    wb_outcome = next(o for o in outcomes if o.platform_id == "wildberries")
    assert wb_outcome.status == "changed"
    assert "stocks" in wb_outcome.detail


def test_main_returns_zero_when_no_platform_errors(monkeypatch, config_path, db_path, capsys):
    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "openapi: 3.0.0", "broken": "openapi: 3.0.0"}),
    )

    exit_code = cli.main(["--config", str(config_path), "--db", str(db_path)])

    assert exit_code == 0


def test_main_returns_nonzero_when_a_platform_errors(monkeypatch, config_path, db_path):
    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "openapi: 3.0.0"}, fail_ids={"broken"}),
    )

    exit_code = cli.main(["--config", str(config_path), "--db", str(db_path)])

    assert exit_code == 1


def test_main_returns_nonzero_on_missing_config(tmp_path, db_path):
    missing = tmp_path / "does_not_exist.yaml"

    exit_code = cli.main(["--config", str(missing), "--db", str(db_path)])

    assert exit_code == 1


def test_main_prints_change_marker_to_stdout(monkeypatch, config_path, db_path, capsys):
    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "paths:\n  /orders: {}\n"}, fail_ids={"broken"}),
    )
    cli.main(["--config", str(config_path), "--db", str(db_path)])

    monkeypatch.setattr(
        cli,
        "take_snapshot",
        _fake_take_snapshot({"wildberries": "paths:\n  /stocks: {}\n"}, fail_ids={"broken"}),
    )
    cli.main(["--config", str(config_path), "--db", str(db_path)])

    captured = capsys.readouterr()
    assert "[ИЗМЕНЕНИЕ] wildberries" in captured.out
