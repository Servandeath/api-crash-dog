"""Тесты сравнения снэпшотов текстового трека."""

from datetime import datetime, timezone

from crashdog.config import Platform
from crashdog.diff import DiffResult
from crashdog.diff.textual import compare
from crashdog.snapshot import Snapshot


def _snap(content: str) -> Snapshot:
    return Snapshot(platform_id="test", content=content, fetched_at=datetime.now(timezone.utc))


def _ozon_platform() -> Platform:
    return Platform(
        id="ozon", name="Ozon Seller", docs_url="https://docs.ozon.ru/api/seller", track="textual",
    )


def test_first_run_is_not_a_change():
    result = compare(_ozon_platform(), None, _snap("<html>docs</html>"))
    assert isinstance(result, DiffResult)
    assert result.changed is False
    assert "Первый снэпшот" in result.summary


def test_identical_content_is_not_a_change():
    html = "<p>Метод получения заказов</p>"
    result = compare(_ozon_platform(), _snap(html), _snap(html))
    assert result.changed is False


def test_whitespace_only_change_is_not_a_change():
    old = "Метод получения заказов\n\nОписание метода"
    new = "  Метод получения заказов  \n\n\nОписание метода  "
    result = compare(_ozon_platform(), _snap(old), _snap(new))
    assert result.changed is False
    assert "пробелах" in result.summary


def test_added_line_is_reported():
    old = "Метод получения заказов"
    new = "Метод получения заказов\nНовое обязательное поле order_id"
    result = compare(_ozon_platform(), _snap(old), _snap(new))
    assert result.changed is True
    assert "+Новое обязательное поле order_id" in result.summary


def test_removed_line_is_reported():
    old = "Метод получения заказов\nУстаревшее поле legacy_id"
    new = "Метод получения заказов"
    result = compare(_ozon_platform(), _snap(old), _snap(new))
    assert result.changed is True
    assert "−Устаревшее поле legacy_id" in result.summary


def test_replaced_line_shows_both_removed_and_added():
    old = "Метод возвращает статус в поле status_v1"
    new = "Метод возвращает статус в поле status_v2"
    result = compare(_ozon_platform(), _snap(old), _snap(new))
    assert result.changed is True
    assert "−Метод возвращает статус в поле status_v1" in result.summary
    assert "+Метод возвращает статус в поле status_v2" in result.summary


def test_long_line_is_truncated_in_summary():
    old = "короткая строка"
    new = "о" * 200
    result = compare(_ozon_platform(), _snap(old), _snap(new))
    assert result.changed is True
    assert "…" in result.summary
    assert "о" * 200 not in result.summary


def test_more_than_five_changed_lines_are_truncated():
    old = "\n".join(f"строка{i}" for i in range(7))
    new = "\n".join(f"строка{i}-изменена" for i in range(7))
    result = compare(_ozon_platform(), _snap(old), _snap(new))
    assert result.changed is True
    assert "и ещё" in result.summary
