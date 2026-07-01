import requests
import time
from datetime import date, timedelta
from typing import Set, Tuple, Optional

from domain.ports import CalendarPort

class CalendarService(CalendarPort):
    """거래소 휴장일을 고려하여 수집 대상 기간을 계산하는 서비스."""
    
    def __init__(self):
        self._holidays_cache = {}

    def _fetch_krx_holidays(self, year: str) -> Set[date]:
        """KRX OPN99000001.jspx API를 호출하여 휴장일 집합을 반환합니다."""
        if year in self._holidays_cache:
            return self._holidays_cache[year]
            
        url_otp = "https://open.krx.co.kr/contents/COM/GenerateOTP.jspx"
        url_data = "https://open.krx.co.kr/contents/OPN/99/OPN99000001.jspx"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36',
            'Referer': 'https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp',
        }

        try:
            # 1. OTP 발급
            params = {
                'bld': 'MKD/01/0110/01100305/mkd01100305_01',
                'name': 'form',
                '_': int(time.time() * 1000)
            }
            resp_otp = requests.get(url_otp, params=params, headers=headers)
            if resp_otp.status_code != 200:
                return set()
            otp = resp_otp.text.strip()

            # 2. 데이터 조회
            payload = {
                'search_bas_yy': year,
                'gridTp': 'KRX',
                'pagePath': '/contents/MKD/01/0110/01100305/MKD01100305.jsp',
                'code': otp
            }
            resp_data = requests.post(url_data, data=payload, headers=headers)
            if resp_data.status_code != 200:
                return set()

            holidays_set = set()
            result = resp_data.json()
            rows = result.get('block1', [])
            for row in rows:
                date_str = row.get('calnd_dd')
                if date_str:
                    y, m, d = map(int, date_str.split('-'))
                    holidays_set.add(date(y, m, d))
            
            self._holidays_cache[year] = holidays_set
            return holidays_set
        except Exception as e:
            print(f"[CalendarService] {year}년 KRX 휴장일 조회 중 예외 발생: {e}")
            return set()

    def is_holiday(self, target_date: date) -> bool:
        """주말이거나 KRX 고시 휴장일이면 True 반환"""
        if target_date.weekday() >= 5:
            return True
        # 근로자의 날(5월 1일)은 항상 주식 시장 휴장이므로 법적 보정
        if target_date.month == 5 and target_date.day == 1:
            return True
        year_str = str(target_date.year)
        holidays_set = self._fetch_krx_holidays(year_str)
        return target_date in holidays_set

    def get_week_dates(self, year: int, week: int) -> Tuple[date, date]:
        """특정 ISO 주차의 시작일(월)과 종료일(금)을 반환합니다."""
        first_day = date(year, 1, 4)
        first_monday = first_day - timedelta(days=first_day.weekday())
        target_monday = first_monday + timedelta(weeks=week - 1)
        target_friday = target_monday + timedelta(days=4)
        return target_monday, target_friday

    def get_last_trading_day(self, target_date: date) -> date:
        """주어진 날짜 이전의 가장 최근 영업일을 반환합니다."""
        curr = target_date
        while True:
            if self.is_holiday(curr):
                curr -= timedelta(days=1)
                continue
            return curr

    def get_first_trading_day(self, target_date: date) -> date:
        """주어진 날짜 이후의 가장 첫 영업일을 반환합니다."""
        curr = target_date
        while True:
            if self.is_holiday(curr):
                curr += timedelta(days=1)
                continue
            return curr

    def get_trading_range_in_period(self, start_date: date, end_date: date) -> Tuple[Optional[date], Optional[date]]:
        """지정된 임의 기간 내에서 휴장일을 제외한 첫 거래일과 마지막 거래일을 반환합니다."""
        trading_days = []
        curr = start_date
        while curr <= end_date:
            if not self.is_holiday(curr):
                trading_days.append(curr)
            curr += timedelta(days=1)
            
        if not trading_days:
            return None, None
            
        return trading_days[0], trading_days[-1]
