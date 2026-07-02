from datetime import datetime, date, timedelta
import pandas as pd
from typing import List, Optional, Dict, Set

from domain.models import WeeklyCollectionEvent, CollectionStatus, WeeklyGainerItem
from domain.ports import CalendarPort, StockDataPort, ReportStoragePort, CloudUploadPort
from domain.gainer_filter import GainerFilter
from application.services.excel_report_builder import ExcelReportBuilder

class WeeklyGainerService:
    """주간 및 월간 등락 종목 수집, 필터링 및 리포트 생성을 총괄하는 서비스."""

    def __init__(
        self,
        calendar: CalendarPort,
        stock_data: StockDataPort,
        repository: ReportStoragePort,
        uploader: CloudUploadPort,
        repository_monthly: Optional[ReportStoragePort] = None,
        excel_builder: Optional[ExcelReportBuilder] = None
    ):
        self.calendar = calendar
        self.krx = stock_data
        self.repo = repository  # 기본(주간) 레포지토리
        self.repo_monthly = repository_monthly or repository  # 월간 레포지토리 (없으면 기본 사용)
        self.gdrive = uploader
        self.excel_builder = excel_builder or ExcelReportBuilder()

    def _generate_fingerprint(self, items: List[WeeklyGainerItem]) -> str:
        """상위 5개 종목의 코드와 등락률로 고유 지문을 생성합니다."""
        top_items = sorted(items, key=lambda x: x.change_rate, reverse=True)[:5]
        return "|".join([f"{item.symbol_code}:{item.change_rate:.2f}" for item in top_items])

    def collect_period(
        self,
        period_type: str,
        year: int,
        period_value: int,
        force: bool = False,
        is_final: bool = False
    ) -> bool:
        """주간 또는 월간 등락 종목 데이터를 수집하여 필터링 후 로컬 및 클라우드에 업로드합니다.

        Args:
            period_type: "WEEKLY" 또는 "MONTHLY"
            year: 대상 연도
            period_value: 주간일 경우 week, 월간일 경우 month
            force: 기존 데이터 존재와 무관하게 수집 강행 여부
            is_final: 확정 데이터 처리 여부 (FINAL 상태 설정)
        """
        period_type = period_type.upper()
        if period_type not in ("WEEKLY", "MONTHLY"):
            raise ValueError(f"[Service] 지원하지 않는 수집 주기입니다: {period_type}")

        # 1. 대상 날짜 범위 결정
        if period_type == "WEEKLY":
            monday, friday = self.calendar.get_week_dates(year, period_value)
            iso_year, iso_week, _ = monday.isocalendar()
            event_id = f"{iso_year}-W{iso_week:02d}"
            start_target = monday
            end_target = friday
        else:  # MONTHLY
            start_target = date(year, period_value, 1)
            if period_value == 12:
                end_target = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_target = date(year, period_value + 1, 1) - timedelta(days=1)
            event_id = f"{year}-M{period_value:02d}"

        # 2. 기존 상태 확인
        repo = self.repo if period_type == "WEEKLY" else self.repo_monthly
        existing = repo.get_by_id(event_id)
        if not force and existing:
            if existing.status == CollectionStatus.FINAL:
                print(f"[Service] {event_id}는 이미 최종 확정(FINAL) 상태입니다. 건너뜁니다.")
                return True

        print(f"\n[Service] {event_id} ({period_type}) 수집 시도... ({start_target} ~ {end_target})")

        # 영업일 보정 및 수집 타겟 범위 계산
        today = date.today()
        # 진행 중인 기간의 경우 오늘까지만 수집하도록 제한
        real_end = today if end_target >= today else end_target
        trading_start, trading_end = self.calendar.get_trading_range_in_period(start_target, real_end)

        if not trading_start or not trading_end:
            print(f"[Service] {event_id} 기간 내 거래 영업일이 존재하지 않습니다. 건너뜁니다.")
            return True

        # 3. 데이터 수집 (KRX 어댑터)
        all_items = self.krx.fetch_period_data(trading_start, trading_end)
        if not all_items:
            print(f"[Service] {event_id} 데이터 수집 실패")
            return False

        # 4. 시작일과 마지막일의 지수구성종목 수집 및 합집합 필터 구성
        try:
            # KOSPI 200 구성종목 합집합 필터
            start_k200 = self.krx.fetch_index_components("KOSPI_200", trading_start)
            end_k200 = self.krx.fetch_index_components("KOSPI_200", trading_end)
            filter_k200 = GainerFilter(start_k200, end_k200, threshold=20.0)
            
            # KOSDAQ 150 구성종목 합집합 필터
            start_k150 = self.krx.fetch_index_components("KOSDAQ_150", trading_start)
            end_k150 = self.krx.fetch_index_components("KOSDAQ_150", trading_end)
            filter_k150 = GainerFilter(start_k150, end_k150, threshold=20.0)
        except Exception as e:
            print(f"[Service] 지수 구성종목 수집 중 에러 발생 (건너뛰거나 빈 리스트로 처리): {e}")
            filter_k200 = GainerFilter(set(), set(), threshold=20.0)
            filter_k150 = GainerFilter(set(), set(), threshold=20.0)

        filter_all = GainerFilter(None, None, threshold=20.0)

        # 5. 데이터 필터링
        items_all = filter_all.filter(all_items)
        items_all.sort(key=lambda x: x.change_rate, reverse=True)

        items_k200 = filter_k200.filter(all_items)
        items_k200.sort(key=lambda x: x.change_rate, reverse=True)

        items_k150 = filter_k150.filter(all_items)
        items_k150.sort(key=lambda x: x.change_rate, reverse=True)

        # 지문 생성 (전체 등락 기준)
        new_fingerprint = self._generate_fingerprint(items_all)

        # 6. 지문 비교 (무결성 체크)
        if not force and existing and existing.fingerprint == new_fingerprint:
            print(f"[Service] {event_id} 데이터 변화 없음 (휴장일 혹은 업데이트 전). 건너뜁니다.")
            if is_final and existing.status != CollectionStatus.FINAL:
                existing.status = CollectionStatus.FINAL
                repo.save(existing)
            return True

        # 7. 이벤트 객체 생성
        event = WeeklyCollectionEvent(
            id=event_id,
            year=year,
            week=period_value if period_type == "WEEKLY" else 0,
            collected_at=datetime.now(),
            day_of_week=datetime.now().strftime("%A"),
            last_trading_day=trading_end,
            status=CollectionStatus.FINAL if is_final else CollectionStatus.COMPLETED,
            items=items_all,
            total_count=len(all_items),
            fingerprint=new_fingerprint
        )
        if period_type == "MONTHLY":
            event.month = period_value
            event.week_of_month = 0

        # 8. 로컬 저장 (Parquet)
        repo.save(event)
        print(f"[Service] 로컬 저장 완료 ({len(items_all)}개 종목, Status: {event.status.value})")

        # 9. Excel 바이너리 작성 및 클라우드 업로드
        if items_all:
            column_mapping = {
                'symbol_code': '종목코드', 'symbol_name': '종목명',
                'start_date': '시작일', 'base_price': '기준가',
                'end_date': '종료일', 'close_price': '종가',
                'change': '대비', 'change_rate': '등락률',
                'volume': '거래량', 'amount': '거래대금'
            }

            def prepare_df(items):
                df = pd.DataFrame([item.__dict__ for item in items])
                if not df.empty:
                    df = df[list(column_mapping.keys())].rename(columns=column_mapping)
                else:
                    df = pd.DataFrame(columns=list(column_mapping.values()))
                return df

            sheets = {
                "전체_등락종목": prepare_df(items_all),
                "KOSPI_200": prepare_df(items_k200),
                "KOSDAQ_150": prepare_df(items_k150)
            }

            excel_data = self.excel_builder.build_report(sheets)

            # 경로 및 파일명 결정
            if period_type == "WEEKLY":
                remote_path = f"{year}/{event.month:02d}월"
                start_md = start_target.strftime('%m%d')
                end_md = end_target.strftime('%m%d')
                filename = f"weekly_gainers_{year}_W{period_value:02d}_{event.month:02d}M{event.week_of_month}W_{start_md}~{end_md}.xlsx"
            else:
                remote_path = f"{year}"
                filename = f"monthly_gainers_{year}_{period_value:02d}월.xlsx"

            success = self.gdrive.upload_excel(excel_data, remote_path, filename)
            if success:
                print(f"[Service] 구글 드라이브 업로드 완료 ({filename})")

        return True

    def collect_week(self, year: int, week: int, force: bool = False, is_final: bool = False) -> bool:
        """하위 호환용 주간 수집 메서드."""
        return self.collect_period("WEEKLY", year, week, force, is_final)

    def collect_month(self, year: int, month: int, force: bool = False, is_final: bool = False) -> bool:
        """월간 수집 메서드."""
        return self.collect_period("MONTHLY", year, month, force, is_final)

    def sync_pipeline(self, period_type: str = "WEEKLY"):
        """전체 수집 파이프라인 실행: 지난 기간 확정 + 이번 기간 업데이트."""
        today = date.today()
        period_type = period_type.upper()
        
        print(f"\n[Pipeline] {period_type} 수집 동기화 시작 (기준일: {today})")

        if period_type == "WEEKLY":
            current_year, current_week, _ = today.isocalendar()
            last_week_date = today - timedelta(weeks=1)
            prev_year, prev_week, _ = last_week_date.isocalendar()
            
            print(f"--- 1단계: 지난주({prev_year}-W{prev_week:02d}) 최종 확정 시도 ---")
            self.collect_week(prev_year, prev_week, is_final=True)

            print(f"--- 2단계: 이번 주({current_year}-W{current_week:02d}) 실시간 업데이트 시도 ---")
            self.collect_week(current_year, current_week, is_final=False)

            print(f"--- 3단계: 매니페스트({self.repo.manifest_path.name}) 구글 드라이브 동기화 ---")
            self.gdrive.upload_file(
                local_path=str(self.repo.manifest_path),
                remote_path="",
                filename=self.repo.manifest_path.name,
                mimetype="application/json"
            )
        else:  # MONTHLY
            current_year = today.year
            current_month = today.month
            
            if current_month == 1:
                prev_year = current_year - 1
                prev_month = 12
            else:
                prev_year = current_year
                prev_month = current_month - 1

            print(f"--- 1단계: 지난달({prev_year}-{prev_month:02d}월) 최종 확정 시도 ---")
            self.collect_month(prev_year, prev_month, is_final=True)

            print(f"--- 2단계: 이번 달({current_year}-{current_month:02d}월) 실시간 업데이트 시도 ---")
            self.collect_month(current_year, current_month, is_final=False)

            print(f"--- 3단계: 매니페스트({self.repo_monthly.manifest_path.name}) 구글 드라이브 동기화 ---")
            self.gdrive.upload_file(
                local_path=str(self.repo_monthly.manifest_path),
                remote_path="",
                filename=self.repo_monthly.manifest_path.name,
                mimetype="application/json"
            )

        print(f"[Pipeline] 모든 동기화 작업 완료!\n")

    def backfill_year(self, year: int, period_type: str = "WEEKLY"):
        """특정 연도의 모든 주차/월을 순회하며 누락된 데이터를 수집합니다."""
        period_type = period_type.upper()
        print(f"\n=== {year}년 {period_type} 데이터 Backfill 시작 ===")
        
        today = date.today()
        
        if period_type == "WEEKLY":
            current_year, current_week, _ = today.isocalendar()
            last_week = 53 if year < current_year else current_week
            for w in range(1, last_week + 1):
                try:
                    is_final = not (year == current_year and w == current_week)
                    self.collect_week(year, w, is_final=is_final)
                except Exception as e:
                    print(f"[Service] {year}-W{w} 수집 중 오류 발생: {e}")
                    continue
        else:  # MONTHLY
            last_month = 12 if year < today.year else today.month
            for m in range(1, last_month + 1):
                try:
                    is_final = not (year == today.year and m == today.month)
                    self.collect_month(year, m, is_final=is_final)
                except Exception as e:
                    print(f"[Service] {year}-{m:02d}월 수집 중 오류 발생: {e}")
                    continue
                    
        print(f"=== {year}년 {period_type} Backfill 완료 ===\n")
