"""Тесты сравнения снэпшотов структурированного трека."""

from datetime import datetime, timezone

from crashdog.config import Platform
from crashdog.diff import DiffResult
from crashdog.diff.structured import compare
from crashdog.snapshot import Snapshot


def _snap(content: str) -> Snapshot:
    return Snapshot(platform_id="test", content=content, fetched_at=datetime.now(timezone.utc))


def _wb_platform() -> Platform:
    return Platform(
        id="wildberries", name="Wildberries", docs_url="https://openapi.wildberries.ru",
        track="structured", spec_url="https://openapi.wildberries.ru/spec.yaml",
    )


def _moysklad_platform() -> Platform:
    return Platform(
        id="moysklad", name="МойСклад", docs_url="https://dev.moysklad.ru",
        track="structured", spec_source="github",
        spec_repo="moysklad/api-remap-1.2-openapi-specification",
    )


def test_first_run_is_not_a_change():
    result = compare(_wb_platform(), None, _snap("paths: {}"))
    assert isinstance(result, DiffResult)
    assert result.changed is False
    assert "Первый снэпшот" in result.summary


def test_identical_commit_sha_is_not_a_change():
    result = compare(_moysklad_platform(), _snap("abc123"), _snap("abc123"))
    assert result.changed is False


def test_different_commit_sha_is_a_change():
    result = compare(_moysklad_platform(), _snap("abc123"), _snap("def456"))
    assert result.changed is True
    assert "def456"[:7] in result.summary
    assert "moysklad/api-remap-1.2-openapi-specification" in result.summary


def test_identical_structured_content_is_not_a_change():
    yaml_text = "paths:\n  /orders:\n    get: {}\n"
    result = compare(_wb_platform(), _snap(yaml_text), _snap(yaml_text))
    assert result.changed is False


def test_top_level_key_change_is_reported_by_path():
    old = "paths:\n  /orders:\n    get: v1\n"
    new = "paths:\n  /orders:\n    get: v2\n"
    result = compare(_wb_platform(), _snap(old), _snap(new))
    assert result.changed is True
    assert "paths.orders.get" not in result.summary  # проверяем, что путь строится через реальные ключи
    assert "paths./orders.get" in result.summary


def test_added_and_removed_keys_are_annotated():
    old = "paths:\n  /orders: {}\n"
    new = "paths:\n  /stocks: {}\n"
    result = compare(_wb_platform(), _snap(old), _snap(new))
    assert "paths./stocks (добавлено)" in result.summary
    assert "paths./orders (удалено)" in result.summary


def test_formatting_only_change_is_not_a_change():
    old = "paths:\n  /orders: {}\n"
    new = "paths:\n    /orders: {}\n"  # другой отступ, тот же YAML-результат
    result = compare(_wb_platform(), _snap(old), _snap(new))
    assert result.changed is False
    assert "форматировании" in result.summary


def test_unparseable_content_falls_back_to_raw_change():
    result = compare(_wb_platform(), _snap("paths: {}"), _snap("paths: [unclosed"))
    assert result.changed is True
    assert "не удалось разобрать" in result.summary


def test_non_dict_top_level_falls_back_to_raw_change():
    result = compare(_wb_platform(), _snap("- a\n- b\n"), _snap("- a\n- c\n"))
    assert result.changed is True
    assert "не словарь" in result.summary


def test_more_than_five_changed_paths_are_truncated():
    old_lines = "\n".join(f"key{i}: old" for i in range(7))
    new_lines = "\n".join(f"key{i}: new" for i in range(7))
    result = compare(_wb_platform(), _snap(old_lines), _snap(new_lines))
    assert "и ещё 2" in result.summary