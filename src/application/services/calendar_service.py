import holidays
from datetime import date, timedelta

from domain.ports import CalendarPort

class CalendarService(CalendarPort):
    """거래소 휴장일을 고려하여 수집 대상 기간을 계산하는 서비스."""

    
    def __init__(self):
        self.kr_holidays = holidays.KR()
        # 근로자의 날(5월 1일)은 주식 시장 휴장이므로 강제 추가
        for y in range(2020, 2031):
            self.kr_holidays[date(y, 5, 1)] = "Labor Day"

    def get_week_dates(self, year: int, week: int):
        """특정 ISO 주차의 시작일(월)과 종료일(금)을 반환합니다."""
        # 해당 주차의 월요일 찾기
        first_day = date(year, 1, 4)  # ISO 주차의 기준일 (1월 4일은 항상 첫 주에 포함됨)
        first_monday = first_day - timedelta(days=first_day.weekday())
        target_monday = first_monday + timedelta(weeks=week - 1)
        target_friday = target_monday + timedelta(days=4)
        
        return target_monday, target_friday

    def get_last_trading_day(self, target_date: date) -> date:
        """주어진 날짜 이전의 가장 최근 영업일을 반환합니다."""
        curr = target_date
        while curr in self.kr_holidays or curr.weekday() >= 5:
            curr -= timedelta(days=1)
        return curr

    def get_first_trading_day(self, target_date: date) -> date:
        """주어진 날짜 이후의 가장 가까운 영업일을 반환합니다."""
        curr = target_date
        while curr in self.kr_holidays or curr.weekday() >= 5:
            curr += timedelta(days=1)
        return curr
