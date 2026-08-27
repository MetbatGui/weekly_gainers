from datetime import date, datetime
from typing import Optional, Set

from application.services.collection_orchestrator_service import CollectionOrchestratorService
from application.services.weekly_gainer_service import WeeklyGainerService
from domain.models import CollectionStatus, WeeklyCollectionEvent, WeeklyGainerItem
from domain.ports import CalendarPort, CloudUploadPort, StockDataPort
from infra.storage.sqlite_repository import SqliteReportStorageAdapter


class DeterministicCalendar(CalendarPort):
    def get_week_dates(self, year: int, week: int):
        monday = date.fromisocalendar(year, week, 1)
        return monday, date.fromisocalendar(year, week, 5)

    def get_last_trading_day(self, target_date: date) -> date:
        return target_date

    def get_first_trading_day(self, target_date: date) -> date:
        return target_date

    def is_holiday(self, target_date: date) -> bool:
        return False

    def get_trading_range_in_period(self, start_date: date, end_date: date):
        return start_date, end_date


class DeterministicStockData(StockDataPort):
    def fetch_period_data(self, start_date: date, end_date: date):
        return [
            WeeklyGainerItem(
                symbol_code="005930", symbol_name="삼성전자",
                start_date=start_date, base_price=100.0,
                end_date=end_date, close_price=130.0,
                change=30.0, change_rate=30.0, volume=1, amount=1,
            )
        ]

    def fetch_index_components(self, index_code: str, target_date: date) -> Set[str]:
        return set()


class SuccessfulUploader(CloudUploadPort):
    def upload_excel(self, file_content: bytes, remote_path: str, filename: str) -> bool:
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = "application/octet-stream") -> bool:
        return True

    def download_file(self, remote_path: str, filename: str) -> Optional[bytes]:
        return None


def test_daily_sync_repairs_missing_week_through_sqlite_service_path(tmp_path):
    base_dir = str(tmp_path / "db")
    weekly_repo = SqliteReportStorageAdapter(base_dir=base_dir, period_type="WEEKLY")
    monthly_repo = SqliteReportStorageAdapter(base_dir=base_dir, period_type="MONTHLY")
    weekly_repo.save(
        WeeklyCollectionEvent(
            id="2023-W01", year=2023, week=1,
            collected_at=datetime(2023, 1, 6), day_of_week="Friday",
            last_trading_day=date(2023, 1, 6),
            status=CollectionStatus.FINAL, total_count=1, fingerprint="005930:30.00",
        )
    )
    service = WeeklyGainerService(
        calendar=DeterministicCalendar(), stock_data=DeterministicStockData(),
        repository=weekly_repo, repository_monthly=monthly_repo,
        uploader=SuccessfulUploader(),
    )

    CollectionOrchestratorService(service).run_daily_sync(
        today=date(2023, 1, 20), coverage_start=date(2023, 1, 1)
    )

    repaired = weekly_repo.get_by_id("2023-W02")
    assert repaired is not None
    assert repaired.status == CollectionStatus.FINAL
    assert repaired.total_count == 1
