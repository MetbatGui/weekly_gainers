"""GDrive DB SSOT를 진짜 임시 작업 사본으로 받아오는 세션 (db_ssot_guide.md §6.1).

로컬 db/{weekly,monthly}/{year}.db 같은 영속 경로를 신뢰하지 않는다. 매 실행마다
tempfile.mkdtemp()로 새 임시 디렉토리를 만들어 GDrive에서 최신 DB를 받아오고,
실행이 끝나면(성공/실패 무관) 통째로 삭제한다 - 로컬에는 세션 종료 후 아무것도 남지 않는다.

다운로드 실패는 "원격에 아직 없음"(정상, 최초 백필 전)과 구분해 연도별로 fail-closed
처리한다: 해당 연도만 이번 실행에서 건너뛰고(빈 DB로 시작해 그대로 덮어쓰는 사고 방지),
나머지 정상 연도는 평소대로 처리한다 - weekly_gainers 크론의 기존 가용성 우선 정책을
유지하기 위한 절충.
"""

import logging
import shutil
import tempfile
from pathlib import Path

from domain.ports import CloudUploadPort

logger = logging.getLogger(__name__)

_PERIOD_SUBFOLDER = {"WEEKLY": "weekly", "MONTHLY": "monthly"}


class DbSyncSession:
    """coverage_start_year ~ end_year 범위의 weekly/monthly DB를 임시 작업 사본으로 관리."""

    def __init__(self, uploader: CloudUploadPort, coverage_start_year: int, end_year: int):
        self.uploader = uploader
        self.years = list(range(coverage_start_year, end_year + 1))
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="weekly_gainers_db_"))
        self.failed_years: dict[str, set[int]] = {"WEEKLY": set(), "MONTHLY": set()}

    def __enter__(self) -> "DbSyncSession":
        for period_type, subfolder in _PERIOD_SUBFOLDER.items():
            local_dir = self.tmp_dir / subfolder
            local_dir.mkdir(parents=True, exist_ok=True)
            remote_path = f"db/{subfolder}"
            for year in self.years:
                filename = f"{year}.db"
                # ponytail: path_exists() 자체의 실패(네트워크 오류 등)는 "원격에 없음"과
                # 구분하지 못하고 False로 뭉개짐 - get_file()의 실패(§6.1 핵심 대상)보다
                # 발생 빈도/영향이 낮은 메타데이터 조회라 여기서는 감수. 자주 걸리면
                # path_exists 자체에 재시도를 추가할 것.
                if not self.uploader.path_exists(remote_path, filename):
                    continue  # 원격에 아직 없음 - 정상(백필 전), 빈 DB로 시작 허용
                data = self.uploader.download_file(remote_path, filename)
                if data is None:
                    logger.warning(
                        f"[DbSyncSession] {period_type} {year}년 DB 다운로드 실패 - "
                        "이번 실행에서 해당 연도 건너뜀"
                    )
                    self.failed_years[period_type].add(year)
                    continue
                (local_dir / filename).write_bytes(data)
        return self

    def base_dir(self) -> str:
        return str(self.tmp_dir)

    def __exit__(self, exc_type, exc, tb) -> bool:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        return False
