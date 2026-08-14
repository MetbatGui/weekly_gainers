from datetime import date
from typing import List, Optional, Set, Tuple
from unittest.mock import patch

from domain.ports import CalendarPort, StockDataPort, ReportStoragePort, CloudUploadPort
from domain.models import WeeklyCollectionEvent, WeeklyGainerItem
from application.services.weekly_gainer_service import WeeklyGainerService
from application.services.collection_orchestrator_service import CollectionOrchestratorService


class StubCalendar(CalendarPort):
    def get_week_dates(self, year: int, week: int) -> Tuple[date, date]:
        return date(2026, 1, 1), date(2026, 1, 1)

    def get_last_trading_day(self, target_date: date) -> date:
        return target_date

    def get_first_trading_day(self, target_date: date) -> date:
        return target_date

    def is_holiday(self, target_date: date) -> bool:
        return False

    def get_trading_range_in_period(self, start_date: date, end_date: date) -> Tuple[Optional[date], Optional[date]]:
        return start_date, end_date


class StubStockData(StockDataPort):
    def fetch_period_data(self, start_date: date, end_date: date) -> List[WeeklyGainerItem]:
        return []

    def fetch_index_components(self, index_code: str, target_date: date) -> Set[str]:
        return set()


class StubRepository(ReportStoragePort):
    def save(self, event: WeeklyCollectionEvent) -> None:
        pass

    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        return None

    def exists(self, event_id: str) -> bool:
        return False


class StubUploader(CloudUploadPort):
    def upload_excel(self, file_content: bytes, remote_path: str, filename: str) -> bool:
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        return True

    def download_file(self, remote_path: str, filename: str) -> Optional[bytes]:
        return None


def _build_orchestrator():
    service = WeeklyGainerService(
        calendar=StubCalendar(),
        stock_data=StubStockData(),
        repository=StubRepository(),
        uploader=StubUploader(),
        repository_monthly=StubRepository(),
    )
    return service, CollectionOrchestratorService(service)


def test_run_daily_sync_calls_weekly_and_monthly_prev_and_current():
    """today를 주입해 결정론적으로 지난주/이번주, 지난달/이번달 호출 인자를 검증한다."""
    service, orchestrator = _build_orchestrator()
    injected_today = date(2026, 6, 25)  # 2026-W26, 목요일

    with patch.object(service, "collect_week", return_value=True) as mock_week, \
         patch.object(service, "collect_month", return_value=True) as mock_month:
        orchestrator.run_daily_sync(today=injected_today)

    mock_week.assert_any_call(2026, 25, is_final=True)
    mock_week.assert_any_call(2026, 26, is_final=False)
    assert mock_week.call_count == 2

    mock_month.assert_any_call(2026, 5, is_final=True)
    mock_month.assert_any_call(2026, 6, is_final=False)
    assert mock_month.call_count == 2


def test_run_daily_sync_january_boundary_rolls_back_to_prev_year_december():
    service, orchestrator = _build_orchestrator()
    injected_today = date(2026, 1, 8)  # 2026-W02

    with patch.object(service, "collect_week", return_value=True), \
         patch.object(service, "collect_month", return_value=True) as mock_month:
        orchestrator.run_daily_sync(today=injected_today)

    mock_month.assert_any_call(2025, 12, is_final=True)
    mock_month.assert_any_call(2026, 1, is_final=False)
