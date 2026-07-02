from datetime import date, datetime
from unittest.mock import patch, MagicMock
from pathlib import Path
import pandas as pd
import pytest

from application.services.weekly_gainer_service import WeeklyGainerService
from application.services.calendar_service import CalendarService
from infra.adapters.krx_adapter import KrxStockDataAdapter
from infra.storage.parquet_repository import ParquetWeeklyGainerRepository
from domain.ports import CloudUploadPort

# Google Drive 업로더는 인증 토큰 의존성 때문에 Stub으로 대체합니다 (스텁 대체 원칙)
class StubUploader(CloudUploadPort):
    def __init__(self):
        self.uploaded_files = []

    def upload_excel(self, file_content: bytes, remote_path: str, filename: str) -> bool:
        self.uploaded_files.append((filename, remote_path, file_content))
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        # 락이 풀린 후 파일을 읽어야 하므로, 경로만 저장하지 않고 데이터 자체를 메모리에 복사해 두는 것이 안전함
        with open(local_path, "rb") as f:
            content_data = f.read()
        self.uploaded_files.append((filename, remote_path, content_data))
        return True

    def download_file(self, remote_path: str, filename: str) -> Optional[bytes]:
        for f_name, r_path, content in self.uploaded_files:
            if f_name == filename and r_path == remote_path:
                return content
        return None

def test_weekly_gainer_service_integration_flow(tmp_path):
    """실제 서비스에 실제 인프라 어댑터들을 주입하고, HTTP만 모킹한 상태에서 전체 주간 수집 파이프라인 통합 흐름 검증"""
    import io
    
    # 1. 실제 어댑터들 생성 (스토리지 격리)
    calendar = CalendarService()
    
    # 실제 KRX 어댑터
    stock_data = KrxStockDataAdapter()
    
    # 구글 드라이브 업로더 스텁
    uploader = StubUploader()
    
    # 구글 드라이브 기반 저장소 (로컬 대신 드라이브 SSOT 사용)
    from infra.storage.google_drive_repository import GoogleDriveReportStorageAdapter
    repository = GoogleDriveReportStorageAdapter(uploader=uploader, period_type="WEEKLY")

    # 2. 서비스 인스턴스에 실제 어댑터들 주입 (의존성 주입 완료형)
    service = WeeklyGainerService(
        calendar=calendar,
        stock_data=stock_data,
        repository=repository,
        uploader=uploader
    )

    # 3. HTTP 응답 데이터 모킹 (KRX 전종목 등락 데이터)
    mock_krx_data = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "005930",
                "ISU_ABBRV": "삼성전자",
                "BAS_PRC": "70,000",
                "TDD_CLSPRC": "85,000",
                "CMPPREVDD_PRC": "15,000",
                "FLUC_RT": "21.43",        # 20% 초과 종목
                "ACC_TRDVOL": "100,000",
                "ACC_TRDVAL": "8,500,000,000"
            },
            {
                "ISU_SRT_CD": "000660",
                "ISU_ABBRV": "SK하이닉스",
                "BAS_PRC": "150,000",
                "TDD_CLSPRC": "165,000",
                "CMPPREVDD_PRC": "15,000",
                "FLUC_RT": "10.00",        # 20% 미만 종목 (필터링되어야 함)
                "ACC_TRDVOL": "50,000",
                "ACC_TRDVAL": "9,000,000,000"
            }
        ]
    }

    # KRX HTTP 세션 post 모킹 및 지수구성종목 모킹
    with patch.object(stock_data.session, 'post') as mock_post, \
         patch.object(stock_data, 'fetch_index_components', return_value={"005930"}) as mock_idx:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SUCCESS"
        mock_response.json.return_value = mock_krx_data
        mock_post.return_value = mock_response

        # 4. 수집 프로세스 실행 (2026년 26주차: 6월 22일 ~ 6월 26일)
        success = service.collect_week(2026, 26, force=True, is_final=False)

        # 5. 종합 검증
        assert success is True
        
        # 지수 구성종목이 총 4번 호출되는지 검증 (시작일/종료일 x K200/K150)
        assert mock_idx.call_count == 4
        
        # 구글 드라이브 스텁에 물리 매니페스트가 생성되었는지 검증
        event_id = "2026-W26"
        assert repository.exists(event_id) is True
        
        # 파일 저장 검증
        loaded_event = repository.get_by_id(event_id)
        assert loaded_event is not None
        assert loaded_event.year == 2026
        assert loaded_event.week == 26
        
        # 필터링 검증: 20% 넘는 삼성전자만 남아야 함 (SK하이닉스는 10%이므로 필터 탈락)
        assert len(loaded_event.items) == 1
        assert loaded_event.items[0].symbol_name == "삼성전자"
        assert loaded_event.items[0].change_rate == 21.43

        # 업로더 기록 검증 (엑셀 리포트, 매니페스트 등 총 2건 확인)
        assert len(uploader.uploaded_files) == 2
        
        # 엑셀 파일 찾기
        excel_upload = next((f for f in uploader.uploaded_files if f[0].endswith(".xlsx")), None)
        assert excel_upload is not None
        excel_filename, excel_remote_path, excel_content = excel_upload
        assert "weekly_gainers_2026_W26" in excel_filename
        assert isinstance(excel_content, bytes)
        
        # 매니페스트 파일 찾기
        manifest_upload = next((f for f in uploader.uploaded_files if f[0].endswith(".json")), None)
        assert manifest_upload is not None
        
        # 엑셀 데이터프레임 복원 및 시트별 검증
        excel_file = pd.ExcelFile(io.BytesIO(excel_content), engine='openpyxl')
        assert "전체_등락종목" in excel_file.sheet_names
        assert "KOSPI_200" in excel_file.sheet_names
        assert "KOSDAQ_150" in excel_file.sheet_names
        
        df_all = pd.read_excel(excel_file, sheet_name="전체_등락종목")
        assert len(df_all) == 1
        assert df_all.iloc[0]['종목명'] == "삼성전자"
        
        df_k200 = pd.read_excel(excel_file, sheet_name="KOSPI_200")
        assert len(df_k200) == 1
        assert df_k200.iloc[0]['종목명'] == "삼성전자"

