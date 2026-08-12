"""Тесты загрузки и валидации конфигурации площадок."""

import pytest

from crashdog.config import ConfigError, get_platform, load_platforms


def test_load_real_platforms_returns_six_entries(real_platforms_path):
    platforms = load_platforms(real_platforms_path)
    assert len(platforms) == 6


def test_wildberries_parsed_correctly(real_platforms_path):
    platforms = load_platforms(real_platforms_path)
    wb = get_platform(platforms, "wildberries")
    assert wb.name == "Wildberries"
    assert wb.track == "structured"
    assert wb.spec_url is not None


def test_moysklad_uses_github_source(real_platforms_path):
    platforms = load_platforms(real_platforms_path)
    ms = get_platform(platforms, "moysklad")
    assert ms.spec_source == "github"
    assert ms.spec_repo == "moysklad/api-remap-1.2-openapi-specification"


def test_missing_file_raises_config_error(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(ConfigError, match="не найден"):
        load_platforms(missing)


def test_broken_yaml_raises_config_error(tmp_path):
    bad_file = tmp_path / "broken.yaml"
    bad_file.write_text("platforms: [this is: not valid: yaml", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_platforms(bad_file)


def test_missing_required_field_raises(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "platforms:\n  - id: test\n    name: Test\n    docs_url: https://example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="обязательные поля"):
        load_platforms(config)


def test_invalid_track_raises(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "platforms:\n"
        "  - id: test\n"
        "    name: Test\n"
        "    docs_url: https://example.com\n"
        "    track: banana\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="недопустимый track"):
        load_platforms(config)


def test_duplicate_id_raises(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "platforms:\n"
        "  - id: dup\n"
        "    name: A\n"
        "    docs_url: https://example.com\n"
        "    track: textual\n"
        "  - id: dup\n"
        "    name: B\n"
        "    docs_url: https://example.com\n"
        "    track: textual\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Повторяющийся id"):
        load_platforms(config)


def test_structured_without_spec_source_raises(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "platforms:\n"
        "  - id: test\n"
        "    name: Test\n"
        "    docs_url: https://example.com\n"
        "    track: structured\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="требует"):
        load_platforms(config)


def test_get_platform_not_found_raises(real_platforms_path):
    platforms = load_platforms(real_platforms_path)
    with pytest.raises(ConfigError, match="не найдена"):
        get_platform(platforms, "nonexistent")