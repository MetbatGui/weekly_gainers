from datetime import date
from typing import List, Optional, Set, Tuple

from domain.ports import CalendarPort, StockDataPort, ReportStoragePort, CloudUploadPort
from domain.models import WeeklyCollectionEvent, WeeklyGainerItem
from application.services.weekly_gainer_service import WeeklyGainerService


class StubCalendar(CalendarPort):
    def get_week_dates(self, year, week):
        return date(2026, 1, 1), date(2026, 1, 1)

    def get_last_trading_day(self, target_date):
        return target_date

    def get_first_trading_day(self, target_date):
        return target_date

    def is_holiday(self, target_date):
        return False

    def get_trading_range_in_period(self, start_date, end_date):
        return start_date, end_date


class StubStockData(StockDataPort):
    def fetch_period_data(self, start_date, end_date) -> List[WeeklyGainerItem]:
        return []

    def fetch_index_components(self, index_code, target_date) -> Set[str]:
        return set()


class RepoWithoutDriveSync(ReportStoragePort):
    def save(self, event) -> None:
        pass

    def get_by_id(self, event_id):
        return None

    def exists(self, event_id) -> bool:
        return False

    def list_events(self) -> List[WeeklyCollectionEvent]:
        return []


class RepoWithDriveSync(RepoWithoutDriveSync):
    def __init__(self):
        self.upload_calls = []

    def upload_year_to_drive(self, year: int, uploader: CloudUploadPort) -> bool:
        self.upload_calls.append((year, uploader))
        return True


class StubUploader(CloudUploadPort):
    def upload_excel(self, file_content, remote_path, filename) -> bool:
        return True

    def upload_file(self, local_path, remote_path, filename, mimetype='application/octet-stream') -> bool:
        return True

    def download_file(self, remote_path, filename) -> Optional[bytes]:
        return None


def _build_service(repo, repo_monthly=None):
    return WeeklyGainerService(
        calendar=StubCalendar(),
        stock_data=StubStockData(),
        repository=repo,
        uploader=StubUploader(),
        repository_monthly=repo_monthly or repo,
    )


def test_sync_db_to_drive_delegates_to_weekly_repo():
    weekly_repo = RepoWithDriveSync()
    service = _build_service(weekly_repo, RepoWithDriveSync())

    result = service.sync_db_to_drive("WEEKLY", 2026)

    assert result is True
    assert weekly_repo.upload_calls == [(2026, service.gdrive)]


def test_sync_db_to_drive_delegates_to_monthly_repo():
    weekly_repo = RepoWithDriveSync()
    monthly_repo = RepoWithDriveSync()
    service = _build_service(weekly_repo, monthly_repo)

    result = service.sync_db_to_drive("MONTHLY", 2026)

    assert result is True
    assert monthly_repo.upload_calls == [(2026, service.gdrive)]
    assert weekly_repo.upload_calls == []


def test_sync_db_to_drive_no_ops_when_repo_lacks_drive_sync():
    """upload_year_to_drive를 지원하지 않는 저장소(GDrive 매니페스트 어댑터 등)면 조용히 스킵한다."""
    service = _build_service(RepoWithoutDriveSync())

    result = service.sync_db_to_drive("WEEKLY", 2026)

    assert result is False
