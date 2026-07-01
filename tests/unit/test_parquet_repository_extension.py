from datetime import date, datetime
from pathlib import Path
import pytest

from infra.storage.parquet_repository import ParquetWeeklyGainerRepository
from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus

def test_repository_partitioning_by_period_type(tmp_path):
    """주간(WEEKLY)과 월간(MONTHLY) 주기별로 매니페스트 파일 및 저장 디렉토리가 완벽히 물리적으로 격리되는지 검증"""
    base_path = tmp_path / "data"

    # 1. 주간 저장소 생성 및 데이터 저장
    weekly_repo = ParquetWeeklyGainerRepository(base_path=str(base_path), period_type="WEEKLY")
    weekly_event = WeeklyCollectionEvent(
        id="2026-W26", year=2026, week=26,
        collected_at=datetime.now(), day_of_week="Friday",
        last_trading_day=date(2026, 6, 26), status=CollectionStatus.COMPLETED
    )
    weekly_repo.save(weekly_event)

    # 2. 월간 저장소 생성 및 데이터 저장 (주간과 같은 base_path 공유)
    monthly_repo = ParquetWeeklyGainerRepository(base_path=str(base_path), period_type="MONTHLY")
    monthly_event = WeeklyCollectionEvent(
        id="2026-M06", year=2026, week=0, # 월간 수집은 week를 0으로
        collected_at=datetime.now(), day_of_week="Friday",
        last_trading_day=date(2026, 6, 26), status=CollectionStatus.COMPLETED
    )
    monthly_repo.save(monthly_event)

    # 3. 물리 파일 격리 검증
    # 주간 매니페스트 파일 생성 여부 확인
    weekly_manifest = base_path / "weekly_event_manifest.json"
    assert weekly_manifest.exists() is True
    
    # 월간 매니페스트 파일 생성 여부 확인
    monthly_manifest = base_path / "monthly_event_manifest.json"
    assert monthly_manifest.exists() is True

    # 4. 상호 간의 데이터 독립 격리 검증
    # 주간 저장소에는 월간 수집 이벤트가 존재하지 않아야 함
    assert weekly_repo.exists("2026-M06") is False
    assert weekly_repo.get_by_id("2026-M06") is None

    # 월간 저장소에는 주간 수집 이벤트가 존재하지 않아야 함
    assert monthly_repo.exists("2026-W26") is False
    assert monthly_repo.get_by_id("2026-W26") is None

    # 각자 자신의 이벤트만 소유함 확인
    assert weekly_repo.exists("2026-W26") is True
    assert monthly_repo.exists("2026-M06") is True

def test_repository_backward_compatibility(tmp_path):
    """period_type 파라미터가 생략된 경우 (하위 호환성 모드), 기존의 event_manifest.json 매니페스트가 사용되는지 검증"""
    base_path = tmp_path / "data"

    # period_type 생략 생성 (하위 호환 모드)
    legacy_repo = ParquetWeeklyGainerRepository(base_path=str(base_path))
    
    legacy_event = WeeklyCollectionEvent(
        id="2026-W01", year=2026, week=1,
        collected_at=datetime.now(), day_of_week="Friday",
        last_trading_day=date(2026, 1, 2), status=CollectionStatus.COMPLETED
    )
    legacy_repo.save(legacy_event)

    # 물리 파일이 기존의 event_manifest.json 명칭으로 생겼는지 확인
    legacy_manifest = base_path / "event_manifest.json"
    assert legacy_manifest.exists() is True
    
    # 기존 이름의 매니페스트가 아닌 weekly/monthly_event_manifest.json은 생성되지 않았어야 함
    assert (base_path / "weekly_event_manifest.json").exists() is False
    assert (base_path / "monthly_event_manifest.json").exists() is False

    # 정상 복원 확인
    assert legacy_repo.exists("2026-W01") is True
    loaded = legacy_repo.get_by_id("2026-W01")
    assert loaded is not None
    assert loaded.id == "2026-W01"
