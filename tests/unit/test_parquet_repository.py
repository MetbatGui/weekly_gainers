import pytest
import shutil
from datetime import datetime, date
from pathlib import Path

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from infra.storage.parquet_repository import ParquetWeeklyGainerRepository

@pytest.fixture
def test_repo(tmp_path):
    """테스트용 임시 경로를 사용하는 레포지토리 피스처"""
    repo = ParquetWeeklyGainerRepository(base_path=str(tmp_path))
    return repo

def test_save_and_get_event(test_repo):
    # 1. 테스트 데이터 생성
    item = WeeklyGainerItem(
        symbol_code="005930",
        symbol_name="삼성전자",
        start_date=date(2026, 1, 2),
        base_price=70000.0,
        end_date=date(2026, 1, 9),
        close_price=75000.0,
        change=5000.0,
        change_rate=7.14,
        volume=1000000,
        amount=75000000000
    )
    
    event = WeeklyCollectionEvent(
        id="2026-W02",
        year=2026,
        week=2,
        collected_at=datetime(2026, 1, 9, 16, 0),
        day_of_week="Friday",
        last_trading_day=date(2026, 1, 9),
        status=CollectionStatus.COMPLETED,
        items=[item],
        total_count=2500
    )

    # 2. 저장
    test_repo.save(event)

    # 3. 조회 및 검증
    saved_event = test_repo.get_by_id("2026-W02")
    
    assert saved_event is not None
    assert saved_event.id == "2026-W02"
    assert saved_event.total_count == 2500
    assert len(saved_event.items) == 1
    assert saved_event.items[0].symbol_name == "삼성전자"
    assert saved_event.status == CollectionStatus.COMPLETED

def test_exists_logic(test_repo):
    event = WeeklyCollectionEvent(
        id="2026-W03",
        year=2026,
        week=3,
        collected_at=datetime.now(),
        day_of_week="Friday",
        last_trading_day=date(2026, 1, 16),
        status=CollectionStatus.COMPLETED
    )
    
    assert test_repo.exists("2026-W03") is False
    test_repo.save(event)
    assert test_repo.exists("2026-W03") is True

def test_list_all_events(test_repo):
    # 두 개의 이벤트 저장
    event1 = WeeklyCollectionEvent(
        id="2026-W01", year=2026, week=1,
        collected_at=datetime.now(), day_of_week="Friday",
        last_trading_day=date(2026, 1, 2), status=CollectionStatus.COMPLETED
    )
    event2 = WeeklyCollectionEvent(
        id="2026-W02", year=2026, week=2,
        collected_at=datetime.now(), day_of_week="Friday",
        last_trading_day=date(2026, 1, 9), status=CollectionStatus.COMPLETED
    )
    
    test_repo.save(event1)
    test_repo.save(event2)
    
    events = test_repo.list_all_events()
    assert len(events) == 2
    ids = [e.id for e in events]
    assert "2026-W01" in ids
    assert "2026-W02" in ids
