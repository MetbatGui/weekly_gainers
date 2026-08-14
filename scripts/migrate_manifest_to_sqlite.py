"""
1회성 마이그레이션 스크립트: Google Drive 매니페스트+Excel(GoogleDriveReportStorageAdapter)
-> SQLite(SqliteReportStorageAdapter, db/{weekly,monthly}/{year}.db)

WEEKLY/MONTHLY 각각 list_all_events()로 전체 event_id를 조회한 뒤, get_by_id()로
매니페스트+Excel을 파싱해 새 SQLite 저장소에 그대로 저장한다.

실행: uv run python scripts/migrate_manifest_to_sqlite.py
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

from domain.ports import ReportStoragePort


def migrate_period(old_repo: ReportStoragePort, new_repo: ReportStoragePort, event_ids: List[str]) -> int:
    """event_ids 각각을 old_repo에서 읽어 new_repo에 저장하고, 실제로 이관된 건수를 반환한다."""
    migrated = 0
    for event_id in event_ids:
        try:
            event = old_repo.get_by_id(event_id)
        except Exception as e:
            print(f"[Migrate] {event_id}: old_repo 로드 중 예외 발생({e}), 건너뜀")
            continue
        if event is None:
            print(f"[Migrate] {event_id}: old_repo에서 로드 실패, 건너뜀")
            continue
        new_repo.save(event)
        migrated += 1
    return migrated


def main():
    load_dotenv()

    from infra.storage.google_drive_adapter import GoogleDriveAdapter
    from infra.storage.google_drive_repository import GoogleDriveReportStorageAdapter
    from infra.storage.sqlite_repository import SqliteReportStorageAdapter

    gdrive_adapter = GoogleDriveAdapter()

    for period_type in ("WEEKLY", "MONTHLY"):
        old_repo = GoogleDriveReportStorageAdapter(uploader=gdrive_adapter, period_type=period_type)
        new_repo = SqliteReportStorageAdapter(base_dir="db", period_type=period_type)

        event_ids = [e.id for e in old_repo.list_all_events()]
        migrated = migrate_period(old_repo, new_repo, event_ids)
        print(f"[Migrate] {period_type}: {migrated}/{len(event_ids)}건 이관 완료")


if __name__ == "__main__":
    main()
