from datetime import datetime, date
from typing import List, Set, Optional, Tuple
import pandas as pd
import pytest

from domain.ports import CalendarPort, StockDataPort, ReportStoragePort, CloudUploadPort
from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from application.services.weekly_gainer_service import WeeklyGainerService

# -------------------------------------------------------------
# 1. 포트를 상속한 테스트용 Stub 클래스 정의
# -------------------------------------------------------------

class StubCalendar(CalendarPort):
    def get_week_dates(self, year: int, week: int) -> Tuple[date, date]:
        return date(2026, 6, 22), date(2026, 6, 26)

    def get_last_trading_day(self, target_date: date) -> date:
        return date(2026, 6, 26)

    def get_first_trading_day(self, target_date: date) -> date:
        return date(2026, 6, 22)


class StubStockData(StockDataPort):
    def fetch_period_data(self, start_date: date, end_date: date) -> List[WeeklyGainerItem]:
        return [
            WeeklyGainerItem(
                symbol_code="005930",
                symbol_name="삼성전자",
                start_date=start_date,
                base_price=70000.0,
                end_date=end_date,
                close_price=85000.0,
                change=15000.0,
                change_rate=21.43,
                volume=100000,
                amount=8500000000
            )
        ]

    def fetch_index_components(self, index_code: str, target_date: date) -> Set[str]:
        return {"005930"}


class StubRepository(ReportStoragePort):
    def __init__(self):
        self.saved_event = None

    def save(self, event: WeeklyCollectionEvent) -> None:
        self.saved_event = event

    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        return None

    def exists(self, event_id: str) -> bool:
        return False


class StubUploader(CloudUploadPort):
    def __init__(self):
        self.uploaded_files = []

    def upload_excel(self, dfs: dict[str, pd.DataFrame], remote_path: str, filename: str) -> bool:
        self.uploaded_files.append((filename, remote_path, dfs))
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        self.uploaded_files.append((filename, remote_path, local_path))
        return True



# -------------------------------------------------------------
# 2. 테스트 케이스 선언 (의존성 주입 검증)
# -------------------------------------------------------------

def test_service_execution_with_injected_ports():
    """WeeklyGainerService가 구체 클래스가 아닌 포트에 의존하여 정상적으로 동작하는지 검증"""
    calendar = StubCalendar()
    stock_data = StubStockData()
    repository = StubRepository()
    uploader = StubUploader()

    # 의존성 주입하여 서비스 인스턴스 생성
    service = WeeklyGainerService(
        calendar=calendar,
        stock_data=stock_data,
        repository=repository,
        uploader=uploader
    )

    # 수집기 동작 실행 (2026년 26주차)
    success = service.collect_week(2026, 26, force=True, is_final=False)

    assert success is True
    # 리포지토리에 저장된 이벤트 확인
    assert repository.saved_event is not None
    assert repository.saved_event.id == "2026-W26"
    assert len(repository.saved_event.items) == 1
    assert repository.saved_event.items[0].symbol_name == "삼성전자"

    # 구글 드라이브 업로더 호출 기록 확인
    assert len(uploader.uploaded_files) == 1
    filename, remote_path, df = uploader.uploaded_files[0]
    assert "weekly_gainers_2026_W26" in filename
    assert isinstance(df, pd.DataFrame)
    # 컬럼이 한글로 rename 됨: '종목명'
    assert df.iloc[0]['종목명'] == "삼성전자"

