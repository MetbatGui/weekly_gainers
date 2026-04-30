from datetime import datetime, date
import pandas as pd
from typing import List, Optional

from domain.models import WeeklyCollectionEvent, CollectionStatus
from application.services.calendar_service import CalendarService
from infra.adapters.krx_adapter import KrxStockDataAdapter
from infra.storage.parquet_repository import ParquetWeeklyGainerRepository
from infra.storage.google_drive_adapter import GoogleDriveAdapter

class WeeklyGainerService:
    """주간 등락 종목 수집 및 리포트 생성을 총괄하는 서비스."""

    def __init__(
        self,
        calendar_service: CalendarService,
        krx_adapter: KrxStockDataAdapter,
        repository: ParquetWeeklyGainerRepository,
        gdrive_adapter: GoogleDriveAdapter
    ):
        self.calendar = calendar_service
        self.krx = krx_adapter
        self.repo = repository
        self.gdrive = gdrive_adapter

    def collect_week(self, year: int, week: int, force: bool = False) -> bool:
        """특정 주차의 데이터를 수집하고 저장 및 업로드합니다."""
        event_id = f"{year}-W{week:02d}"
        
        # 1. 이미 수집되었는지 확인 (강제 수집 모드가 아닐 때)
        if not force:
            existing = self.repo.get_by_id(event_id)
            if existing and existing.status == CollectionStatus.COMPLETED:
                print(f"[Service] {event_id}는 이미 수집 완료되었습니다. 건너뜁니다.")
                return True

        print(f"\n[Service] {event_id} 수집 시작...")

        # 2. 수집 기간 계산
        monday, friday = self.calendar.get_week_dates(year, week)
        start_date = self.calendar.get_first_trading_day(monday)
        end_date = self.calendar.get_last_trading_day(friday)

        # 3. 데이터 수집 (KRX 어댑터)
        all_items = self.krx.fetch_weekly_data(start_date, end_date)
        if not all_items:
            print(f"[Service] {event_id} 데이터 수집 실패")
            return False

        # 4. 필터링 (등락률 20% 이상) 및 이벤트 생성
        gainer_items = [item for item in all_items if item.change_rate >= 20.0]
        
        event = WeeklyCollectionEvent(
            id=event_id,
            year=year,
            week=week,
            collected_at=datetime.now(),
            day_of_week=datetime.now().strftime("%A"),
            last_trading_day=end_date,
            status=CollectionStatus.COMPLETED,
            items=gainer_items,
            total_count=len(all_items)
        )

        # 5. 로컬 저장 (Parquet)
        self.repo.save(event)
        print(f"[Service] 로컬 저장 완료 ({len(gainer_items)}개 종목)")

        # 6. 구글 드라이브 업로드 (Excel)
        if gainer_items:
            df = pd.DataFrame([item.__dict__ for item in gainer_items])
            # 리포트용 파일명 및 경로 설정
            remote_path = f"{year}/{event.month:02d}월"
            # 레포지토리에서 생성된 상세 파일명 규칙 활용 (또는 새로 생성)
            filename = f"weekly_gainers_{year}_W{week:02d}_{event.month:02d}M{event.week_of_month}W_{start_date.strftime('%m%d')}~{end_date.strftime('%m%d')}.xlsx"
            
            success = self.gdrive.upload_excel(df, remote_path, filename)
            if success:
                print(f"[Service] 구글 드라이브 업로드 완료")

        return True

    def backfill_year(self, year: int):
        """특정 연도의 모든 주차를 순회하며 누락된 데이터를 수집합니다."""
        print(f"\n=== {year}년 데이터 Backfill 시작 ===")
        
        # 현재 날짜 기준으로 수집 가능한 마지막 주차 계산
        current_year, current_week, _ = date.today().isocalendar()
        
        last_week = 53 if year < current_year else current_week
        
        for w in range(1, last_week + 1):
            try:
                self.collect_week(year, w)
            except Exception as e:
                print(f"[Service] {year}-W{w} 수집 중 오류 발생: {e}")
                continue
                
        print(f"=== {year}년 Backfill 완료 ===\n")
