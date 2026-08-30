import logging
from datetime import date, timedelta
from typing import Optional

from application.services.weekly_gainer_service import WeeklyGainerService
from domain.collection_completeness import RequiredPeriod, find_required_periods

logger = logging.getLogger(__name__)

DEFAULT_COVERAGE_START = date(2020, 1, 1)


class CollectionOrchestratorService:
    """Keep collection data complete by auditing SQLite events, the system of record."""

    def __init__(
        self,
        gainer_service: WeeklyGainerService,
        failed_years: Optional[dict[str, set[int]]] = None,
    ):
        self.service = gainer_service
        # DbSyncSession이 이번 실행에서 다운로드에 실패한 연도 (db_ssot_guide.md §6.1).
        # 해당 연도는 로컬에 데이터가 없어 "전부 누락"으로 오판되기 쉬우므로, 완전성
        # 감사·수집·업로드 대상에서 전부 제외해 빈 DB로 원격을 덮어쓰는 사고를 막는다.
        self.failed_years = failed_years or {"WEEKLY": set(), "MONTHLY": set()}

    def run_daily_sync(
        self,
        today: Optional[date] = None,
        coverage_start: date = DEFAULT_COVERAGE_START,
    ) -> None:
        """Repair missing or incomplete DB periods, then refresh each current period."""
        today = today or date.today()
        logger.info(f"[Pipeline] DB 완전성 동기화 시작 (기준일: {today})")

        weekly_ok, weekly_years = self._sync_period("WEEKLY", coverage_start, today)
        monthly_ok, monthly_years = self._sync_period("MONTHLY", coverage_start, today)

        for year in sorted(weekly_years):
            self.service.sync_manifest("WEEKLY", year)
            weekly_ok = self.service.sync_db_to_drive("WEEKLY", year) and weekly_ok
        for year in sorted(monthly_years):
            self.service.sync_manifest("MONTHLY", year)
            monthly_ok = self.service.sync_db_to_drive("MONTHLY", year) and monthly_ok

        if not weekly_ok or not monthly_ok:
            logger.warning("[Pipeline] 일부 기간 또는 DB 동기화에 실패했습니다. 다음 실행에서 DB 감사가 재시도합니다.")
            return
        logger.info("[Pipeline] DB 완전성 동기화 완료!")

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

        failed_years = self.failed_years.get(period_type, set())
        if failed_years:
            skipped = sorted({period.event_id for period in required if period.year in failed_years})
            if skipped:
                logger.warning(
                    f"[Pipeline] {period_type}: DB 다운로드 실패한 연도 {sorted(failed_years)}의 "
                    f"기간 {len(skipped)}건 이번 실행에서 건너뜀: {skipped}"
                )
            required = [period for period in required if period.year not in failed_years]

        current = next((period for period in reversed(required) if not period.is_final), None)
        if current is None:
            current = self._current_period(period_type, today)
        if current.year in failed_years:
            logger.warning(
                f"[Pipeline] {period_type}: 현재 기간({current.event_id})의 연도가 DB 다운로드 "
                "실패 상태 - 이번 실행에서 건너뜀"
            )
            current = None

        # A valid current event still needs a daily refresh. Avoid adding it twice
        # when the audit already found it missing or incomplete.
        work = {period.event_id: period for period in required}
        if current is not None:
            work.setdefault(current.event_id, current)

        ok = True
        # Drive is a DB-derived replica. Upload every year that DB reports as
        # present so a previously failed historical upload is retried even when
        # no collection is needed for that year today.
        touched_years: set[int] = {event.year for event in events}
        for period in sorted(work.values(), key=lambda item: (item.start_date, item.event_id)):
            logger.info(f"--- {period_type}: DB 감사 수집({period.event_id}, final={period.is_final}, force={period.force}) ---")
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
