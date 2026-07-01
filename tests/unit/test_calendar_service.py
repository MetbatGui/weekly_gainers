from datetime import date
import pytest
from application.services.calendar_service import CalendarService

def test_future_labor_day_evaluation():
    """미래 연도인 2035년 근로자의 날(5월 1일)이 정상적으로 거래소 휴장일로 분류되는지 검증"""
    calendar = CalendarService()
    
    # 2035년 5월 1일 (목요일)
    labor_day_2035 = date(2035, 5, 1)
    
    # 주말이 아니지만 근로자의 날이므로 휴장일이어야 함
    assert calendar.is_holiday(labor_day_2035) is True

def test_trading_range_with_holidays_in_week():
    """주차 내에 휴장일(근로자의 날 금요일)이 포함된 경우, 첫 영업일과 마지막 영업일 범위 탐색 검증"""
    calendar = CalendarService()
    
    # 2026-04-27 (월) ~ 2026-05-01 (금 - 근로자의 날 휴장)
    week_start = date(2026, 4, 27)
    week_end = date(2026, 5, 1)
    
    first_trading, last_trading = calendar.get_trading_range_in_period(week_start, week_end)
    
    assert first_trading == date(2026, 4, 27)
    assert last_trading == date(2026, 4, 30)  # 5/1일 휴장으로 목요일로 축소

def test_trading_range_in_month():
    """한 달(1일~31일) 전체 범위에서 첫 영업일과 마지막 영업일 범위 탐색 검증 (2026년 5월)"""
    calendar = CalendarService()
    
    # 2026년 5월: 1일(금) 근로자의 날 휴장, 5일(화) 어린이날 휴장, 25일(월) 석가탄신일 대체공휴일 휴장
    month_start = date(2026, 5, 1)
    month_end = date(2026, 5, 31)
    
    first_trading, last_trading = calendar.get_trading_range_in_period(month_start, month_end)
    
    assert first_trading == date(2026, 5, 4)   # 5/1일 휴장이므로 다음 월요일인 5/4일 시작
    assert last_trading == date(2026, 5, 29)  # 30, 31일(주말) 제외한 마지막 영업일인 29일 종료

def test_mid_week_holiday_range():
    """주차 중간에 수요일 휴장일(2026년 6월 3일 지방선거)이 있는 경우 첫 영업일(월)과 마지막 영업일(금)이 올바르게 탐색되는지 검증"""
    calendar = CalendarService()
    
    # 2026-06-01 (월) ~ 2026-06-05 (금) - 6/3일 수요일 휴장
    week_start = date(2026, 6, 1)
    week_end = date(2026, 6, 5)
    
    first_trading, last_trading = calendar.get_trading_range_in_period(week_start, week_end)
    
    assert first_trading == date(2026, 6, 1)
    assert last_trading == date(2026, 6, 5)   # 중간 휴장과 무관하게 첫일/마지막일은 월, 금이 됨
