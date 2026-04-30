from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import List, Optional

class CollectionStatus(Enum):
    """주간 수집 작업의 상태를 정의하는 열거형 클래스.

    Attributes:
        PENDING: 수집 대기 중
        IN_PROGRESS: 수집 진행 중
        COMPLETED: 수집 완료
        FAILED: 수집 실패
    """
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class WeeklyGainerItem:
    """개별 종목의 주간 등락 데이터를 담는 데이터 클래스.

    Attributes:
        symbol_code (str): 종목코드 (예: '005930')
        symbol_name (str): 종목명 (예: '삼성전자')
        start_date (date): 주간 시작일 (해당 주의 첫 번째 개장일)
        base_price (float): 기준가 (전주 마지막 개장일 종가 혹은 해당 주 시가)
        end_date (date): 주간 종료일 (해당 주의 마지막 개장일)
        close_price (float): 종료일 종가
        change (float): 전주 대비 등락폭 (종가 - 기준가)
        change_rate (float): 등락률 (단위: %)
        volume (int): 주간 누적 거래량
        amount (int): 주간 누적 거래대금
    """
    symbol_code: str
    symbol_name: str
    start_date: date
    base_price: float
    end_date: date
    close_price: float
    change: float
    change_rate: float
    volume: int
    amount: int


@dataclass
class WeeklyCollectionEvent:
    """주간 수집 이벤트 및 전체 요약 데이터를 관리하는 엔티티.

    Attributes:
        id (str): 주차 식별자 (형식: 'YYYY-Www', 예: '2026-W18')
        year (int): 연도
        week (int): ISO 주차 번호
        month (int): 해당 주차가 속한 월 (과반 로직 적용)
        week_of_month (int): 해당 월의 몇 번째 주인지 (과반 로직 적용)
        collected_at (datetime): 수집이 수행된 실제 일시
        day_of_week (str): 수집 시점의 요일 (예: 'Friday')
        last_trading_day (date): 해당 주의 실제 마지막 개장일
        status (CollectionStatus): 수집 진행 상태
        items (List[WeeklyGainerItem]): 해당 주차에 수집된 상위 등락 종목 리스트 (등락률 20% 이상)
        total_count (int): 해당 주차의 시장 전체 상장 종목 수
    """
    id: str
    year: int
    week: int
    collected_at: datetime
    day_of_week: str
    last_trading_day: date
    month: int = 0
    week_of_month: int = 0
    status: CollectionStatus = CollectionStatus.PENDING
    items: List[WeeklyGainerItem] = field(default_factory=list)
    total_count: int = 0

    def __post_init__(self):
        """데이터 생성 후 요일 및 월별 주차 정보를 자동 계산하여 고정합니다."""
        if not self.day_of_week and self.collected_at:
            self.day_of_week = self.collected_at.strftime("%A")

        # 과반 로직(ISO 8601) 기반 월 및 월별 주차 계산
        # 해당 주의 목요일을 기준으로 달을 결정함
        thursday = self.last_trading_day + timedelta(days=(3 - self.last_trading_day.weekday()))
        self.month = thursday.month
        
        # 해당 월의 몇 번째 목요일인지 계산
        count = 0
        temp = date(thursday.year, thursday.month, 1)
        while temp <= thursday:
            if temp.weekday() == 3: # Thursday
                count += 1
            temp += timedelta(days=1)
        self.week_of_month = count
