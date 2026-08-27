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

    def _repo_for(self, period_type: str) -> ReportStoragePort:
        return self.repo if period_type.upper() == "WEEKLY" else self.repo_monthly

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
        repo = self._repo_for(period_type)
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

        # 4. 지문 생성 및 비교 (무결성 체크) - 변화 없으면 지수 구성종목 조회 없이 조기 종료
        filter_all = GainerFilter(None, None, threshold=20.0)
        items_all = filter_all.filter(all_items)
        items_all.sort(key=lambda x: x.change_rate, reverse=True)
        new_fingerprint = self._generate_fingerprint(items_all)

        if not force and existing and existing.fingerprint == new_fingerprint:
            print(f"[Service] {event_id} 데이터 변화 없음 (휴장일 혹은 업데이트 전). 건너뜁니다.")
            if is_final and existing.status != CollectionStatus.FINAL:
                existing.status = CollectionStatus.FINAL
                repo.save(existing)
            return True

        # 5. 시작일과 마지막일의 지수구성종목 수집 및 합집합 풀 구성
        try:
            # KOSPI 200 구성종목 합집합 (시작일 또는 종료일 기준 소속 시 포함)
            start_k200 = self.krx.fetch_index_components("KOSPI_200", trading_start)
            end_k200 = self.krx.fetch_index_components("KOSPI_200", trading_end)
            k200_pool = start_k200 | end_k200

            # KOSDAQ 150 구성종목 합집합 (시작일 또는 종료일 기준 소속 시 포함)
            start_k150 = self.krx.fetch_index_components("KOSDAQ_150", trading_start)
            end_k150 = self.krx.fetch_index_components("KOSDAQ_150", trading_end)
            k150_pool = start_k150 | end_k150
        except Exception as e:
            print(f"[Service] 지수 구성종목 수집 중 에러 발생 (건너뛰거나 빈 리스트로 처리): {e}")
            k200_pool = set()
            k150_pool = set()

        # 6. 전체 종목에 지수 소속 플래그 설정 (DB에 영속화되어 K200/K150 시트를 조회 시점에 재구성 가능)
        for item in items_all:
            item.in_kospi200 = item.symbol_code in k200_pool
            item.in_kosdaq150 = item.symbol_code in k150_pool

        items_k200 = [item for item in items_all if item.in_kospi200]
        items_k150 = [item for item in items_all if item.in_kosdaq150]

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
            start_md = start_target.strftime('%m%d')
            end_md = end_target.strftime('%m%d')
            if period_type == "WEEKLY":
                remote_path = f"{year}/{event.month:02d}월"
                filename = f"weekly_gainers_{year}_W{period_value:02d}_{event.month:02d}M{event.week_of_month}W_{start_md}~{end_md}.xlsx"
            else:
                remote_path = f"{year}/{period_value:02d}월"
                filename = f"monthly_gainers_{year}_M{period_value:02d}_{start_md}~{end_md}.xlsx"

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

    def sync_manifest(self, period_type: str, year: int):
        """저장소가 매니페스트 파일을 쓰는 구현체(Parquet 등)인 경우 구글 드라이브로 동기화."""
        repo = self._repo_for(period_type)
        if not hasattr(repo, "_get_manifest_path"):
            return
        manifest_file = repo._get_manifest_path(year)
        if manifest_file.exists():
            print(f"--- 매니페스트({manifest_file.name}) 구글 드라이브 동기화 ---")
            self.gdrive.upload_file(
                local_path=str(manifest_file),
                remote_path=str(year),
                filename=manifest_file.name,
                mimetype="application/json"
            )

    def sync_db_to_drive(self, period_type: str, year: int) -> bool:
        """저장소가 SQLite DB 파일 기반(SqliteReportStorageAdapter)인 경우 해당 연도 DB를 구글 드라이브로 업로드."""
        repo = self._repo_for(period_type)
        if not hasattr(repo, "upload_year_to_drive"):
            return False
        return repo.upload_year_to_drive(year, self.gdrive)

    def list_events(self, period_type: str) -> List[WeeklyCollectionEvent]:
        """Return the stored events used as the daily pipeline's sole coverage input."""
        return self._repo_for(period_type).list_events()

    def backfill_year(self, year: int, period_type: str = "WEEKLY", force: bool = False):
        """특정 연도의 모든 주차/월을 순회하며 누락된 데이터를 수집합니다.

        force=True를 주면 지문이 동일해도 재수집하여 items를 최신 스키마(예: 지수 소속 플래그)로 갱신합니다.
        """
        period_type = period_type.upper()
        print(f"\n=== {year}년 {period_type} 데이터 Backfill 시작 ===")

        today = date.today()

        if period_type == "WEEKLY":
            current_year, current_week, _ = today.isocalendar()
            last_week = 53 if year < current_year else current_week
            for w in range(1, last_week + 1):
                try:
                    is_final = not (year == current_year and w == current_week)
                    self.collect_week(year, w, force=force, is_final=is_final)
                except Exception as e:
                    print(f"[Service] {year}-W{w} 수집 중 오류 발생: {e}")
                    continue
        else:  # MONTHLY
            last_month = 12 if year < today.year else today.month
            for m in range(1, last_month + 1):
                try:
                    is_final = not (year == today.year and m == today.month)
                    self.collect_month(year, m, force=force, is_final=is_final)
                except Exception as e:
                    print(f"[Service] {year}-{m:02d}월 수집 중 오류 발생: {e}")
                    continue

        print(f"=== {year}년 {period_type} Backfill 완료 ===\n")
