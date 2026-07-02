import os
import sys
import argparse
from datetime import date
from dotenv import load_dotenv

# src 경로를 시스템 경로에 추가
sys.path.append(os.path.join(os.getcwd(), 'src'))

from application.services.calendar_service import CalendarService
from application.services.weekly_gainer_service import WeeklyGainerService
from infra.adapters.krx_adapter import KrxStockDataAdapter
from infra.storage.google_drive_repository import GoogleDriveReportStorageAdapter
from infra.storage.google_drive_adapter import GoogleDriveAdapter

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
    
    # 구글 드라이브 기반 SSOT 저장소 주입 (로컬 파일 완전 제거)
    repository_weekly = GoogleDriveReportStorageAdapter(uploader=gdrive_adapter, period_type="WEEKLY")
    repository_monthly = GoogleDriveReportStorageAdapter(uploader=gdrive_adapter, period_type="MONTHLY")
    
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
            # 동기화 파이프라인 기동
            service.sync_pipeline(period_type=args.period)
            
        elif args.action == "collect":
            if not args.year or not args.value:
                print("[Error] collect 액션 실행 시에는 --year 및 --value 지정이 필수입니다.")
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
                
        elif args.action == "backfill":
            if not args.year:
                print("[Error] backfill 액션 실행 시에는 --year 지정이 필수입니다.")
                sys.exit(1)
                
            # 백필 실행
            service.backfill_year(year=args.year, period_type=args.period)
            
    except Exception as e:
        print(f"ERROR: 실행 중 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
