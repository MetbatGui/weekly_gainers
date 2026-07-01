from datetime import date
from unittest.mock import patch, MagicMock
import pytest

from infra.adapters.krx_adapter import KrxStockDataAdapter
from domain.models import WeeklyGainerItem

def test_fetch_period_data_success_mock():
    """Mock HTTP 응답을 활용해 KrxStockDataAdapter가 KRX 전종목 등락률 데이터를 성공적으로 조회 및 파싱하는지 검증"""
    adapter = KrxStockDataAdapter()
    
    # 임의 기간
    start_date = date(2026, 4, 27)
    end_date = date(2026, 4, 30)

    # 거래소 가짜 JSON 응답 데이터 모의 구성
    mock_response_data = {
        "OutBlock_1": [
            {
                "ISU_SRT_CD": "005930",
                "ISU_ABBRV": "삼성전자",
                "BAS_PRC": "70,000",       # BAS_PRC 콤마 포함 문자열
                "TDD_CLSPRC": "85,000",    # TDD_CLSPRC 종가
                "CMPPREVDD_PRC": "15,000", # 변동폭
                "FLUC_RT": "21.43",        # 등락률
                "ACC_TRDVOL": "100,000",   # 거래량
                "ACC_TRDVAL": "8,500,000,000" # 거래대금
            },
            {
                "ISU_SRT_CD": "000660",
                "ISU_ABBRV": "SK하이닉스",
                "BAS_PRC": "150,000",
                "TDD_CLSPRC": "180,000",
                "CMPPREVDD_PRC": "30,000",
                "FLUC_RT": "20.00",
                "ACC_TRDVOL": "50,000",
                "ACC_TRDVAL": "9,000,000,000"
            }
        ]
    }

    # requests.Session.post 메서드를 모킹
    with patch.object(adapter.session, 'post') as mock_post:
        # 모의 응답 객체 생성
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SUCCESS"
        mock_response.json.return_value = mock_response_data
        mock_post.return_value = mock_response

        # 실행
        items = adapter.fetch_period_data(start_date, end_date)

        # 1. HTTP 호출 여부 및 페이로드 검증
        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        
        # 호출 URL 검증
        assert "getJsonData.cmd" in called_args[0]
        
        # 페이로드 데이터 검증
        payload = called_kwargs.get('data', {})
        assert payload.get('bld') == 'dbms/MDC/STAT/standard/MDCSTAT01602'
        assert payload.get('strtDd') == '20260427'
        assert payload.get('endDd') == '20260430'
        assert payload.get('mktId') == 'ALL'

        # 2. 파싱된 데이터(도메인 모델) 검증
        assert len(items) == 2
        
        # 첫 번째 종목(삼성전자) 검증
        assert isinstance(items[0], WeeklyGainerItem)
        assert items[0].symbol_code == "005930"
        assert items[0].symbol_name == "삼성전자"
        assert items[0].base_price == 70000.0
        assert items[0].close_price == 85000.0
        assert items[0].change == 15000.0
        assert items[0].change_rate == 21.43
        assert items[0].volume == 100000
        assert items[0].amount == 8500000000

        # 두 번째 종목(SK하이닉스) 검증
        assert items[1].symbol_name == "SK하이닉스"
        assert items[1].change_rate == 20.00

def test_fetch_period_data_session_expired_retry_mock():
    """세션 만료(LOGOUT) 감지 시 자동으로 재로그인(fetch_weekly_data 재시도)하는 흐름 검증"""
    adapter = KrxStockDataAdapter()
    start_date = date(2026, 4, 27)
    end_date = date(2026, 4, 30)

    # 첫 번째 post 호출은 "LOGOUT" 반환, 두 번째 post 호출은 정상 데이터 반환 모킹
    with patch.object(adapter.session, 'post') as mock_post, \
         patch.object(adapter, '_login') as mock_login:
        
        # 첫 번째 호출 응답 (세션 만료)
        mock_resp_logout = MagicMock()
        mock_resp_logout.status_code = 200
        mock_resp_logout.text = "LOGOUT DETECTED"
        
        # 두 번째 호출 응답 (성공 데이터)
        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.text = "SUCCESS"
        mock_resp_success.json.return_value = {
            "OutBlock_1": [
                {
                    "ISU_SRT_CD": "005930",
                    "ISU_ABBRV": "삼성전자",
                    "BAS_PRC": "70,000",
                    "TDD_CLSPRC": "85,000",
                    "CMPPREVDD_PRC": "15,000",
                    "FLUC_RT": "21.43",
                    "ACC_TRDVOL": "100,000",
                    "ACC_TRDVAL": "8,500,000,000"
                }
            ]
        }
        
        # mock_post.side_effect를 설정하여 순차적으로 반환
        mock_post.side_effect = [mock_resp_logout, mock_resp_success]

        # 실행
        items = adapter.fetch_period_data(start_date, end_date)

        # 검증: _login()이 한 번 호출되었고, post 호출이 총 2번 수행되었는지 확인
        mock_login.assert_called_once()
        assert mock_post.call_count == 2
        assert len(items) == 1
        assert items[0].symbol_name == "삼성전자"
