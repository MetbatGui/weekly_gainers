import io
from unittest.mock import patch, MagicMock
import pytest

from infra.storage.google_drive_adapter import GoogleDriveAdapter

def test_google_drive_adapter_excel_bytes_upload():
    """GoogleDriveAdapter가 Excel 바이너리 바이트(bytes)를 입력받아 구글 드라이브로 업로드하는지 검증"""
    
    # Google API 인증 자체를 Mocking하여 인증 과정을 완벽하게 격리
    with patch.object(GoogleDriveAdapter, "_authenticate") as mock_auth:
        mock_service = MagicMock()
        mock_auth.return_value = mock_service
        
        # 파일 존재하지 않는 상태 모킹 (create 호출 유도)
        mock_service.files().list().execute.return_value = {"files": []}
        
        adapter = GoogleDriveAdapter()

        # 테스트용 엑셀 바이너리 데이터 (임의의 바이트 데이터)
        dummy_excel_bytes = b"dummy excel file content"

        # MediaIoBaseUpload 패치 및 폴더 경로 자동 생성 모킹
        with patch("infra.storage.google_drive_adapter.MediaIoBaseUpload") as mock_media_upload, \
             patch.object(adapter, "_ensure_path", return_value="mock_parent_folder_id") as mock_ensure:
             
            success = adapter.upload_excel(
                file_content=dummy_excel_bytes,
                remote_path="test_folder",
                filename="test_multi_sheet.xlsx"
            )
            
            assert success is True
            mock_ensure.assert_called_once_with("test_folder")
            
            # MediaIoBaseUpload 호출 확인
            mock_media_upload.assert_called_once()
            captured_stream = mock_media_upload.call_args[0][0] # 첫 번째 인자가 io.BytesIO
            
            # 스트림에 담긴 데이터가 입력된 더미 바이트와 일치하는지 검증
            captured_stream.seek(0)
            assert captured_stream.read() == dummy_excel_bytes

            # create 호출 검증 (이제 폴더 생성이 모킹되었으므로 파일 생성 create 1회만 발생함)
            mock_service.files().create.assert_called_once()
            called_body = mock_service.files().create.call_args[1].get('body', {})
            assert called_body.get('name') == 'test_multi_sheet.xlsx'
            assert called_body.get('parents') == ['mock_parent_folder_id']
