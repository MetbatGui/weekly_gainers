from abc import ABC, abstractmethod
from datetime import date
from typing import List, Set, Optional, Tuple
import pandas as pd

from domain.models import WeeklyCollectionEvent, WeeklyGainerItem

class CalendarPort(ABC):
    """거래소 영업일 및 휴장일을 계산하는 인터페이스."""
    
    @abstractmethod
    def get_week_dates(self, year: int, week: int) -> Tuple[date, date]:
        pass

    @abstractmethod
    def get_last_trading_day(self, target_date: date) -> date:
        pass

    @abstractmethod
    def get_first_trading_day(self, target_date: date) -> date:
        pass

    @abstractmethod
    def is_holiday(self, target_date: date) -> bool:
        pass

    @abstractmethod
    def get_trading_range_in_period(self, start_date: date, end_date: date) -> Tuple[Optional[date], Optional[date]]:
        pass



class StockDataPort(ABC):
    """주식 전종목 데이터 및 지수구성종목 데이터를 수집하는 인터페이스."""

    @abstractmethod
    def fetch_period_data(self, start_date: date, end_date: date) -> List[WeeklyGainerItem]:
        pass

    @abstractmethod
    def fetch_index_components(self, index_code: str, target_date: date) -> Set[str]:
        pass


class ReportStoragePort(ABC):
    """수집 완료 데이터(Parquet) 및 매니페스트 메타데이터를 저장하는 인터페이스."""

    @abstractmethod
    def save(self, event: WeeklyCollectionEvent) -> None:
        pass

    @abstractmethod
    def get_by_id(self, event_id: str) -> Optional[WeeklyCollectionEvent]:
        pass

    @abstractmethod
    def exists(self, event_id: str) -> bool:
        pass


class CloudUploadPort(ABC):
    """생성된 엑셀 리포트 및 메가데이터 파일을 클라우드(구글 드라이브)에 업로드하는 인터페이스."""

    @abstractmethod
    def upload_excel(self, dfs: dict[str, pd.DataFrame], remote_path: str, filename: str) -> bool:
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str, filename: str, mimetype: str = 'application/octet-stream') -> bool:
        pass

