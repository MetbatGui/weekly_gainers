import logging
import requests
import time
import json
from datetime import date
from typing import List, Optional, Set
from pathlib import Path
from domain.models import WeeklyGainerItem
from domain.ports import StockDataPort

import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class KrxStockDataAdapter(StockDataPort):
    """KRX API를 호출하여 주간 등락 데이터를 수집하는 어댑터.
    
    Attributes:
        BASE_URL (str): KRX 정보데이터시스템 기본 URL
    """
    
    BASE_URL = "https://data.krx.co.kr"

    def __init__(self, cache_dir: Optional[str] = None):
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
        
        self.cache_dir = Path(cache_dir) if cache_dir else Path("data/weekly_gainers/cache")
        self.username = os.getenv("KRX_USERNAME")
        self.password = os.getenv("KRX_PASSWORD")
        self.is_logged_in = False
        self._login()

    def _login(self) -> None:
        """KRX 정보데이터시스템 로그인 및 세션 쿠키 갱신"""
        if not self.username or not self.password:
            logger.warning("[Adapter:KRX] 경고: KRX_USERNAME 또는 KRX_PASSWORD가 설정되지 않았습니다. 비로그인 모드로 진행합니다.")
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
                logger.info(f"[Adapter:KRX] 로그인 성공 (회원: {self.username})")
                self.is_logged_in = True
            else:
                logger.warning(f"[Adapter:KRX] 로그인 실패: {data}")
                self.is_logged_in = False
                
            # 기본 필수 쿠키 강제 세팅
            self.session.cookies.set('mdc.client_session', 'true', domain='data.krx.co.kr')
            self.session.cookies.set('lang', 'ko_KR', domain='data.krx.co.kr')
            
        except Exception as e:
            logger.error(f"[Adapter:KRX] 로그인 중 예외 발생: {e}")
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
        """하위 호환성을 유지하기 위한 fetch_period_data의 에일리어스 메서드입니다."""
        return self.fetch_period_data(start_date, end_date, retry)

    def fetch_period_data(self, start_date: date, end_date: date, retry: bool = True) -> List[WeeklyGainerItem]:
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
                logger.info("[Adapter:KRX] 세션 만료 감지, 재로그인 시도...")
                self._login()
                return self.fetch_weekly_data(start_date, end_date, retry=False)

            if response.status_code != 200:
                logger.warning(f"[Adapter:KRX] HTTP 에러 발생: {response.status_code}")
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
            logger.error(f"[Adapter:KRX] 예외 발생: {e}")
            return []

    def fetch_index_components(self, index_code: str, target_date: date, retry: bool = True) -> Set[str]:
        """지정된 지수(index_code)의 구성종목 코드 세트를 조회합니다. (파일 기반 캐시 적용)"""
        # 캐시 검사
        cache_key = f"{index_code.upper().replace('_', '')}_{target_date.strftime('%Y%m%d')}"
        cache_file = self.cache_dir / f"index_components_{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                
                # 유효기간 확인:
                # 1) 과거 거래일(target_date < today): 캐시 데이터가 존재하면 영구 유효
                # 2) 오늘/미래 거래일: 생성일이 오늘과 동일한 경우에만 유효
                today = date.today()
                today_str = today.isoformat()
                cached_components = cache_data.get("components", [])

                is_valid = False
                if cached_components:
                    if target_date < today:
                        is_valid = True
                    elif cache_data.get("created_at") == today_str:
                        is_valid = True

                if is_valid:
                    logger.info(f"[Adapter:KRX] {index_code} {target_date} 구성종목 캐시 히트 (생성일: {cache_data.get('created_at')})")
                    return set(cached_components)
                else:
                    logger.info(f"[Adapter:KRX] {index_code} {target_date} 캐시 만료됨 (생성일: {cache_data.get('created_at')}, 오늘: {today_str})")
            except Exception as e:
                logger.warning(f"[Adapter:KRX] 캐시 파일 읽기 실패: {e}")

        # 1. 지수 코드에 따른 파라미터 매핑
        code_upper = index_code.upper().replace("_", "")
        if code_upper in ("KOSPI200", "KOSPI 200"):
            ind_idx = "1"
            ind_idx2 = "028"
            idx_name = "코스피 200"
        elif code_upper in ("KOSDAQ150", "KOSDAQ 150"):
            ind_idx = "2"
            ind_idx2 = "203"
            idx_name = "코스닥 150"
        else:
            raise ValueError(f"[Adapter:KRX] 지원하지 않는 지수 코드입니다: {index_code}")

        url = f"{self.BASE_URL}/comm/bldAttendant/getJsonData.cmd"
        payload = {
            'bld': 'dbms/MDC/STAT/standard/MDCSTAT00601',
            'locale': 'ko_KR',
            'tboxindIdx_finder_equidx0_1': idx_name,
            'indIdx': ind_idx,
            'indIdx2': ind_idx2,
            'codeNmindIdx_finder_equidx0_1': idx_name,
            'param1indIdx_finder_equidx0_1': '',
            'trdDd': target_date.strftime('%Y%m%d'),
            'money': '3',
            'csvxls_isNo': 'false',
        }

        try:
            response = self.session.post(url, data=payload, timeout=30)
            
            # 세션 만료 처리
            if "LOGOUT" in response.text and retry:
                logger.info("[Adapter:KRX] 세션 만료 감지, 재로그인 시도...")
                self._login()
                return self.fetch_index_components(index_code, target_date, retry=False)

            if response.status_code != 200:
                logger.warning(f"[Adapter:KRX] 지수 구성종목 조회 HTTP 에러: {response.status_code}")
                return set()
            
            data = response.json()
            rows = data.get('output', []) or data.get('OutBlock_1', [])
            
            # 각 종목코드(ISU_SRT_CD)를 추출하여 세트로 반환
            components = {row.get('ISU_SRT_CD') for row in rows if row.get('ISU_SRT_CD')}
            
            # 캐시 저장
            if components:
                try:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    today_str = date.today().isoformat()
                    cache_data = {
                        "created_at": today_str,
                        "components": list(components)
                    }
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=2, ensure_ascii=False)
                    logger.info(f"[Adapter:KRX] {index_code} {target_date} 구성종목 캐시 저장 완료 (생성일: {today_str})")
                except Exception as e:
                    logger.warning(f"[Adapter:KRX] 캐시 파일 저장 실패: {e}")

            return components

        except Exception as e:
            logger.error(f"[Adapter:KRX] 지수 구성종목 조회 예외 발생: {e}")
            return set()


