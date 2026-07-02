import os
import io
import json
import tempfile
import pandas as pd
from typing import Optional, List, Set
from datetime import datetime, date
from pathlib import Path

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem, CollectionStatus
from domain.ports import ReportStoragePort, CloudUploadPort

class GoogleDriveReportStorageAdapter(ReportStoragePort):
    """Google Drive를 단일진실공급원(SSOT)으로 사용하여 Excel 리포트 기반의 주간/월간 수집 이력을 저장 및 로드하는 어댑터."""

    def __init__(self, uploader: CloudUploadPort, period_type: Optional[str] = None):
        self.gdrive = uploader
        self.period_type = period_type

    def _safe_remove(self, file_path: str) -> bool:
        """Windows 환경의 파일 락을 방어하며 안전하게 임시 파일을 삭제합니다."""
        import time
        for _ in range(5):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return True
            except PermissionError:
                time.sleep(0.1)
        return False

    def _get_manifest_name(self, year: int) -> str:
        """지정된 연도의 매니페스트 파일명을 반환합니다."""
        if self.period_type == "WEEKLY":
            return f"weekly_event_manifest_{year}.json"
        elif self.period_type == "MONTHLY":
            return f"monthly_event_manifest_{year}.json"
        else:
            return f"event_manifest_{year}.json"

    def _load_manifest(self, year: int) -> dict:
        """구글 드라이브로부터 해당 연도의 매니페스트를 다운로드하여 파싱합니다."""
        try:
            filename = self._get_manifest_name(year)
            # {year}/ 폴더 하위에서 매니페스트 파일 로드
            content_bytes = self.gdrive.download_file(remote_path=str(year), filename=filename)
            if not content_bytes:
                return {}
            return json.loads(content_bytes.decode("utf-8"))
        except Exception as e:
            print(f"[GDriveRepo] 매니페스트 로드 실패 ({year}): {e}")
            return {}

    def _save_manifest(self, manifest: dict, year: int) -> bool:
        """구글 드라이브에 매니페스트를 업로드합니다. 로컬에는 임시 파일만 사용합니다."""
        filename = self._get_manifest_name(year)
        json_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        
        # Windows 호환 임시 파일 처리 (파일 디스크립터를 즉시 닫음)
        import tempfile
        fd, tmp_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        try:
            with open(tmp_path, "wb") as f:
                f.write(json_bytes)
                
            # 구글 드라이브 {year}/ 폴더 하위로 업로드
            success = self.gdrive.upload_file(
                local_path=tmp_path,
                remote_path=str(year),
                filename=filename,
                mimetype="application/json"
            )
            return success
        finally:
            self._safe_remove(tmp_path)

    def save(self, event: WeeklyCollectionEvent) -> None:
        # 1. Excel 파일명 도출 (Parquet는 업로드하지 않고 매니페스트 파일명으로만 사용)
        if event.week > 0:
            monday = date.fromisocalendar(event.year, event.week, 1)
            friday = date.fromisocalendar(event.year, event.week, 5)
            
            start_md = monday.strftime("%m%d")
            end_md = friday.strftime("%m%d")
            filename = f"weekly_gainers_{event.year}_W{event.week:02d}_{event.month:02d}M{event.week_of_month}W_{start_md}~{end_md}.xlsx"
        else:
            start_date = date(event.year, event.month, 1)
            if event.month == 12:
                next_month = date(event.year + 1, 1, 1)
            else:
                next_month = date(event.year, event.month + 1, 1)
            end_date = next_month - pd.Timedelta(days=1)
            
            start_md = start_date.strftime("%m%d")
            end_md = end_date.strftime("%m%d")
            filename = f"monthly_gainers_{event.year}_M{event.month:02d}_{start_md}~{end_md}.xlsx"

        # 2. 드라이브 상의 매니페스트 업데이트 및 업로드
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
        event.month = meta.get("month", 0)
        event.week_of_month = meta.get("week_of_month", 0)

        # 3. 저장된 Excel 파일이 존재하면 드라이브로부터 다운로드하여 복원 (전체 등락종목 시트 파싱)
        filename = meta.get("filename")
        if filename:
            # 주간/월간 엑셀 리포트 원격 경로: f"{year}/{month:02d}월"
            remote_path = f"{event.year}/{event.month:02d}월"
            excel_bytes = self.gdrive.download_file(remote_path=remote_path, filename=filename)
            
            if excel_bytes:
                # pandas excel 엔진은 openpyxl을 사용
                df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="전체_등락종목")
                
                # 한글 컬럼 -> 도메인 필드 매핑 딕셔너리
                col_mapping = {
                    '종목코드': 'symbol_code',
                    '종목명': 'symbol_name',
                    '시작일': 'start_date',
                    '기준가': 'base_price',
                    '종료일': 'end_date',
                    '종가': 'close_price',
                    '대비': 'change',
                    '등락률': 'change_rate',
                    '거래량': 'volume',
                    '거래대금': 'amount'
                }
                df.rename(columns=col_mapping, inplace=True)
                
                # 엑셀 데이터 타입을 도메인 모델에 맞게 클렌징 캐스팅하여 복원
                items = []
                for _, row in df.iterrows():
                    # 콤마(,) 제거 및 캐스팅 처리 함수
                    def clean_float(val) -> float:
                        if pd.isna(val):
                            return 0.0
                        return float(str(val).replace(",", ""))

                    def clean_int(val) -> int:
                        if pd.isna(val):
                            return 0
                        return int(str(val).replace(",", ""))
                    
                    # 종목코드 복원 시 앞자리 0 누락 방어
                    sym_code = str(row["symbol_code"]).strip()
                    if len(sym_code) < 6 and sym_code.isdigit():
                        sym_code = sym_code.zfill(6)

                    items.append(WeeklyGainerItem(
                        symbol_code=sym_code,
                        symbol_name=str(row["symbol_name"]),
                        start_date=pd.to_datetime(row["start_date"]).date(),
                        base_price=clean_float(row["base_price"]),
                        end_date=pd.to_datetime(row["end_date"]).date(),
                        close_price=clean_float(row["close_price"]),
                        change=clean_float(row["change"]),
                        change_rate=clean_float(row["change_rate"]),
                        volume=clean_int(row["volume"]),
                        amount=clean_int(row["amount"])
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
        
        # 4. 구글 드라이브 상에서 연도별 매니페스트 검색 및 로드
        drive_service = getattr(self.gdrive, "drive_service", None)
        
        manifest_files = []
        if drive_service:
            if self.period_type == "WEEKLY":
                pattern = "weekly_event_manifest_"
            elif self.period_type == "MONTHLY":
                pattern = "monthly_event_manifest_"
            else:
                pattern = "event_manifest_"
                
            try:
                query = f"name contains '{pattern}' and name contains '.json' and trashed = false"
                results = drive_service.files().list(q=query, fields="files(id, name)").execute()
                manifest_files = results.get('files', [])
            except Exception as e:
                print(f"[GDriveRepo] 드라이브 매니페스트 검색 오류: {e}")
                manifest_files = []
        else:
            uploaded_files = getattr(self.gdrive, "uploaded_files", [])
            for item in uploaded_files:
                if len(item) >= 3:
                    filename, remote_path, content = item[0], item[1], item[2]
                    # StubUploader가 upload_file로 가로채 메모리에 bytes 형태로 보관한 json 파싱
                    if filename.endswith(".json") and isinstance(content, bytes):
                        try:
                            data = json.loads(content.decode("utf-8"))
                            for event_id, meta in data.items():
                                events.append(WeeklyCollectionEvent(
                                    id=meta["id"], year=meta["year"], week=meta["week"],
                                    collected_at=datetime.fromisoformat(meta["collected_at"]),
                                    day_of_week=meta["day_of_week"],
                                    last_trading_day=date.fromisoformat(meta["last_trading_day"]),
                                    status=CollectionStatus(meta["status"]), total_count=meta["total_count"]
                                ))
                        except Exception:
                            pass
            return events

        for file_info in manifest_files:
            try:
                filename = file_info['name']
                year_str = filename.split("_")[-1].replace(".json", "")
                year = int(year_str)
                
                manifest = self._load_manifest(year)
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
                print(f"[GDriveRepo] 드라이브 파일 로드 오류 ({file_info.get('name')}): {e}")
                continue

        return events
