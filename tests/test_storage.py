"""Тесты хранилища снэпшотов и находок."""

from datetime import datetime, timedelta, timezone

import pytest

from crashdog.diff import DiffResult
from crashdog.snapshot import Snapshot
from crashdog.storage import connect, get_findings, get_latest_snapshot, save_finding, save_snapshot


def _snap(platform_id: str, content: str, when: datetime) -> Snapshot:
    return Snapshot(platform_id=platform_id, content=content, fetched_at=when)


def _finding(platform_id: str, changed: bool, summary: str, when: datetime) -> DiffResult:
    return DiffResult(platform_id=platform_id, changed=changed, summary=summary, detected_at=when)


def test_get_latest_snapshot_returns_none_when_empty(tmp_path):
    with connect(tmp_path / "db.sqlite3") as conn:
        assert get_latest_snapshot(conn, "wildberries") is None


def test_save_and_get_latest_snapshot_roundtrip(tmp_path):
    now = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_snapshot(conn, _snap("wildberries", "openapi: 3.0.0", now))

    with connect(tmp_path / "db.sqlite3") as conn:
        result = get_latest_snapshot(conn, "wildberries")

    assert result is not None
    assert result.platform_id == "wildberries"
    assert result.content == "openapi: 3.0.0"
    assert result.fetched_at == now


def test_get_latest_snapshot_returns_most_recent(tmp_path):
    older = datetime.now(timezone.utc) - timedelta(days=1)
    newer = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_snapshot(conn, _snap("wildberries", "old content", older))
        save_snapshot(conn, _snap("wildberries", "new content", newer))
        result = get_latest_snapshot(conn, "wildberries")

    assert result.content == "new content"


def test_get_latest_snapshot_is_scoped_to_platform(tmp_path):
    now = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_snapshot(conn, _snap("wildberries", "wb content", now))
        save_snapshot(conn, _snap("moysklad", "ms content", now))
        result = get_latest_snapshot(conn, "moysklad")

    assert result.content == "ms content"


def test_save_finding_and_get_findings_roundtrip(tmp_path):
    now = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_finding(conn, _finding("wildberries", True, "Изменились пути: paths./orders", now))
        findings = get_findings(conn)

    assert len(findings) == 1
    assert findings[0].platform_id == "wildberries"
    assert findings[0].changed is True
    assert findings[0].summary == "Изменились пути: paths./orders"
    assert findings[0].detected_at == now


def test_get_findings_orders_newest_first(tmp_path):
    older = datetime.now(timezone.utc) - timedelta(hours=1)
    newer = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_finding(conn, _finding("wildberries", False, "старая находка", older))
        save_finding(conn, _finding("wildberries", True, "новая находка", newer))
        findings = get_findings(conn)

    assert [f.summary for f in findings] == ["новая находка", "старая находка"]


def test_get_findings_filters_by_platform(tmp_path):
    now = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_finding(conn, _finding("wildberries", True, "wb находка", now))
        save_finding(conn, _finding("moysklad", True, "ms находка", now))
        findings = get_findings(conn, platform_id="moysklad")

    assert len(findings) == 1
    assert findings[0].platform_id == "moysklad"


def test_get_findings_only_changed_excludes_unchanged(tmp_path):
    now = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        save_finding(conn, _finding("wildberries", False, "без изменений", now))
        save_finding(conn, _finding("wildberries", True, "есть изменения", now))
        findings = get_findings(conn, only_changed=True)

    assert len(findings) == 1
    assert findings[0].summary == "есть изменения"


def test_get_findings_respects_limit(tmp_path):
    now = datetime.now(timezone.utc)
    with connect(tmp_path / "db.sqlite3") as conn:
        for i in range(3):
            save_finding(conn, _finding("wildberries", True, f"находка {i}", now + timedelta(seconds=i)))
        findings = get_findings(conn, limit=2)

    assert len(findings) == 2


def test_schema_is_idempotent_across_connections(tmp_path):
    db_path = tmp_path / "db.sqlite3"
    with connect(db_path):
        pass
    with connect(db_path):
        pass  # не должно падать на повторном CREATE TABLE / CREATE INDEX
