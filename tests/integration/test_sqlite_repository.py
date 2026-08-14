from datetime import date, datetime
import sqlite3

import pytest

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from infra.storage.sqlite_repository import SqliteReportStorageAdapter


def _make_event(event_id="2026-W26", status=CollectionStatus.COMPLETED, items=None):
    return WeeklyCollectionEvent(
        id=event_id,
        year=2026,
        week=26,
        collected_at=datetime(2026, 6, 26, 18, 0, 0),
        day_of_week="Friday",
        last_trading_day=date(2026, 6, 26),
        status=status,
        items=items if items is not None else [
            WeeklyGainerItem(
                symbol_code="005930",
                symbol_name="삼성전자",
                start_date=date(2026, 6, 22),
                base_price=70000.0,
                end_date=date(2026, 6, 26),
                close_price=85000.0,
                change=15000.0,
                change_rate=21.43,
                volume=100000,
                amount=8500000000,
            ),
        ],
        total_count=1000,
        fingerprint="005930:21.43",
    )


def test_save_and_get_by_id_round_trip(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    event = _make_event()

    repo.save(event)
    loaded = repo.get_by_id("2026-W26")

    assert loaded is not None
    assert loaded.id == "2026-W26"
    assert loaded.year == 2026
    assert loaded.week == 26
    assert loaded.status == CollectionStatus.COMPLETED
    assert loaded.fingerprint == "005930:21.43"
    assert loaded.last_trading_day == date(2026, 6, 26)
    assert loaded.collected_at == datetime(2026, 6, 26, 18, 0, 0)

    assert len(loaded.items) == 1
    item = loaded.items[0]
    assert item.symbol_code == "005930"
    assert item.symbol_name == "삼성전자"
    assert item.start_date == date(2026, 6, 22)
    assert item.end_date == date(2026, 6, 26)
    assert item.base_price == 70000.0
    assert item.close_price == 85000.0
    assert item.change == 15000.0
    assert item.change_rate == 21.43
    assert item.volume == 100000
    assert item.amount == 8500000000


def test_get_by_id_missing_returns_none(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    assert repo.get_by_id("2026-W01") is None


def test_exists_true_only_when_completed(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")

    repo.save(_make_event(event_id="2026-W01", status=CollectionStatus.PENDING))
    repo.save(_make_event(event_id="2026-W02", status=CollectionStatus.COMPLETED))

    assert repo.exists("2026-W01") is False
    assert repo.exists("2026-W02") is True
    assert repo.exists("2026-W99") is False


def test_save_replaces_items_on_resave(tmp_path):
    """같은 event_id를 다시 저장하면 items가 누적되지 않고 최신 스냅샷으로 전체 교체된다."""
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")

    first_items = [
        WeeklyGainerItem(
            symbol_code="005930", symbol_name="삼성전자",
            start_date=date(2026, 6, 22), base_price=70000.0,
            end_date=date(2026, 6, 26), close_price=85000.0,
            change=15000.0, change_rate=21.43, volume=100000, amount=8500000000,
        ),
    ]
    second_items = [
        WeeklyGainerItem(
            symbol_code="000660", symbol_name="SK하이닉스",
            start_date=date(2026, 6, 22), base_price=150000.0,
            end_date=date(2026, 6, 26), close_price=190000.0,
            change=40000.0, change_rate=26.67, volume=50000, amount=9000000000,
        ),
    ]

    repo.save(_make_event(items=first_items, status=CollectionStatus.COMPLETED))
    repo.save(_make_event(items=second_items, status=CollectionStatus.FINAL, ))

    loaded = repo.get_by_id("2026-W26")
    assert loaded.status == CollectionStatus.FINAL
    assert len(loaded.items) == 1
    assert loaded.items[0].symbol_code == "000660"


def test_weekly_and_monthly_period_types_are_physically_isolated(tmp_path):
    base = str(tmp_path / "db")
    weekly_repo = SqliteReportStorageAdapter(base_dir=base, period_type="WEEKLY")
    monthly_repo = SqliteReportStorageAdapter(base_dir=base, period_type="MONTHLY")

    weekly_repo.save(_make_event(event_id="2026-W26"))
    monthly_event = _make_event(event_id="2026-M06")
    monthly_event.week = 0
    monthly_event.month = 6
    monthly_repo.save(monthly_event)

    assert weekly_repo.get_by_id("2026-M06") is None
    assert monthly_repo.get_by_id("2026-W26") is None
    assert weekly_repo.get_by_id("2026-W26") is not None
    assert monthly_repo.get_by_id("2026-M06") is not None

    assert (tmp_path / "db" / "weekly" / "2026.db").exists()
    assert (tmp_path / "db" / "monthly" / "2026.db").exists()


def test_db_file_has_events_and_items_tables(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    repo.save(_make_event())

    conn = sqlite3.connect(tmp_path / "db" / "weekly" / "2026.db")
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "events" in tables
        assert "items" in tables
    finally:
        conn.close()
