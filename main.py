import os
import sys
from dotenv import load_dotenv

# src 경로를 시스템 경로에 추가
sys.path.append(os.path.join(os.getcwd(), 'src'))

from application.services.calendar_service import CalendarService
from application.services.weekly_gainer_service import WeeklyGainerService
from infra.adapters.krx_adapter import KrxStockDataAdapter
from infra.storage.parquet_repository import ParquetWeeklyGainerRepository
from infra.storage.google_drive_adapter import GoogleDriveAdapter

def main():
    # .env 로드
    load_dotenv()
    
    # 의존성 초기화
    calendar_service = CalendarService()
    krx_adapter = KrxStockDataAdapter()
    repository = ParquetWeeklyGainerRepository(base_path="data/weekly_gainers")
    gdrive_adapter = GoogleDriveAdapter()
    
    service = WeeklyGainerService(
        calendar_service=calendar_service,
        krx_adapter=krx_adapter,
        repository=repository,
        gdrive_adapter=gdrive_adapter
    )
    
    # 파이프라인 실행 (지난주 확정 + 이번 주 실시간 업데이트)
    try:
        service.sync_pipeline()
    except Exception as e:
        print(f"ERROR: 실행 중 오류 발생: {e}")

if __name__ == "__main__":
    main()
