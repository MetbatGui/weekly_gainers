import io
import json
import os
import pandas as pd
import pytest
from datetime import datetime, date
from typing import Optional

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from infra.storage.google_drive_repository import GoogleDriveReportStorageAdapter
from domain.ports import CloudUploadPort

# 테스트용 CloudUploadPort 스텁 정의
class StubCloudUploader(CloudUploadPort):
    def __init__(self):
        self.uploaded_files = {} # Key: (remote_path, filename) -> Value: bytes

    def upload_excel(self, file_content: bytes, remote_path: str, filename: str) -> bool:
        self.uploaded_files[(remote_path, filename)] = file_content
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        with open(local_path, "rb") as f:
            self.uploaded_files[(remote_path, filename)] = f.read()
        return True

    def download_file(self, remote_path: str, filename: str) -> Optional[bytes]:
        return self.uploaded_files.get((remote_path, filename))

@pytest.fixture
def drive_repo():
    uploader = StubCloudUploader()
    repo = GoogleDriveReportStorageAdapter(uploader=uploader, period_type="WEEKLY")
    return repo

def test_google_drive_repo_save_and_get_lifecycle(drive_repo):
    """GoogleDriveReportStorageAdapter가 로컬 Parquet 흔적을 남기지 않고, 드라이브 상의 Excel 리포트 시트를 파싱해 도메인 모델을 완벽히 복원하는지 검증"""
    
    event_id = "2026-W26"
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
        id=event_id,
        year=2026,
        week=26,
        collected_at=datetime(2026, 6, 26, 15, 30),
        day_of_week="Friday",
        last_trading_day=date(2026, 6, 26),
        status=CollectionStatus.COMPLETED,
        items=[item],
        fingerprint="dummy_fingerprint"
    )

    # 1. 수집 전 존재 검사
    assert drive_repo.exists(event_id) is False
    assert drive_repo.get_by_id(event_id) is None

    # 2. 저장 수행 (매니페스트만 올라감)
    drive_repo.save(event)

    # 3. 스텁 업로더 검증 (매니페스트 JSON 생성 확인)
    manifest_name = "weekly_event_manifest_2026.json"
    manifest_content = drive_repo.gdrive.download_file("2026", manifest_name)
    assert manifest_content is not None
    manifest_dict = json.loads(manifest_content.decode("utf-8"))
    assert event_id in manifest_dict
    assert manifest_dict[event_id]["fingerprint"] == "dummy_fingerprint"

    # 매니페스트 상에 등록된 파일명이 .xlsx인지 확인
    excel_filename = manifest_dict[event_id]["filename"]
    assert excel_filename.endswith(".xlsx")

    # 4. Excel 기반 복원 테스트를 위한 Mock Excel 데이터 등록
    df_mock = pd.DataFrame([{
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
        df_mock.to_excel(writer, sheet_name="전체_등락종목", index=False)
    excel_bytes = excel_buffer.getvalue()
    
    # 엑셀은 f"{year}/{month:02d}월" 경로 아래에 저장됨 (2026년 26주차 목요일 기준 월은 6월)
    excel_remote_path = "2026/06월"
    drive_repo.gdrive.uploaded_files[(excel_remote_path, excel_filename)] = excel_bytes

    # 5. 복원 조회 실행
    loaded_event = drive_repo.get_by_id(event_id)
    assert loaded_event is not None
    assert loaded_event.id == event_id
    assert loaded_event.year == 2026
    assert loaded_event.week == 26
    assert len(loaded_event.items) == 1
    assert loaded_event.items[0].symbol_name == "삼성전자"
    assert loaded_event.items[0].change_rate == 21.43

    # 6. 존재 여부 확인
    assert drive_repo.exists(event_id) is True
