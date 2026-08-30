from pathlib import Path
from typing import Optional

from domain.ports import CloudUploadPort
from infra.storage.db_sync_session import DbSyncSession


class FakeUploader(CloudUploadPort):
    def __init__(self, remote_files: dict[tuple[str, str], bytes] | None = None, broken: set[tuple[str, str]] | None = None):
        self.remote_files = remote_files or {}
        self.broken = broken or set()  # 원격엔 있지만 get_file이 실패해야 하는 (remote_path, filename)

    def upload_excel(self, file_content, remote_path, filename) -> bool:
        return True

    def upload_file(self, local_path, remote_path, filename, mimetype='application/octet-stream') -> bool:
        return True

    def path_exists(self, remote_path, filename) -> bool:
        return (remote_path, filename) in self.remote_files

    def download_file(self, remote_path, filename) -> Optional[bytes]:
        if (remote_path, filename) in self.broken:
            return None
        return self.remote_files.get((remote_path, filename))


def test_downloads_existing_years_into_tempdir_and_cleans_up_on_exit():
    uploader = FakeUploader(remote_files={("db/weekly", "2024.db"): b"weekly-2024"})

    with DbSyncSession(uploader, coverage_start_year=2024, end_year=2024) as session:
        base = Path(session.base_dir())
        assert (base / "weekly" / "2024.db").read_bytes() == b"weekly-2024"
        assert session.failed_years == {"WEEKLY": set(), "MONTHLY": set()}
        tmp_dir = base

    assert not tmp_dir.exists()


def test_year_not_yet_on_remote_is_not_a_failure():
    uploader = FakeUploader(remote_files={})

    with DbSyncSession(uploader, coverage_start_year=2026, end_year=2026) as session:
        base = Path(session.base_dir())
        assert not (base / "weekly" / "2026.db").exists()
        assert session.failed_years == {"WEEKLY": set(), "MONTHLY": set()}


def test_download_failure_for_existing_remote_file_is_fail_closed_per_year():
    uploader = FakeUploader(
        remote_files={("db/weekly", "2023.db"): b"", ("db/weekly", "2024.db"): b"weekly-2024"},
        broken={("db/weekly", "2023.db")},
    )

    with DbSyncSession(uploader, coverage_start_year=2023, end_year=2024) as session:
        base = Path(session.base_dir())
        assert not (base / "weekly" / "2023.db").exists()
        assert (base / "weekly" / "2024.db").read_bytes() == b"weekly-2024"
        assert session.failed_years["WEEKLY"] == {2023}
        assert 2024 not in session.failed_years["WEEKLY"]
