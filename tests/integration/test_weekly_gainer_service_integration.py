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

    def upload_excel(self, dfs: dict[str, pd.DataFrame], remote_path: str, filename: str) -> bool:
        self.uploaded_files.append((filename, remote_path, dfs))
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        self.uploaded_files.append((filename, remote_path, local_path))
        return True

def test_weekly_gainer_service_integration_flow(tmp_path):
    """실제 서비스에 실제 인프라 어댑터들을 주입하고, HTTP만 모킹한 상태에서 전체 주간 수집 파이프라인 통합 흐름 검증"""
    
    # 1. 실제 어댑터들 생성 (스토리지 격리)
    calendar = CalendarService()
    
    # 실제 KRX 어댑터
    stock_data = KrxStockDataAdapter()
    
    # 실제 Parquet 저장소 (tmp_path를 주입하여 격리)
    base_path = tmp_path / "data" / "weekly_gainers"
    repository = ParquetWeeklyGainerRepository(base_path=str(base_path))
    
    # 구글 드라이브 업로더 스텁
    uploader = StubUploader()

    # 2. 서비스 인스턴스에 실제 어댑터들 주입 (마일스톤 1 의존성 주입 완성형)
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

    # KRX HTTP 세션 post 모킹
    with patch.object(stock_data.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SUCCESS"
        mock_response.json.return_value = mock_krx_data
        mock_post.return_value = mock_response

        # 4. 수집 프로세스 실행 (2026년 26주차: 6월 22일 ~ 6월 26일)
        success = service.collect_week(2026, 26, force=True, is_final=False)

        # 5. 종합 검증
        assert success is True
        
        # 실제 Parquet 저장소에 물리 파일 및 매니페스트가 생성되었는지 검증
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

        # 업로더 기록 검증 (단일 DataFrame 엑셀 업로드 수행 확인)
        assert len(uploader.uploaded_files) == 1
        filename, remote_path, df = uploader.uploaded_files[0]
        assert "weekly_gainers_2026_W26" in filename
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1  # 엑셀 시트에도 1개 종목만 들어있어야 함
        assert df.iloc[0]['종목명'] == "삼성전자"
