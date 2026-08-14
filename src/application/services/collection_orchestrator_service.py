from datetime import date, timedelta
from typing import Optional

from application.services.weekly_gainer_service import WeeklyGainerService


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

        print(f"--- 주간: 지난주({prev_year}-W{prev_week:02d}) 최종 확정 시도 ---")
        self.service.collect_week(prev_year, prev_week, is_final=True)

        print(f"--- 주간: 이번 주({current_year}-W{current_week:02d}) 실시간 업데이트 시도 ---")
        self.service.collect_week(current_year, current_week, is_final=False)

        self.service.sync_manifest("WEEKLY", current_year)
        self.service.sync_db_to_drive("WEEKLY", current_year)
        if prev_year != current_year:
            # 연도 경계(1월 초)에서 방금 FINAL 확정된 지난해 마지막 주도 동기화
            self.service.sync_manifest("WEEKLY", prev_year)
            self.service.sync_db_to_drive("WEEKLY", prev_year)

        current_month_year, current_month = today.year, today.month
        if current_month == 1:
            prev_month_year, prev_month = current_month_year - 1, 12
        else:
            prev_month_year, prev_month = current_month_year, current_month - 1

        print(f"--- 월간: 지난달({prev_month_year}-{prev_month:02d}월) 최종 확정 시도 ---")
        self.service.collect_month(prev_month_year, prev_month, is_final=True)

        print(f"--- 월간: 이번 달({current_month_year}-{current_month:02d}월) 실시간 업데이트 시도 ---")
        self.service.collect_month(current_month_year, current_month, is_final=False)

        self.service.sync_manifest("MONTHLY", current_month_year)
        self.service.sync_db_to_drive("MONTHLY", current_month_year)
        if prev_month_year != current_month_year:
            # 연도 경계(1월)에서 방금 FINAL 확정된 지난해 12월도 동기화
            self.service.sync_manifest("MONTHLY", prev_month_year)
            self.service.sync_db_to_drive("MONTHLY", prev_month_year)

        print(f"[Pipeline] 모든 동기화 작업 완료!\n")
