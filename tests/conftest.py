"""Общие фикстуры для тестов api-crash-dog."""

from pathlib import Path

import pytest


@pytest.fixture
def real_platforms_path() -> Path:
    """Путь к боевому platforms.yaml в корне репозитория."""
    return Path(__file__).resolve().parent.parent / "platforms.yaml"