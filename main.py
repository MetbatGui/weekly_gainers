import logging
import os
import sys
import argparse
from datetime import date
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# src 경로를 시스템 경로에 추가
sys.path.append(os.path.join(os.getcwd(), 'src'))

from application.services.calendar_service import CalendarService
from application.services.weekly_gainer_service import WeeklyGainerService
from application.services.collection_orchestrator_service import (
    CollectionOrchestratorService,
    DEFAULT_COVERAGE_START,
)
from infra.adapters.krx_adapter import KrxStockDataAdapter
from infra.storage.sqlite_repository import SqliteReportStorageAdapter
from infra.storage.google_drive_adapter import GoogleDriveAdapter
from infra.storage.db_sync_session import DbSyncSession

def main():
    # .env 로드
    load_dotenv()
    
    # CLI 인자 파서 정의
    parser = argparse.ArgumentParser(description="주간/월간 등락률 수집 배치 프로그램")
    parser.add_argument(
        "--period", "-p",
        choices=["weekly", "monthly"],
        default="weekly",
        help="수집 주기 선택 (weekly 또는 monthly, 기본값: weekly)"
    )
    parser.add_argument(
        "--action", "-a",
        choices=["sync", "collect", "backfill"],
        default="sync",
        help="실행 액션 (sync: 동기화 파이프라인, collect: 단일 수집, backfill: 연도 백필, 기본값: sync)"
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        help="대상 연도 (생략 시 오늘 기준 연도)"
    )
    parser.add_argument(
        "--value", "-v",
        type=int,
        help="수집 대상 주차(W) 혹은 월(M) 번호"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="기존 상태(FINAL)를 무시하고 강제 수집"
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="collect 시 해당 수집을 확정(FINAL) 상태로 처리"
    )
    parser.add_argument(
        "--skip-holiday-check",
        action="store_true",
        help="오늘이 휴장일인지 여부 검사를 스킵 (기본적으로 휴장일이면 조기 종료)"
    )
    
    args = parser.parse_args()

    # 의존성 초기화
    calendar_service = CalendarService()
    
    # 1. 배치 기동 시 휴장일 조기 스킵 메커니즘
    today = date.today()
    if not args.skip_holiday_check and not args.force:
        if calendar_service.is_holiday(today):
            print(f"[Batch] 오늘은 거래소 휴장일({today})입니다. 수집 동기화를 안전하게 스킵하고 종료합니다.")
            return

    krx_adapter = KrxStockDataAdapter()

    gdrive_adapter = GoogleDriveAdapter()

    # DB SSOT(Drive)를 진짜 임시 작업 사본으로 받아오는 세션 (db_ssot_guide.md §6.1).
    # 로컬 db/ 디렉토리는 더 이상 신뢰하지 않는다 - 세션이 끝나면 tempdir을 통째로 삭제한다.
    # collect/backfill이 커버리지 시작 이전 연도를 지정해도 그 해를 세션 범위에 포함시켜야
    # DbSyncSession이 실제로 다운로드를 시도한다 - 안 그러면 "시도 안 함"이 "실패 없음"으로
    # 오인되어 원격 미확인 상태로 그 연도를 빈 DB 취급/업로드하게 된다.
    start_year = min(DEFAULT_COVERAGE_START.year, args.year or DEFAULT_COVERAGE_START.year)
    end_year = max(date.today().year, args.year or 0)
    with DbSyncSession(gdrive_adapter, start_year, end_year) as session:
        repository_weekly = SqliteReportStorageAdapter(base_dir=session.base_dir(), period_type="WEEKLY")
        repository_monthly = SqliteReportStorageAdapter(base_dir=session.base_dir(), period_type="MONTHLY")

        service = WeeklyGainerService(
            calendar=calendar_service,
            stock_data=krx_adapter,
            repository=repository_weekly,
            uploader=gdrive_adapter,
            repository_monthly=repository_monthly
        )

        try:
            # 액션별 분기 실행
            if args.action == "sync":
                # 동기화 파이프라인 기동 (주간+월간 동시 처리, --period 무시)
                orchestrator = CollectionOrchestratorService(service, failed_years=session.failed_years)
                orchestrator.run_daily_sync()

            elif args.action == "collect":
                if not args.year or not args.value:
                    print("[Error] collect 액션 실행 시에는 --year 및 --value 지정이 필수입니다.")
                    sys.exit(1)
                if args.year in session.failed_years[args.period.upper()]:
                    print(f"[Error] {args.year}년 DB를 원격에서 받아오지 못했습니다. 이번 실행을 중단합니다.")
                    sys.exit(1)

                # 단일 수집 실행
                success = service.collect_period(
                    period_type=args.period,
                    year=args.year,
                    period_value=args.value,
                    force=args.force,
                    is_final=args.final
                )
                if not success:
                    print(f"[Collect] {args.period} {args.year}-{args.value} 수집 실패")
                    sys.exit(1)
                service.sync_manifest(args.period, args.year)
                service.sync_db_to_drive(args.period, args.year)

            elif args.action == "backfill":
                if not args.year:
                    print("[Error] backfill 액션 실행 시에는 --year 지정이 필수입니다.")
                    sys.exit(1)
                if args.year in session.failed_years[args.period.upper()]:
                    print(f"[Error] {args.year}년 DB를 원격에서 받아오지 못했습니다. 이번 실행을 중단합니다.")
                    sys.exit(1)

                # 백필 실행 (--force 시 지문 동일 여부와 무관하게 재수집하여 최신 스키마로 갱신)
                service.backfill_year(year=args.year, period_type=args.period, force=args.force)
                service.sync_manifest(args.period, args.year)
                service.sync_db_to_drive(args.period, args.year)

        except Exception as e:
            print(f"ERROR: 실행 중 오류 발생: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
