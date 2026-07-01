from datetime import datetime, date, timedelta
import pandas as pd
from typing import List, Optional

from domain.models import WeeklyCollectionEvent, CollectionStatus, WeeklyGainerItem
from domain.ports import CalendarPort, StockDataPort, ReportStoragePort, CloudUploadPort

class WeeklyGainerService:
    """주간 등락 종목 수집 및 리포트 생성을 총괄하는 서비스."""

    def __init__(
        self,
        calendar: CalendarPort,
        stock_data: StockDataPort,
        repository: ReportStoragePort,
        uploader: CloudUploadPort
    ):
        self.calendar = calendar
        self.krx = stock_data
        self.repo = repository
        self.gdrive = uploader


    def _generate_fingerprint(self, items: List[WeeklyGainerItem]) -> str:
        """상위 5개 종목의 코드와 등락률로 고유 지문을 생성합니다."""
        top_items = sorted(items, key=lambda x: x.change_rate, reverse=True)[:5]
        return "|".join([f"{item.symbol_code}:{item.change_rate:.2f}" for item in top_items])

    def collect_week(self, year: int, week: int, force: bool = False, is_final: bool = False) -> bool:
        """특정 주차의 데이터를 수집하고 저장 및 업로드합니다.
        
        Args:
            year, week: 대상 주차
            force: 기존 데이터 존재 여부와 상관없이 수집 강행
            is_final: 이번 수집을 해당 주차의 '최종 확정'으로 처리할지 여부
        """
        # 1. 수집 대상 날짜 계산
        monday, friday = self.calendar.get_week_dates(year, week)
        iso_year, iso_week, _ = monday.isocalendar()
        event_id = f"{iso_year}-W{iso_week:02d}"
        
        # 2. 기존 상태 확인
        existing = self.repo.get_by_id(event_id)
        if not force and existing:
            if existing.status == CollectionStatus.FINAL:
                print(f"[Service] {event_id}는 이미 최종 확정(FINAL) 상태입니다. 건너뜁니다.")
                return True

        print(f"\n[Service] {event_id} 수집 시도... ({monday} ~ {friday})")

        start_date = self.calendar.get_first_trading_day(monday)
        # 만약 오늘이 포함된 주차라면 오늘까지, 아니라면 금요일까지
        today = date.today()
        if friday >= today:
            end_date = self.calendar.get_last_trading_day(today)
        else:
            end_date = self.calendar.get_last_trading_day(friday)

        # 3. 데이터 수집 (KRX 어댑터)
        all_items = self.krx.fetch_period_data(start_date, end_date)
        if not all_items:
            print(f"[Service] {event_id} 데이터 수집 실패")
            return False

        # 4. 필터링 및 지문 생성
        gainer_items = [item for item in all_items if item.change_rate >= 20.0]
        gainer_items.sort(key=lambda x: x.change_rate, reverse=True)
        new_fingerprint = self._generate_fingerprint(gainer_items)

        # 5. 지문 비교 (무결성 체크)
        if not force and existing and existing.fingerprint == new_fingerprint:
            print(f"[Service] {event_id} 데이터 변화 없음 (휴장일 혹은 업데이트 전). 건너뜁니다.")
            # 상태가 FINAL로 요청되었는데 기존이 COMPLETED였다면 상태만 업데이트
            if is_final and existing.status != CollectionStatus.FINAL:
                existing.status = CollectionStatus.FINAL
                self.repo.save(existing)
            return True

        # 6. 이벤트 객체 생성
        event = WeeklyCollectionEvent(
            id=event_id,
            year=iso_year,
            week=iso_week,
            collected_at=datetime.now(),
            day_of_week=datetime.now().strftime("%A"),
            last_trading_day=end_date,
            status=CollectionStatus.FINAL if is_final else CollectionStatus.COMPLETED,
            items=gainer_items,
            total_count=len(all_items),
            fingerprint=new_fingerprint
        )

        # 7. 로컬 저장 (Parquet)
        self.repo.save(event)
        print(f"[Service] 로컬 저장 완료 ({len(gainer_items)}개 종목, Status: {event.status.value})")

        # 8. 구글 드라이브 업로드 (Excel)
        if gainer_items:
            column_mapping = {
                'symbol_code': '종목코드', 'symbol_name': '종목명',
                'start_date': '시작일', 'base_price': '기준가',
                'end_date': '종료일', 'close_price': '종가',
                'change': '대비', 'change_rate': '등락률',
                'volume': '거래량', 'amount': '거래대금'
            }
            df = pd.DataFrame([item.__dict__ for item in gainer_items])
            df = df[list(column_mapping.keys())].rename(columns=column_mapping)
            
            # 리포트용 경로 설정
            remote_path = f"{iso_year}/{event.month:02d}월"
            
            # 파일명 결정: 진행 중이더라도 해당 주의 전체 기간(월~금)을 이름으로 사용 (덮어쓰기 유도)
            start_md = monday.strftime('%m%d')
            end_md = friday.strftime('%m%d')
            filename = f"weekly_gainers_{iso_year}_W{iso_week:02d}_{event.month:02d}M{event.week_of_month}W_{start_md}~{end_md}.xlsx"
            
            success = self.gdrive.upload_excel(df, remote_path, filename)
            if success:
                print(f"[Service] 구글 드라이브 업로드 완료 ({filename})")

        return True

    def sync_pipeline(self):
        """전체 수집 파이프라인 실행: 지난주 확정 + 이번 주 업데이트."""
        today = date.today()
        current_year, current_week, _ = today.isocalendar()
        
        print(f"\n[Pipeline] 주간 수집 동기화 시작 (기준일: {today})")

        # 1. 지난주 확정 (Monday-Friday 전체 데이터)
        last_week_date = today - timedelta(weeks=1)
        prev_year, prev_week, _ = last_week_date.isocalendar()
        
        print(f"--- 1단계: 지난주({prev_year}-W{prev_week:02d}) 최종 확정 시도 ---")
        self.collect_week(prev_year, prev_week, is_final=True)

        # 2. 이번 주 업데이트 (진행 중인 데이터)
        print(f"--- 2단계: 이번 주({current_year}-W{current_week:02d}) 실시간 업데이트 시도 ---")
        self.collect_week(current_year, current_week, is_final=False)

        # 3. 매니페스트 동기화 (다른 시스템과의 동기화용)
        print(f"--- 3단계: 매니페스트({self.repo.manifest_path.name}) 구글 드라이브 동기화 ---")
        self.gdrive.upload_file(
            local_path=str(self.repo.manifest_path),
            remote_path="",
            filename=self.repo.manifest_path.name,
            mimetype="application/json"
        )

        print(f"[Pipeline] 모든 동기화 작업 완료!\n")

    def backfill_year(self, year: int):
        """특정 연도의 모든 주차를 순회하며 누락된 데이터를 수집합니다."""
        print(f"\n=== {year}년 데이터 Backfill 시작 ===")
        
        # 현재 날짜 기준으로 수집 가능한 마지막 주차 계산
        current_year, current_week, _ = date.today().isocalendar()
        
        last_week = 53 if year < current_year else current_week
        
        for w in range(1, last_week + 1):
            try:
                # 이미 지난(끝난) 주차는 FINAL로 수집, 현재 진행중인 주차만 COMPLETED로 수집
                is_final = not (year == current_year and w == current_week)
                self.collect_week(year, w, is_final=is_final)
            except Exception as e:
                print(f"[Service] {year}-W{w} 수집 중 오류 발생: {e}")
                continue
                
        print(f"=== {year}년 Backfill 완료 ===\n")
