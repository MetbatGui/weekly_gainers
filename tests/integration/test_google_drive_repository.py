import io
import json
import pytest
import pandas as pd
from typing import Optional
from datetime import datetime, date
from unittest.mock import patch, MagicMock

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from infra.storage.google_drive_adapter import GoogleDriveAdapter
from infra.storage.google_drive_repository import GoogleDriveReportStorageAdapter

def test_google_drive_repository_integration_flow():
    """Mocking된 Google Drive API 세션 상에서 GoogleDriveReportStorageAdapter의 업로드, 다운로드, 매니페스트 관리가 완전히 모킹되어 연동되는지 검증"""
    
    # 1. Google API 인증 모킹
    with patch.object(GoogleDriveAdapter, "_authenticate") as mock_auth:
        mock_service = MagicMock()
        mock_auth.return_value = mock_service
        
        # 파일 존재하지 않는 상태 모킹 (최초 create 유도)
        mock_service.files().list().execute.return_value = {"files": []}
        
        # 실제 어댑터 생성
        gdrive_adapter = GoogleDriveAdapter()
        
        # 구글 드라이브 리포지토리 생성
        repo = GoogleDriveReportStorageAdapter(uploader=gdrive_adapter, period_type="WEEKLY")

        # 2. 테스트 데이터 생성
        item = WeeklyGainerItem(
            symbol_code="005930",
            symbol_name="삼성전자",
            start_date=date(2026, 6, 22),
            base_price=70000.0,
            end_date=date(2026, 6, 26),
            close_price=85000.0,
            change=15000.0,
            change_rate=21.43,
            volume=100000,
            amount=8500000000
        )
        event = WeeklyCollectionEvent(
            id="2026-W26",
            year=2026,
            week=26,
            collected_at=datetime(2026, 6, 26, 15, 30),
            day_of_week="Friday",
            last_trading_day=date(2026, 6, 26),
            status=CollectionStatus.COMPLETED,
            items=[item],
            fingerprint="dummy_fp"
        )

        # 3. 저장(save) 모킹 및 실행
        # _ensure_path 및 MediaIoBaseUpload 패치
        with patch.object(gdrive_adapter, "_ensure_path", return_value="mock_parent_id") as mock_ensure, \
             patch("googleapiclient.http.MediaFileUpload") as mock_media_upload:
             
            # 매니페스트는 다운로드 시 처음엔 비어있는 상태 시뮬레이션
            with patch.object(repo, "_load_manifest", return_value={}) as mock_load:
                repo.save(event)
                
                # 매니페스트 로드 검증
                mock_load.assert_called_once_with(2026)

            # ensure_path 및 MediaIoBaseUpload 호출 검증
            assert mock_ensure.call_count >= 1
            mock_media_upload.assert_called()

        # 4. 복원 조회(get_by_id) 모킹 및 실행
        # get_by_id 시 다운로드될 모의 바이트 데이터
        mock_manifest_data = {
            "2026-W26": {
                "id": "2026-W26",
                "year": 2026,
                "week": 26,
                "month": 6,
                "week_of_month": 4,
                "collected_at": "2026-06-26T15:30:00",
                "day_of_week": "Friday",
                "last_trading_day": "2026-06-26",
                "status": "COMPLETED",
                "total_count": 100,
                "filename": "weekly_gainers_2026_W26.xlsx",
                "fingerprint": "dummy_fp"
            }
        }
        
        # 4-1. Excel mock 파일 작성
        df_dummy = pd.DataFrame([{
            '종목코드': '005930',
            '종목명': '삼성전자',
            '시작일': '2026-06-22',
            '기준가': 70000.0,
            '종료일': '2026-06-26',
            '종가': 85000.0,
            '대비': 15000.0,
            '등락률': 21.43,
            '거래량': 100000,
            '거래대금': 8500000000
        }])
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_dummy.to_excel(writer, sheet_name="전체_등락종목", index=False)
        excel_bytes = excel_buffer.getvalue()

        # 어댑터 다운로드 함수 모킹
        def mock_download(remote_path, filename):
            if "manifest" in filename:
                return json.dumps(mock_manifest_data).encode("utf-8")
            if filename.endswith(".xlsx"):
                return excel_bytes
            return None

        with patch.object(gdrive_adapter, "download_file", side_effect=mock_download) as mock_dl:
            loaded_event = repo.get_by_id("2026-W26")
            
            # 다운로드 검증
            assert mock_dl.call_count == 2 # 1차 매니페스트 + 2차 Excel
            
            assert loaded_event is not None
            assert loaded_event.id == "2026-W26"
            assert len(loaded_event.items) == 1
            assert loaded_event.items[0].symbol_name == "삼성전자"
            assert loaded_event.items[0].change_rate == 21.43
