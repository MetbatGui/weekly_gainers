from datetime import date, timedelta
from typing import Callable, List, Optional, Tuple

from application.services.weekly_gainer_service import WeeklyGainerService

Period = Tuple[int, int]


def compute_gap_periods(
    last_sync: Optional[date],
    today: date,
    period_of: Callable[[date], Period],
    prev_period: Period,
    current_period: Period,
    step: Callable[[Period], Period],
    min_days_back: int = 7,
) -> List[Period]:
    """last_sync~today 공백이 min_days_back일을 넘으면, 표준 처리 범위(prev_period,
    current_period)보다 앞선 기간들을 목록으로 반환한다. 공백이 없거나 last_sync 기록이
    없으면 빈 목록. prev_period/current_period는 항상 결과에서 제외된다(표준 흐름이 처리)."""
    if last_sync is None:
        return []
    gap_days = (today - last_sync).days - 1
    if gap_days <= min_days_back:
        return []

    boundary = {prev_period, current_period}
    periods: List[Tuple[int, int]] = []
    seen = set()
    cursor = period_of(last_sync)
    while cursor not in boundary and cursor <= current_period:
        if cursor not in seen:
            seen.add(cursor)
            periods.append(cursor)
        cursor = step(cursor)
    return periods


def compute_gap_weeks(
    last_sync: Optional[date],
    today: date,
    prev_period: Tuple[int, int],
    current_period: Tuple[int, int],
    min_days_back: int = 7,
) -> List[Tuple[int, int]]:
    def period_of(d: date) -> Tuple[int, int]:
        y, w, _ = d.isocalendar()
        return (y, w)

    def step(period: Tuple[int, int]) -> Tuple[int, int]:
        y, w = period
        return period_of(date.fromisocalendar(y, w, 1) + timedelta(weeks=1))

    return compute_gap_periods(last_sync, today, period_of, prev_period, current_period, step, min_days_back)


def compute_gap_months(
    last_sync: Optional[date],
    today: date,
    prev_period: Tuple[int, int],
    current_period: Tuple[int, int],
    min_days_back: int = 7,
) -> List[Tuple[int, int]]:
    def period_of(d: date) -> Tuple[int, int]:
        return (d.year, d.month)

    def step(period: Tuple[int, int]) -> Tuple[int, int]:
        y, m = period
        return (y + 1, 1) if m == 12 else (y, m + 1)

    return compute_gap_periods(last_sync, today, period_of, prev_period, current_period, step, min_days_back)


class CollectionOrchestratorService:
    """수집 호출 순서 조합(주간/월간 지난 기간 확정 + 이번 기간 갱신 + 매니페스트 동기화)을 전담하는 오케스트레이터."""

    def __init__(self, gainer_service: WeeklyGainerService):
        self.service = gainer_service

    def run_daily_sync(self, today: Optional[date] = None):
        """지난 기간 확정 + 이번 기간 업데이트를 주간/월간 모두에 대해 수행.

        Args:
            today: 기준일 (기본값 date.today(), 테스트용 주입 지점)
        """
        today = today or date.today()
        print(f"\n[Pipeline] 수집 동기화 시작 (기준일: {today})")

        current_year, current_week, _ = today.isocalendar()
        prev_year, prev_week, _ = (today - timedelta(weeks=1)).isocalendar()

        weekly_ok = True
        last_weekly_sync = self.service.get_last_sync_date("WEEKLY")
        gap_weeks = compute_gap_weeks(
            last_weekly_sync, today, (prev_year, prev_week), (current_year, current_week)
        )
        for gap_year, gap_week in gap_weeks:
            print(f"--- 주간: 갭 백필({gap_year}-W{gap_week:02d}) ---")
            weekly_ok = self.service.collect_week(gap_year, gap_week, is_final=True) and weekly_ok

        print(f"--- 주간: 지난주({prev_year}-W{prev_week:02d}) 최종 확정 시도 ---")
        weekly_ok = self.service.collect_week(prev_year, prev_week, is_final=True) and weekly_ok

        print(f"--- 주간: 이번 주({current_year}-W{current_week:02d}) 실시간 업데이트 시도 ---")
        weekly_ok = self.service.collect_week(current_year, current_week, is_final=False) and weekly_ok

        self.service.sync_manifest("WEEKLY", current_year)
        self.service.sync_db_to_drive("WEEKLY", current_year)
        if prev_year != current_year:
            # 연도 경계(1월 초)에서 방금 FINAL 확정된 지난해 마지막 주도 동기화
            self.service.sync_manifest("WEEKLY", prev_year)
            self.service.sync_db_to_drive("WEEKLY", prev_year)

        if weekly_ok:
            self.service.set_last_sync_date("WEEKLY", today)

        current_month_year, current_month = today.year, today.month
        if current_month == 1:
            prev_month_year, prev_month = current_month_year - 1, 12
        else:
            prev_month_year, prev_month = current_month_year, current_month - 1

        monthly_ok = True
        last_monthly_sync = self.service.get_last_sync_date("MONTHLY")
        gap_months = compute_gap_months(
            last_monthly_sync, today,
            (prev_month_year, prev_month), (current_month_year, current_month),
        )
        for gap_year, gap_month in gap_months:
            print(f"--- 월간: 갭 백필({gap_year}-{gap_month:02d}월) ---")
            monthly_ok = self.service.collect_month(gap_year, gap_month, is_final=True) and monthly_ok

        print(f"--- 월간: 지난달({prev_month_year}-{prev_month:02d}월) 최종 확정 시도 ---")
        monthly_ok = self.service.collect_month(prev_month_year, prev_month, is_final=True) and monthly_ok

        print(f"--- 월간: 이번 달({current_month_year}-{current_month:02d}월) 실시간 업데이트 시도 ---")
        monthly_ok = self.service.collect_month(current_month_year, current_month, is_final=False) and monthly_ok

        self.service.sync_manifest("MONTHLY", current_month_year)
        self.service.sync_db_to_drive("MONTHLY", current_month_year)
        if prev_month_year != current_month_year:
            # 연도 경계(1월)에서 방금 FINAL 확정된 지난해 12월도 동기화
            self.service.sync_manifest("MONTHLY", prev_month_year)
            self.service.sync_db_to_drive("MONTHLY", prev_month_year)

        if monthly_ok:
            self.service.set_last_sync_date("MONTHLY", today)

        print(f"[Pipeline] 모든 동기화 작업 완료!\n")
