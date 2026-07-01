import io
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

from infra.storage.google_drive_adapter import GoogleDriveAdapter

def test_google_drive_adapter_polymorphic_excel_generation():
    """GoogleDriveAdapter가 다중 시트 딕셔너리와 단일 DataFrame 입력을 모두 수용하여 정상적으로 엑셀 바이너리를 컴파일하는지 검증"""
    
    # Google API 인증 자체를 Mocking하여 인증 과정을 완벽하게 격리
    with patch.object(GoogleDriveAdapter, "_authenticate") as mock_auth:
        mock_service = MagicMock()
        mock_auth.return_value = mock_service
        
        # 파일 존재하지 않는 상태 모킹 (create 호출 유도)
        mock_service.files().list().execute.return_value = {"files": []}
        
        adapter = GoogleDriveAdapter()

        # 테스트용 데이터프레임
        df_all = pd.DataFrame({"종목명": ["삼성전자"], "등락률": [21.43]})
        df_kospi = pd.DataFrame({"종목명": ["SK하이닉스"], "등락률": [20.00]})

        # 1. 다중 시트 딕셔너리 입력 테스트
        # 캡처를 위해 MediaIoBaseUpload를 패치하여 업로드되는 바이너리 스트림 획득
        with patch("infra.storage.google_drive_adapter.MediaIoBaseUpload") as mock_media_upload:
            success = adapter.upload_excel(
                dfs={"All_Gainers": df_all, "KOSPI_200": df_kospi},
                remote_path="test_folder",
                filename="test_multi_sheet.xlsx"
            )
            
            assert success is True
            # MediaIoBaseUpload 호출 확인 및 바이트 스트림 파싱 검증
            mock_media_upload.assert_called_once()
            captured_stream = mock_media_upload.call_args[0][0] # 첫 번째 인자가 io.BytesIO
            
            # 컴파일된 바이트로부터 엑셀 시트들이 실제로 생성되었는지 판다스로 확인
            captured_stream.seek(0)
            excel_file = pd.ExcelFile(captured_stream, engine='openpyxl')
            assert "All_Gainers" in excel_file.sheet_names
            assert "KOSPI_200" in excel_file.sheet_names

            # 각 시트 데이터 검증
            df_read_all = pd.read_excel(excel_file, sheet_name="All_Gainers")
            assert df_read_all.iloc[0]["종목명"] == "삼성전자"

        # 2. 하위 호환성: 단일 DataFrame 직접 입력 테스트
        with patch("infra.storage.google_drive_adapter.MediaIoBaseUpload") as mock_media_upload_single:
            success_single = adapter.upload_excel(
                dfs=df_all, # 딕셔너리가 아닌 단일 df를 통째로 전달 (하위 호환)
                remote_path="test_folder",
                filename="test_single_sheet.xlsx"
            )

            assert success_single is True
            mock_media_upload_single.assert_called_once()
            captured_stream_single = mock_media_upload_single.call_args[0][0]
            
            captured_stream_single.seek(0)
            excel_file_single = pd.ExcelFile(captured_stream_single, engine='openpyxl')
            # 딕셔너리가 아닌 경우 기본 시트명인 'WeeklyGainers' 또는 'Sheet1' 등으로 자동 폴백되어야 함
            assert "WeeklyGainers" in excel_file_single.sheet_names or "Sheet1" in excel_file_single.sheet_names
            
            df_read_single = pd.read_excel(excel_file_single, sheet_name=excel_file_single.sheet_names[0])
            assert df_read_single.iloc[0]["종목명"] == "삼성전자"
