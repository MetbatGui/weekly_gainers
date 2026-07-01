import os
import json
import pandas as pd
from typing import Optional, List
from datetime import datetime, date
from pathlib import Path

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from domain.ports import ReportStoragePort

class ParquetWeeklyGainerRepository(ReportStoragePort):
    """Parquet 파일을 사용하여 주간 등락률 데이터를 저장하는 구현체.
    
    데이터 구조:
    - {base_path}/{year}/{event_id}.parquet : 개별 종목 데이터
    - {base_path}/event_manifest.json : 이벤트 메타데이터(상태, 수집일 등) 관리
    """

    def __init__(self, base_path: str = "data/weekly_gainers", period_type: Optional[str] = None):
        raw_base = Path(base_path)
        if period_type == "WEEKLY":
            self.manifest_path = raw_base / "weekly_event_manifest.json"
            self.base_path = raw_base / "weekly"
        elif period_type == "MONTHLY":
            self.manifest_path = raw_base / "monthly_event_manifest.json"
            self.base_path = raw_base / "monthly"
        else:
            self.manifest_path = raw_base / "event_manifest.json"
            self.base_path = raw_base
            
        self._ensure_directories()

    def _ensure_directories(self):
        """데이터 저장 경로가 없으면 생성합니다."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> dict:
        """이벤트 메타데이터가 담긴 매니페스트 파일을 로드합니다."""
        if not self.manifest_path.exists():
            return {}
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_manifest(self, manifest: dict):
        """이벤트 메타데이터를 매니페스트 파일에 저장합니다."""
        with open(self.manifest_path, "w", encoding="utf-8") as f:
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
            filename = f"monthly_gainers_{event.year}_{event.month:02d}월.parquet"

        if event.items:
            df = pd.DataFrame([item.__dict__ for item in event.items])
            year_dir = self.base_path / str(event.year)
            year_dir.mkdir(exist_ok=True)
            
            file_path = year_dir / filename
            df.to_parquet(file_path, index=False)

        # 2. 이벤트 메타데이터 업데이트
        manifest = self._load_manifest()
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
        self._save_manifest(manifest)

    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        manifest = self._load_manifest()
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
        manifest = self._load_manifest()
        return event_id in manifest and manifest[event_id]["status"] == CollectionStatus.COMPLETED.value

    def list_all_events(self) -> List[WeeklyCollectionEvent]:
        manifest = self._load_manifest()
        events = []
        for event_id in manifest:
            # 리스트 조회 시에는 성능을 위해 아이템은 로드하지 않고 메타데이터만 구성
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
        return events
