from datetime import date, datetime
from pathlib import Path
import pytest

from infra.storage.parquet_repository import ParquetWeeklyGainerRepository
from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus

def test_parquet_repository_lifecycle_integration(tmp_path):
    """임시 디렉토리(tmp_path)를 활용하여 ParquetWeeklyGainerRepository의 저장, 존재유무, 복원 로딩 통합 주기 검증"""
    # tmp_path를 저장소 base_path로 지정하여 실제 개발 데이터가 격리되도록 설정
    base_path = tmp_path / "data" / "weekly_gainers"
    repo = ParquetWeeklyGainerRepository(base_path=str(base_path))

    event_id = "2026-W26"
    items = [
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
            amount=8500000000
        )
    ]
    
    event = WeeklyCollectionEvent(
        id=event_id,
        year=2026,
        week=26,
        collected_at=datetime(2026, 6, 26, 15, 30),
        day_of_week="Friday",
        last_trading_day=date(2026, 6, 26),
        status=CollectionStatus.COMPLETED,
        items=items,
        fingerprint="dummy_fp_12345"
    )

    # 1. 존재하지 않는 이벤트 확인
    assert repo.exists(event_id) is False
    assert repo.get_by_id(event_id) is None

    # 2. 이벤트 저장
    repo.save(event)

    # 3. 파일 시스템 물리적 생성 확인
    # Milestone 1에서는 월별 격리가 아닌 연도별 폴더 구조: {base_path}/2026/
    partition_dir = base_path / "2026"
    assert partition_dir.exists() is True
    
    # Parquet 파일 존재 확인 (파일명: weekly_gainers_2026_W26_*.parquet)
    parquet_files = list(partition_dir.glob("weekly_gainers_2026_W26_*.parquet"))
    assert len(parquet_files) == 1
    
    # 매니페스트 파일 존재 확인
    manifest_file = base_path / "event_manifest.json"
    assert manifest_file.exists() is True

    # 4. 저장 후 존재여부 확인
    assert repo.exists(event_id) is True

    # 5. 저장 데이터 복원 로드 검증
    loaded_event = repo.get_by_id(event_id)
    assert loaded_event is not None
    assert loaded_event.id == event_id
    assert loaded_event.year == 2026
    assert loaded_event.week == 26
    assert loaded_event.status == CollectionStatus.COMPLETED
    assert loaded_event.fingerprint == "dummy_fp_12345"
    
    # 복원된 종목 아이템 데이터 검증
    assert len(loaded_event.items) == 1
    loaded_item = loaded_event.items[0]
    assert loaded_item.symbol_code == "005930"
    assert loaded_item.symbol_name == "삼성전자"
    assert loaded_item.base_price == 70000.0
    assert loaded_item.close_price == 85000.0
    assert loaded_item.change_rate == 21.43
    assert loaded_item.volume == 100000
    assert loaded_item.amount == 8500000000
