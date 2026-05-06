import requests
import time
from datetime import date
from typing import List, Optional
from domain.models import WeeklyGainerItem

import os
from dotenv import load_dotenv

load_dotenv()

class KrxStockDataAdapter:
    """KRX API를 호출하여 주간 등락 데이터를 수집하는 어댑터.
    
    Attributes:
        BASE_URL (str): KRX 정보데이터시스템 기본 URL
    """
    
    BASE_URL = "https://data.krx.co.kr"

    def __init__(self):
        self.session = requests.Session()
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': self.BASE_URL,
            'Referer': f'{self.BASE_URL}/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        self.username = os.getenv("KRX_USERNAME")
        self.password = os.getenv("KRX_PASSWORD")
        self.is_logged_in = False
        self._login()

    def _login(self) -> None:
        """KRX 정보데이터시스템 로그인 및 세션 쿠키 갱신"""
        if not self.username or not self.password:
            print("[Adapter:KRX] 경고: KRX_USERNAME 또는 KRX_PASSWORD가 설정되지 않았습니다. 비로그인 모드로 진행합니다.")
            return

        login_page = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001.cmd"
        login_jsp = f"{self.BASE_URL}/contents/MDC/COMS/client/view/login.jsp?site=mdc"
        login_url = f"{self.BASE_URL}/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
        
        try:
            # 1 & 2. 초기 세션 발급
            self.session.get(login_page, timeout=15)
            self.session.get(login_jsp, headers={"Referer": login_page}, timeout=15)
            
            payload = {
                "mbrNm": "", "telNo": "", "di": "", "certType": "",
                "mbrId": self.username, "pw": self.password,
            }
            
            # 3. 로그인 POST
            resp = self.session.post(login_url, data=payload, headers={"Referer": login_page}, timeout=15)
            data = resp.json()
            error_code = data.get("_error_code", "")
            
            # 4. CD011 중복 로그인 처리
            if error_code == "CD011":
                payload["skipDup"] = "Y"
                resp = self.session.post(login_url, data=payload, headers={"Referer": login_page}, timeout=15)
                data = resp.json()
                error_code = data.get("_error_code", "")
                
            if error_code == "CD001":
                print(f"[Adapter:KRX] 로그인 성공 (회원: {self.username})")
                self.is_logged_in = True
            else:
                print(f"[Adapter:KRX] 로그인 실패: {data}")
                self.is_logged_in = False
                
            # 기본 필수 쿠키 강제 세팅
            self.session.cookies.set('mdc.client_session', 'true', domain='data.krx.co.kr')
            self.session.cookies.set('lang', 'ko_KR', domain='data.krx.co.kr')
            
        except Exception as e:
            print(f"[Adapter:KRX] 로그인 중 예외 발생: {e}")
            self.is_logged_in = False

    def _parse_num(self, val: str) -> float:
        """콤마가 포함된 문자열을 숫자로 변환합니다."""
        if not val:
            return 0.0
        try:
            if isinstance(val, str):
                val = val.replace(',', '')
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def fetch_weekly_data(self, start_date: date, end_date: date, retry: bool = True) -> List[WeeklyGainerItem]:
        """지정된 기간(주간)의 전종목 등락 데이터를 수집합니다."""
        url = f"{self.BASE_URL}/comm/bldAttendant/getJsonData.cmd"
        payload = {
            'bld': 'dbms/MDC/STAT/standard/MDCSTAT01602',
            'locale': 'ko_KR',
            'mktId': 'ALL',
            'strtDd': start_date.strftime('%Y%m%d'),
            'endDd': end_date.strftime('%Y%m%d'),
            'adjStkPrc_check': 'Y',
            'adjStkPrc': '2',
            'share': '1',
            'money': '1',
            'csvxls_isNo': 'false',
        }

        try:
            response = self.session.post(url, data=payload, timeout=30)
            
            # 세션 만료 처리
            if "LOGOUT" in response.text and retry:
                print("[Adapter:KRX] 세션 만료 감지, 재로그인 시도...")
                self._login()
                return self.fetch_weekly_data(start_date, end_date, retry=False)

            if response.status_code != 200:
                print(f"[Adapter:KRX] HTTP 에러 발생: {response.status_code}")
                return []
            
            data = response.json()
            rows = data.get('OutBlock_1', []) or data.get('output', [])
            
            if not rows:
                return []

            items = []
            for row in rows:
                items.append(WeeklyGainerItem(
                    symbol_code=row.get('ISU_SRT_CD'),
                    symbol_name=row.get('ISU_ABBRV'),
                    start_date=start_date,
                    base_price=self._parse_num(row.get('BAS_PRC')),
                    end_date=end_date,
                    close_price=self._parse_num(row.get('TDD_CLSPRC')),
                    change=self._parse_num(row.get('CMPPREVDD_PRC')),
                    change_rate=self._parse_num(row.get('FLUC_RT')),
                    volume=int(self._parse_num(row.get('ACC_TRDVOL'))),
                    amount=int(self._parse_num(row.get('ACC_TRDVAL')))
                ))
            
            return items

        except Exception as e:
            print(f"[Adapter:KRX] 예외 발생: {e}")
            return []
