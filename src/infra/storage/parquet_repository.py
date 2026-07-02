import os
import json
import pandas as pd
from typing import Optional, List, Set
from datetime import datetime, date
from pathlib import Path

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from domain.ports import ReportStoragePort

class ParquetWeeklyGainerRepository(ReportStoragePort):
    """Parquet 파일과 연도별 매니페스트를 사용하여 주간/월간 등락률 데이터를 저장하는 구현체."""

    def __init__(self, base_path: str = "data/weekly_gainers", period_type: Optional[str] = None):
        self.raw_base = Path(base_path)
        self.period_type = period_type
        
        if period_type == "WEEKLY":
            self.base_path = self.raw_base / "weekly"
        elif period_type == "MONTHLY":
            self.base_path = self.raw_base / "monthly"
        else:
            self.base_path = self.raw_base
            
        self._ensure_directories()

    def _ensure_directories(self):
        """데이터 저장 경로가 없으면 생성합니다."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_manifest_path(self, year: int) -> Path:
        """지정된 연도의 매니페스트 파일 경로를 동적으로 반환합니다."""
        if self.period_type == "WEEKLY":
            return self.raw_base / f"weekly_event_manifest_{year}.json"
        elif self.period_type == "MONTHLY":
            return self.raw_base / f"monthly_event_manifest_{year}.json"
        else:
            return self.raw_base / f"event_manifest_{year}.json"

    @property
    def manifest_path(self) -> Path:
        """하위 호환성과 단일 파일 전송 등을 위한 기본(현재 연도) 매니페스트 경로 프로퍼티."""
        current_year = date.today().year
        return self._get_manifest_path(current_year)

    def _load_manifest(self, year: int) -> dict:
        """지정된 연도의 매니페스트 파일을 로드합니다."""
        m_path = self._get_manifest_path(year)
        if not m_path.exists():
            return {}
        with open(m_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_manifest(self, manifest: dict, year: int):
        """지정된 연도의 매니페스트 파일에 메타데이터를 저장합니다."""
        m_path = self._get_manifest_path(year)
        # 상위 디렉토리 생성 확인
        m_path.parent.mkdir(parents=True, exist_ok=True)
        with open(m_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def save(self, event: WeeklyCollectionEvent) -> None:
        # ISO 주차 정보로부터 해당 주차의 월요일과 금요일 날짜를 고정 계산 (주간인 경우에만)
        if event.week > 0:
            monday = date.fromisocalendar(event.year, event.week, 1)
            friday = date.fromisocalendar(event.year, event.week, 5)
            
            start_md = monday.strftime("%m%d")
            end_md = friday.strftime("%m%d")
            filename = f"weekly_gainers_{event.year}_W{event.week:02d}_{event.month:02d}M{event.week_of_month}W_{start_md}~{end_md}.parquet"
        else:
            # 월간 수집은 시작 거래일과 종료 거래일을 기반으로 명명
            # 단, 파일명 생성을 위해 event.items가 있는 경우 첫/마지막 아이템의 날짜를 참고하거나, 
            # 혹은 event.last_trading_day를 기반으로 한 달 날짜 범위를 추정
            start_date = date(event.year, event.month, 1)
            # 월말일 계산
            if event.month == 12:
                next_month = date(event.year + 1, 1, 1)
            else:
                next_month = date(event.year, event.month + 1, 1)
            end_date = next_month - pd.Timedelta(days=1)
            
            start_md = start_date.strftime("%m%d")
            end_md = end_date.strftime("%m%d")
            filename = f"monthly_gainers_{event.year}_M{event.month:02d}_{start_md}~{end_md}.parquet"

        if event.items:
            df = pd.DataFrame([item.__dict__ for item in event.items])
            year_dir = self.base_path / str(event.year)
            year_dir.mkdir(exist_ok=True)
            
            file_path = year_dir / filename
            df.to_parquet(file_path, index=False)

        # 2. 이벤트 메타데이터 업데이트 (동적 연도별 저장)
        manifest = self._load_manifest(event.year)
        manifest[event.id] = {
            "id": event.id,
            "year": event.year,
            "week": event.week,
            "month": event.month,
            "week_of_month": event.week_of_month,
            "collected_at": event.collected_at.isoformat(),
            "day_of_week": event.day_of_week,
            "last_trading_day": event.last_trading_day.isoformat(),
            "status": event.status.value,
            "total_count": event.total_count,
            "filename": filename,
            "fingerprint": event.fingerprint
        }
        self._save_manifest(manifest, event.year)

    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        # event_id 형식 'YYYY-Www' 또는 'YYYY-Mmm'에서 연도 파싱
        try:
            year_str = event_id.split("-")[0]
            year = int(year_str)
        except (ValueError, IndexError):
            return None

        manifest = self._load_manifest(year)
        if event_id not in manifest:
            return None

        meta = manifest[event_id]
        event = WeeklyCollectionEvent(
            id=meta["id"],
            year=meta["year"],
            week=meta["week"],
            collected_at=datetime.fromisoformat(meta["collected_at"]),
            day_of_week=meta["day_of_week"],
            last_trading_day=date.fromisoformat(meta["last_trading_day"]),
            status=CollectionStatus(meta["status"]),
            total_count=meta["total_count"],
            fingerprint=meta.get("fingerprint")
        )
        # 매니페스트에서 계산된 월/주차 정보 복구
        event.month = meta.get("month", 0)
        event.week_of_month = meta.get("week_of_month", 0)

        # 저장된 파일명으로 아이템 로드
        filename = meta.get("filename")
        if not filename:
            return event

        file_path = self.base_path / str(event.year) / filename
        if file_path.exists():
            df = pd.read_parquet(file_path)
            items = []
            for _, row in df.iterrows():
                items.append(WeeklyGainerItem(
                    symbol_code=row["symbol_code"],
                    symbol_name=row["symbol_name"],
                    start_date=pd.to_datetime(row["start_date"]).date(),
                    base_price=float(row["base_price"]),
                    end_date=pd.to_datetime(row["end_date"]).date(),
                    close_price=float(row["close_price"]),
                    change=float(row["change"]),
                    change_rate=float(row["change_rate"]),
                    volume=int(row["volume"]),
                    amount=int(row["amount"])
                ))
            event.items = items

        return event

    def exists(self, event_id: str) -> bool:
        try:
            year_str = event_id.split("-")[0]
            year = int(year_str)
        except (ValueError, IndexError):
            return False

        manifest = self._load_manifest(year)
        return event_id in manifest and manifest[event_id]["status"] == CollectionStatus.COMPLETED.value

    def list_all_events(self) -> List[WeeklyCollectionEvent]:
        events = []
        
        # 연도별 매니페스트 검색 패턴
        if self.period_type == "WEEKLY":
            pattern = "weekly_event_manifest_*.json"
        elif self.period_type == "MONTHLY":
            pattern = "monthly_event_manifest_*.json"
        else:
            pattern = "event_manifest_*.json"
            
        manifest_files = list(self.raw_base.glob(pattern))
        
        # 하위 호환성: 연도별 접미사가 없는 기존 파일도 체크
        legacy_filename = "weekly_event_manifest.json" if self.period_type == "WEEKLY" else "monthly_event_manifest.json" if self.period_type == "MONTHLY" else "event_manifest.json"
        legacy_file = self.raw_base / legacy_filename
        if legacy_file.exists() and legacy_file not in manifest_files:
            manifest_files.append(legacy_file)
            
        for m_path in manifest_files:
            try:
                with open(m_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                for event_id in manifest:
                    meta = manifest[event_id]
                    events.append(WeeklyCollectionEvent(
                        id=meta["id"],
                        year=meta["year"],
                        week=meta["week"],
                        collected_at=datetime.fromisoformat(meta["collected_at"]),
                        day_of_week=meta["day_of_week"],
                        last_trading_day=date.fromisoformat(meta["last_trading_day"]),
                        status=CollectionStatus(meta["status"]),
                        total_count=meta["total_count"]
                    ))
            except Exception as e:
                print(f"[Repository] 매니페스트 파일 로드 스킵 ({m_path.name}): {e}")
                continue
                
        return events
