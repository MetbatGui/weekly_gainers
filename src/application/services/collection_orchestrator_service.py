from datetime import date, timedelta
from typing import Optional

from application.services.weekly_gainer_service import WeeklyGainerService
from domain.collection_completeness import RequiredPeriod, find_required_periods


DEFAULT_COVERAGE_START = date(2020, 1, 1)


class CollectionOrchestratorService:
    """Keep collection data complete by auditing SQLite events, the system of record."""

    def __init__(self, gainer_service: WeeklyGainerService):
        self.service = gainer_service

    def run_daily_sync(
        self,
        today: Optional[date] = None,
        coverage_start: date = DEFAULT_COVERAGE_START,
    ) -> None:
        """Repair missing or incomplete DB periods, then refresh each current period."""
        today = today or date.today()
        print(f"\n[Pipeline] DB 완전성 동기화 시작 (기준일: {today})")

        weekly_ok, weekly_years = self._sync_period("WEEKLY", coverage_start, today)
        monthly_ok, monthly_years = self._sync_period("MONTHLY", coverage_start, today)

        for year in sorted(weekly_years):
            self.service.sync_manifest("WEEKLY", year)
            weekly_ok = self.service.sync_db_to_drive("WEEKLY", year) and weekly_ok
        for year in sorted(monthly_years):
            self.service.sync_manifest("MONTHLY", year)
            monthly_ok = self.service.sync_db_to_drive("MONTHLY", year) and monthly_ok

        if not weekly_ok or not monthly_ok:
            print("[Pipeline] 일부 기간 또는 DB 동기화에 실패했습니다. 다음 실행에서 DB 감사가 재시도합니다.")
            return
        print("[Pipeline] DB 완전성 동기화 완료!\n")

    def _sync_period(
        self,
        period_type: str,
        coverage_start: date,
        today: date,
    ) -> tuple[bool, set[int]]:
        events = self.service.list_events(period_type)
        required = find_required_periods(
            events,
            period_type=period_type,
            coverage_start=coverage_start,
            today=today,
        )
        current = next((period for period in reversed(required) if not period.is_final), None)
        if current is None:
            current = self._current_period(period_type, today)

        # A valid current event still needs a daily refresh. Avoid adding it twice
        # when the audit already found it missing or incomplete.
        work = {period.event_id: period for period in required}
        work.setdefault(current.event_id, current)

        ok = True
        # Drive is a DB-derived replica. Upload every year that DB reports as
        # present so a previously failed historical upload is retried even when
        # no collection is needed for that year today.
        touched_years: set[int] = {event.year for event in events}
        for period in sorted(work.values(), key=lambda item: (item.start_date, item.event_id)):
            print(f"--- {period_type}: DB 감사 수집({period.event_id}, final={period.is_final}, force={period.force}) ---")
            if period_type == "WEEKLY":
                success = self.service.collect_week(
                    period.year, period.value, force=period.force, is_final=period.is_final
                )
            else:
                success = self.service.collect_month(
                    period.year, period.value, force=period.force, is_final=period.is_final
                )
            ok = success and ok
            if success:
                touched_years.add(period.year)
        return ok, touched_years

    @staticmethod
    def _current_period(period_type: str, today: date) -> RequiredPeriod:
        coverage_start = today - timedelta(days=today.weekday()) if period_type == "WEEKLY" else today.replace(day=1)
        return find_required_periods([], period_type=period_type, coverage_start=coverage_start, today=today)[0]
