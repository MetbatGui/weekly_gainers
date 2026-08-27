from datetime import date, datetime

from application.services.collection_orchestrator_service import CollectionOrchestratorService
from domain.models import CollectionStatus, WeeklyCollectionEvent


def weekly_event(event_id: str, week: int, last_day: date, *, status=CollectionStatus.FINAL, total_count=100):
    return WeeklyCollectionEvent(
        id=event_id,
        year=last_day.isocalendar().year,
        week=week,
        collected_at=datetime(2026, 1, 1),
        day_of_week="Thursday",
        last_trading_day=last_day,
        status=status,
        total_count=total_count,
    )


class SpyService:
    def __init__(self, weekly_events=None, monthly_events=None):
        self.events = {"WEEKLY": weekly_events or [], "MONTHLY": monthly_events or []}
        self.week_calls = []
        self.month_calls = []
        self.sync_calls = []

    def list_events(self, period_type):
        return self.events[period_type]

    def collect_week(self, year, week, force=False, is_final=False):
        self.week_calls.append((year, week, force, is_final))
        return True

    def collect_month(self, year, month, force=False, is_final=False):
        self.month_calls.append((year, month, force, is_final))
        return True

    def sync_manifest(self, period_type, year):
        self.sync_calls.append(("manifest", period_type, year))

    def sync_db_to_drive(self, period_type, year):
        self.sync_calls.append(("db", period_type, year))
        return True


class RetryingDriveSpyService(SpyService):
    def __init__(self, *args, failed_uploads=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed_uploads = set(failed_uploads or [])

    def sync_db_to_drive(self, period_type, year):
        self.sync_calls.append(("db", period_type, year))
        key = (period_type, year)
        if key in self.failed_uploads:
            self.failed_uploads.remove(key)
            return False
        return True


def test_daily_sync_repairs_interior_gap_from_db_without_last_sync_date():
    service = SpyService(
        weekly_events=[
            weekly_event("2023-W01", 1, date(2023, 1, 6)),
            weekly_event("2023-W03", 3, date(2023, 1, 20), status=CollectionStatus.COMPLETED),
        ]
    )

    CollectionOrchestratorService(service).run_daily_sync(
        today=date(2023, 1, 20), coverage_start=date(2023, 1, 1)
    )

    assert service.week_calls == [
        (2023, 2, False, True),
        (2023, 3, False, False),
    ]


def test_daily_sync_repairs_unknown_market_total_with_force():
    service = SpyService(
        weekly_events=[weekly_event("2023-W01", 1, date(2023, 1, 6), total_count=0)]
    )

    CollectionOrchestratorService(service).run_daily_sync(
        today=date(2023, 1, 13), coverage_start=date(2023, 1, 2)
    )

    assert service.week_calls == [
        (2023, 1, True, True),
        (2023, 2, False, False),
    ]


def test_daily_sync_handles_december_monday_as_next_year_week_one():
    service = SpyService()

    CollectionOrchestratorService(service).run_daily_sync(
        today=date(2025, 1, 3), coverage_start=date(2024, 12, 30)
    )

    assert service.week_calls == [(2025, 1, False, False)]


def test_daily_sync_retries_drive_upload_for_existing_historical_db_year():
    service = RetryingDriveSpyService(
        weekly_events=[
            weekly_event("2023-W52", 52, date(2023, 12, 29)),
            weekly_event("2024-W01", 1, date(2024, 1, 5), status=CollectionStatus.COMPLETED),
        ],
        failed_uploads={("WEEKLY", 2023)},
    )
    orchestrator = CollectionOrchestratorService(service)

    orchestrator.run_daily_sync(today=date(2024, 1, 5), coverage_start=date(2024, 1, 1))
    orchestrator.run_daily_sync(today=date(2024, 1, 5), coverage_start=date(2024, 1, 1))

    weekly_db_syncs = [call for call in service.sync_calls if call[0] == "db" and call[1] == "WEEKLY"]
    assert weekly_db_syncs == [
        ("db", "WEEKLY", 2023),
        ("db", "WEEKLY", 2024),
        ("db", "WEEKLY", 2023),
        ("db", "WEEKLY", 2024),
    ]
