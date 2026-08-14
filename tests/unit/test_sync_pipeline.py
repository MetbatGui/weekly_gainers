from datetime import date, timedelta
from typing import List, Optional, Set, Tuple
from unittest.mock import patch

from domain.ports import CalendarPort, StockDataPort, ReportStoragePort, CloudUploadPort
from domain.models import WeeklyCollectionEvent, WeeklyGainerItem
from application.services.weekly_gainer_service import WeeklyGainerService


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


def _build_service():
    return WeeklyGainerService(
        calendar=StubCalendar(),
        stock_data=StubStockData(),
        repository=StubRepository(),
        uploader=StubUploader(),
        repository_monthly=StubRepository(),
    )


def test_sync_pipeline_runs_weekly_and_monthly_in_a_single_call():
    """sync_pipeline()이 period_type 인자 없이 주간+월간을 한 번에 동기화한다."""
    service = _build_service()

    today = date.today()
    current_year, current_week, _ = today.isocalendar()
    prev_year, prev_week, _ = (today - timedelta(weeks=1)).isocalendar()

    current_month = today.month
    current_month_year = today.year
    if current_month == 1:
        prev_month_year, prev_month = current_month_year - 1, 12
    else:
        prev_month_year, prev_month = current_month_year, current_month - 1

    with patch.object(service, "collect_week", return_value=True) as mock_week, \
         patch.object(service, "collect_month", return_value=True) as mock_month:
        service.sync_pipeline()

    mock_week.assert_any_call(prev_year, prev_week, is_final=True)
    mock_week.assert_any_call(current_year, current_week, is_final=False)
    assert mock_week.call_count == 2

    mock_month.assert_any_call(prev_month_year, prev_month, is_final=True)
    mock_month.assert_any_call(current_month_year, current_month, is_final=False)
    assert mock_month.call_count == 2
