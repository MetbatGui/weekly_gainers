from datetime import date, datetime
from typing import Optional
import sqlite3

import pytest

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from domain.ports import CloudUploadPort
from infra.storage.sqlite_repository import SqliteReportStorageAdapter


class StubUploader(CloudUploadPort):
    def __init__(self):
        self.uploaded_files = []

    def upload_excel(self, file_content: bytes, remote_path: str, filename: str) -> bool:
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        self.uploaded_files.append((local_path, remote_path, filename, mimetype))
        return True

    def download_file(self, remote_path: str, filename: str) -> Optional[bytes]:
        return None


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


def test_index_membership_flags_round_trip(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    items = [
        WeeklyGainerItem(
            symbol_code="005930", symbol_name="삼성전자",
            start_date=date(2026, 6, 22), base_price=70000.0,
            end_date=date(2026, 6, 26), close_price=85000.0,
            change=15000.0, change_rate=21.43, volume=100000, amount=8500000000,
            in_kospi200=True, in_kosdaq150=False,
        ),
        WeeklyGainerItem(
            symbol_code="900000", symbol_name="비지수종목",
            start_date=date(2026, 6, 22), base_price=1000.0,
            end_date=date(2026, 6, 26), close_price=1300.0,
            change=300.0, change_rate=30.0, volume=1000, amount=1300000,
            in_kospi200=False, in_kosdaq150=False,
        ),
    ]
    repo.save(_make_event(items=items))

    loaded = repo.get_by_id("2026-W26")

    by_code = {item.symbol_code: item for item in loaded.items}
    assert by_code["005930"].in_kospi200 is True
    assert by_code["005930"].in_kosdaq150 is False
    assert by_code["900000"].in_kospi200 is False


def test_legacy_db_without_index_columns_is_migrated_on_read(tmp_path):
    """기존(플래그 컬럼 추가 전) DB 파일도 읽기 시 자동으로 컬럼이 보강된다."""
    db_path = tmp_path / "db" / "weekly"
    db_path.mkdir(parents=True)
    conn = sqlite3.connect(db_path / "2026.db")
    conn.execute(
        """CREATE TABLE items (
            event_id TEXT, symbol_code TEXT, symbol_name TEXT,
            start_date TEXT, base_price REAL, end_date TEXT, close_price REAL,
            change REAL, change_rate REAL, volume INTEGER, amount INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE events (
            id TEXT PRIMARY KEY, year INTEGER, week INTEGER, month INTEGER,
            week_of_month INTEGER, collected_at TEXT, day_of_week TEXT,
            last_trading_day TEXT, status TEXT, total_count INTEGER, fingerprint TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO events VALUES ('2026-W26', 2026, 26, 6, 4, '2026-06-26T18:00:00', 'Friday', '2026-06-26', 'COMPLETED', 1, 'fp')"
    )
    conn.execute(
        "INSERT INTO items (event_id, symbol_code, symbol_name, start_date, base_price, end_date, close_price, change, change_rate, volume, amount) "
        "VALUES ('2026-W26', '005930', '삼성전자', '2026-06-22', 70000.0, '2026-06-26', 85000.0, 15000.0, 21.43, 100000, 8500000000)"
    )
    conn.commit()
    conn.close()

    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    loaded = repo.get_by_id("2026-W26")

    assert loaded is not None
    assert loaded.items[0].in_kospi200 is False
    assert loaded.items[0].in_kosdaq150 is False


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

        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        assert "idx_items_event_id" in indexes
    finally:
        conn.close()


def test_upload_year_to_drive_uploads_db_file(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    repo.save(_make_event())
    uploader = StubUploader()

    result = repo.upload_year_to_drive(2026, uploader)

    assert result is True
    assert len(uploader.uploaded_files) == 1
    local_path, remote_path, filename, mimetype = uploader.uploaded_files[0]
    assert local_path == str(tmp_path / "db" / "weekly" / "2026.db")
    assert remote_path == "db/weekly"
    assert filename == "2026.db"


def test_upload_year_to_drive_returns_false_when_no_file(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    uploader = StubUploader()

    result = repo.upload_year_to_drive(2099, uploader)

    assert result is False
    assert uploader.uploaded_files == []


def test_list_events_reads_every_year_file_for_db_completeness_audit(tmp_path):
    repo = SqliteReportStorageAdapter(base_dir=str(tmp_path / "db"), period_type="WEEKLY")
    first = _make_event(event_id="2025-W52")
    first.year = 2025
    first.week = 52
    first.last_trading_day = date(2025, 12, 26)
    second = _make_event(event_id="2026-W01")

    repo.save(first)
    repo.save(second)

    events = repo.list_events()

    assert [event.id for event in events] == ["2025-W52", "2026-W01"]
    assert all(event.items for event in events)
    assert not (tmp_path / "db" / "weekly" / "meta.db").exists()
