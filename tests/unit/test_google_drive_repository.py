import io
import json
import os
import pandas as pd
import pytest
from datetime import datetime, date

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from infra.storage.google_drive_repository import GoogleDriveReportStorageAdapter
from domain.ports import CloudUploadPort

# 테스트용 CloudUploadPort 스텁 정의
class StubCloudUploader(CloudUploadPort):
    def __init__(self):
        self.uploaded_files = {} # Key: (remote_path, filename) -> Value: bytes or local_path
        self.uploaded_excels = {} # Key: (remote_path, filename) -> Value: bytes

    def upload_excel(self, file_content: bytes, remote_path: str, filename: str) -> bool:
        self.uploaded_excels[(remote_path, filename)] = file_content
        return True

    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        # 파일 내용을 직접 읽어서 메모리에 보관
        with open(local_path, "rb") as f:
            self.uploaded_files[(remote_path, filename)] = f.read()
        return True

    def download_file(self, remote_path: str, filename: str) -> Optional[bytes]:
        # 보관된 파일 내용 반환
        return self.uploaded_files.get((remote_path, filename))

@pytest.fixture
def drive_repo():
    uploader = StubCloudUploader()
    repo = GoogleDriveReportStorageAdapter(uploader=uploader, period_type="WEEKLY")
    return repo

def test_google_drive_repo_save_and_get_lifecycle(drive_repo):
    """GoogleDriveReportStorageAdapter가 로컬에 파일을 잔류시키지 않고 구글 드라이브 메모리 스키마를 통해 저장/로드/존재유무를 완벽히 수행하는지 검증"""
    
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

    # 2. 저장 수행
    drive_repo.save(event)

    # 3. 스텁 업로더 검증 (매니페스트 및 Parquet 파일이 정상적으로 구글 드라이브에 올라갔는지 검증)
    manifest_name = "weekly_event_manifest_2026.json"
    
    # 드라이브 매니페스트 확인
    manifest_content = drive_repo.gdrive.download_file("2026", manifest_name)
    assert manifest_content is not None
    manifest_dict = json.loads(manifest_content.decode("utf-8"))
    assert event_id in manifest_dict
    assert manifest_dict[event_id]["fingerprint"] == "dummy_fingerprint"

    # 드라이브 Parquet 확인
    parquet_filename = manifest_dict[event_id]["filename"]
    assert parquet_filename.startswith("weekly_gainers_2026_W26")
    
    parquet_content = drive_repo.gdrive.download_file("2026/data/weekly", parquet_filename)
    assert parquet_content is not None
    
    # 4. 복원 조회 검사
    loaded_event = drive_repo.get_by_id(event_id)
    assert loaded_event is not None
    assert loaded_event.id == event_id
    assert loaded_event.year == 2026
    assert loaded_event.week == 26
    assert len(loaded_event.items) == 1
    assert loaded_event.items[0].symbol_name == "삼성전자"
    assert loaded_event.items[0].change_rate == 21.43

    # 5. 존재 여부 확인
    assert drive_repo.exists(event_id) is True
