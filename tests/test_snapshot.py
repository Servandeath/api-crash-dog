"""Тесты получения снэпшота с площадки."""

from datetime import datetime

import httpx
import pytest

from crashdog.config import Platform
from crashdog.snapshot import Snapshot, SnapshotError, take_snapshot


class _FakeResponse:
    def __init__(self, text="", json_data=None, status_code=200):
        self.text = text
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("mocked failure", request=None, response=self)

    def json(self):
        return self._json_data


def test_direct_spec_url_returns_content(monkeypatch):
    platform = Platform(
        id="wildberries", name="Wildberries", docs_url="https://openapi.wildberries.ru",
        track="structured", spec_url="https://openapi.wildberries.ru/spec.yaml",
    )

    def fake_get(url, **kwargs):
        assert url == platform.spec_url
        return _FakeResponse(text="openapi: 3.0.0")

    monkeypatch.setattr(httpx, "get", fake_get)

    snapshot = take_snapshot(platform)

    assert isinstance(snapshot, Snapshot)
    assert snapshot.platform_id == "wildberries"
    assert snapshot.content == "openapi: 3.0.0"
    assert isinstance(snapshot.fetched_at, datetime)


def test_github_source_returns_latest_commit_sha(monkeypatch):
    platform = Platform(
        id="moysklad", name="МойСклад", docs_url="https://dev.moysklad.ru",
        track="structured", spec_source="github",
        spec_repo="moysklad/api-remap-1.2-openapi-specification",
    )

    def fake_get(url, **kwargs):
        assert "api.github.com/repos/moysklad" in url
        return _FakeResponse(json_data=[{"sha": "abc123"}])

    monkeypatch.setattr(httpx, "get", fake_get)

    snapshot = take_snapshot(platform)

    assert snapshot.content == "abc123"


def test_textual_platform_fetches_docs_url(monkeypatch):
    platform = Platform(
        id="ozon", name="Ozon Seller", docs_url="https://docs.ozon.ru/api/seller",
        track="textual",
    )

    def fake_get(url, **kwargs):
        assert url == platform.docs_url
        return _FakeResponse(text="<html>docs</html>")

    monkeypatch.setattr(httpx, "get", fake_get)

    snapshot = take_snapshot(platform)

    assert snapshot.content == "<html>docs</html>"


def test_http_error_raises_snapshot_error(monkeypatch):
    platform = Platform(
        id="wildberries", name="Wildberries", docs_url="https://openapi.wildberries.ru",
        track="structured", spec_url="https://openapi.wildberries.ru/spec.yaml",
    )

    def fake_get(url, **kwargs):
        return _FakeResponse(status_code=500)

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(SnapshotError):
        take_snapshot(platform)


def test_github_source_without_spec_repo_raises():
    platform = Platform(
        id="broken", name="Broken", docs_url="https://example.com",
        track="structured", spec_source="github",
    )

    with pytest.raises(SnapshotError, match="spec_repo"):
        take_snapshot(platform)


def test_local_source_reads_file_from_disk(tmp_path):
    spec_file = tmp_path / "wildberries-general.yaml"
    spec_file.write_text("openapi: 3.0.0\npaths: {}\n", encoding="utf-8")

    platform = Platform(
        id="wildberries", name="Wildberries", docs_url="https://dev.wildberries.ru",
        track="structured", spec_source="local", spec_path=str(spec_file),
    )

    snapshot = take_snapshot(platform)

    assert snapshot.platform_id == "wildberries"
    assert snapshot.content == "openapi: 3.0.0\npaths: {}\n"


def test_local_source_missing_file_raises(tmp_path):
    platform = Platform(
        id="wildberries", name="Wildberries", docs_url="https://dev.wildberries.ru",
        track="structured", spec_source="local", spec_path=str(tmp_path / "does_not_exist.yaml"),
    )

    with pytest.raises(SnapshotError, match="не найден"):
        take_snapshot(platform)


def test_local_source_without_spec_path_raises():
    platform = Platform(
        id="wildberries", name="Wildberries", docs_url="https://dev.wildberries.ru",
        track="structured", spec_source="local",
    )

    with pytest.raises(SnapshotError, match="spec_path"):
        take_snapshot(platform)


def test_github_source_empty_commits_raises(monkeypatch):
    platform = Platform(
        id="moysklad", name="МойСклад", docs_url="https://dev.moysklad.ru",
        track="structured", spec_source="github",
        spec_repo="moysklad/api-remap-1.2-openapi-specification",
    )

    def fake_get(url, **kwargs):
        return _FakeResponse(json_data=[])

    monkeypatch.setattr(httpx, "get", fake_get)

    with pytest.raises(SnapshotError, match="нет коммитов"):
        take_snapshot(platform)