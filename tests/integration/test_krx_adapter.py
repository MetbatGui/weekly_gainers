from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pytest
import json

from infra.adapters.krx_adapter import KrxStockDataAdapter
from domain.models import WeeklyGainerItem

def test_fetch_period_data_success_mock(tmp_path):
    """Mock HTTP 응답을 활용해 KrxStockDataAdapter가 KRX 전종목 등락률 데이터를 성공적으로 조회 및 파싱하는지 검증"""
    adapter = KrxStockDataAdapter(cache_dir=str(tmp_path / "cache"))
    
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

def test_fetch_period_data_session_expired_retry_mock(tmp_path):
    """세션 만료(LOGOUT) 감지 시 자동으로 재로그인(fetch_weekly_data 재시도)하는 흐름 검증"""
    adapter = KrxStockDataAdapter(cache_dir=str(tmp_path / "cache"))
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

def test_fetch_index_components_success_mock(tmp_path):
    """Mock HTTP 응답을 활용해 KrxStockDataAdapter가 지수 구성종목을 성공적으로 조회 및 파싱하는지 검증"""
    adapter = KrxStockDataAdapter(cache_dir=str(tmp_path / "cache"))
    target_date = date(2026, 6, 30)

    mock_response_data = {
        "output": [
            {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"},
            {"ISU_SRT_CD": "000660", "ISU_ABBRV": "SK하이닉스"}
        ]
    }

    with patch.object(adapter.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SUCCESS"
        mock_response.json.return_value = mock_response_data
        mock_post.return_value = mock_response

        # 코스피 200
        components = adapter.fetch_index_components("KOSPI_200", target_date)

        mock_post.assert_called_once()
        called_args, called_kwargs = mock_post.call_args
        
        # 페이로드 검증
        payload = called_kwargs.get('data', {})
        assert payload.get('bld') == 'dbms/MDC/STAT/standard/MDCSTAT00601'
        assert payload.get('indIdx') == '1'
        assert payload.get('indIdx2') == '028'
        assert payload.get('tboxindIdx_finder_equidx0_1') == '코스피 200'

        # 결과 검증
        assert len(components) == 2
        assert components == {"005930", "000660"}


def test_fetch_index_components_cache_hit_mock(tmp_path):
    """지수 구성종목 조회 시 캐시가 존재하고 유효한 경우 캐시에서 로드하여 API 호출을 차단하는지 검증"""
    adapter = KrxStockDataAdapter(cache_dir=str(tmp_path / "cache"))
    target_date = date(2026, 6, 30)

    mock_response_data = {
        "output": [
            {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"}
        ]
    }

    with patch.object(adapter.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SUCCESS"
        mock_response.json.return_value = mock_response_data
        mock_post.return_value = mock_response

        # 1. 첫 번째 조회: 캐시가 없으므로 API 호출 발생 및 캐시 저장
        components1 = adapter.fetch_index_components("KOSPI_200", target_date)
        assert mock_post.call_count == 1
        assert components1 == {"005930"}

        # 2. 두 번째 조회: 동일한 날짜/지수이므로 캐시 히트 발생. API 호출 증가하지 않음
        components2 = adapter.fetch_index_components("KOSPI_200", target_date)
        assert mock_post.call_count == 1  # 여전히 1회
        assert components2 == {"005930"}


def test_fetch_index_components_cache_expired_mock(tmp_path):
    """지수 구성종목 캐시 파일이 존재하지만 생성일이 오늘이 아닌 경우 캐시가 만료되고 새로 API를 호출하는지 검증"""
    adapter = KrxStockDataAdapter(cache_dir=str(tmp_path / "cache"))
    target_date = date.today()

    # 1. 인위적으로 어제 날짜로 만료된 캐시 생성 (오늘자 대상)
    import json
    adapter.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = adapter.cache_dir / f"index_components_KOSPI200_{target_date.strftime('%Y%m%d')}.json"
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    cache_data = {
        "created_at": yesterday_str,
        "components": ["000660"]  # 어제 기준 구성종목
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f)

    # 새로운 API 결과는 "005930" (오늘 새로 가져오는 구성종목)
    mock_response_data = {
        "output": [
            {"ISU_SRT_CD": "005930", "ISU_ABBRV": "삼성전자"}
        ]
    }

    with patch.object(adapter.session, 'post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "SUCCESS"
        mock_response.json.return_value = mock_response_data
        mock_post.return_value = mock_response

        # 2. 조회 수행: 캐시가 만료되었으므로 API를 새로 찔러 가져와야 함
        components = adapter.fetch_index_components("KOSPI_200", target_date)
        assert mock_post.call_count == 1
        assert components == {"005930"}  # 캐시 데이터인 000660이 아닌 새로 수집한 005930이 되어야 함

        # 3. 새로운 캐시 파일 검사 (오늘 날짜로 갱신되었는지 확인)
        with open(cache_file, "r", encoding="utf-8") as f:
            new_cache_data = json.load(f)
        assert new_cache_data["created_at"] == date.today().isoformat()
        assert set(new_cache_data["components"]) == {"005930"}


def test_fetch_index_components_past_date_cache_hit_mock(tmp_path):
    """과거 거래일(target_date < today)의 캐시는 생성일이 오늘이 아니어도 만료되지 않고 히트하는지 검증"""
    adapter = KrxStockDataAdapter(cache_dir=str(tmp_path / "cache"))
    target_date = date(2026, 6, 30)  # 과거 거래일

    adapter.cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = adapter.cache_dir / "index_components_KOSPI200_20260630.json"
    old_created_at = "2026-07-01"

    cache_data = {
        "created_at": old_created_at,
        "components": ["005930", "000660"]
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f)

    with patch.object(adapter.session, 'post') as mock_post:
        # 조회 수행: 과거 거래일이므로 API를 호출하지 않고 기존 캐시 데이터를 그대로 로드해야 함
        components = adapter.fetch_index_components("KOSPI_200", target_date)
        assert mock_post.call_count == 0
        assert components == {"005930", "000660"}



