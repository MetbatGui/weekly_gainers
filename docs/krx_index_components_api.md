# KRX 지수구성종목 조회 API 명세 (MDCSTAT00601)

KRX 정보데이터시스템에서 제공하는 **지수구성종목 조회(BLD: dbms/MDC/STAT/standard/MDCSTAT00601)** API의 요청 및 응답 규격 메모리입니다.

---

## 1. 개요
* **요청 URL**: `https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd`
* **기능**: 특정 거래일(`trdDd`) 기준, 특정 지수(예: 코스피 200, 코스닥 150 등)에 편입된 구성종목 정보 및 당일 시세 요약을 반환합니다.
* **인증**: 필요 시 기존 어댑터 세션 및 로그인 로직(`mdc.client_session`, `lang` 쿠키 등)을 적용하여 호출합니다.

---

## 2. 요청 파라미터 (Request Payload)

| 파라미터명 | 코스피 200 설정값 | 코스닥 150 설정값 | 설명 |
| :--- | :--- | :--- | :--- |
| **`bld`** | `dbms/MDC/STAT/standard/MDCSTAT00601` | `dbms/MDC/STAT/standard/MDCSTAT00601` | 호출 타겟 BLD 명칭 (고정) |
| **`locale`** | `ko_KR` | `ko_KR` | 다국어 설정 (국문) |
| **`tboxindIdx_finder_equidx0_4`** | `코스피 200` | `코스닥 150` | 지수 이름 텍스트 상자 매핑 값 |
| **`indIdx`** | `1` | `2` | **지수 시장 대분류**<br>• `1`: 코스피 지수 계열<br>• `2`: 코스닥 지수 계열 |
| **`indIdx2`** | `028` | `203` | **상세 지수 코드**<br>• `028`: 코스피 200<br>• `203`: 코스닥 150 |
| **`codeNmindIdx_finder_equidx0_4`** | `코스피 200` | `코스닥 150` | 실제 지수 검색 코드명 |
| **`param1indIdx_finder_equidx0_4`** | `""` | `""` | 추가 필터 파라미터 (공백) |
| **`trdDd`** | `YYYYMMDD` (예: `20260630`) | `YYYYMMDD` (예: `20260630`) | 거래 기준일자 |
| **`money`** | `3` | `3` | 금액 단위 코드 |
| **`csvxls_isNo`** | `false` | `false` | 조회 형식 (엑셀 여부: 거짓) |

---

## 3. 응답 데이터 구조 (Response JSON)

응답은 JSON 포맷으로 반환되며, `output` 키 내에 구성종목들의 상세 정보 배열이 담겨 있습니다.

### 응답 필드 분석

| 필드명 | 의미 | 데이터 타입 | 예시값 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| **`ISU_SRT_CD`** | 단축 종목 코드 | String | `"005930"` | 6자리 주식 종목 코드 |
| **`ISU_ABBRV`** | 종목 약명 (종목명) | String | `"삼성전자"` | 한글 종목명 |
| **`TDD_CLSPRC`** | 당일 종가 | String | `"334,000"` | 콤마(,)가 포함된 천 단위 구분 기호 포함 |
| **`FLUC_TP_CD`** | 등락 구분 코드 | String | `"1"` | `1` (상승), `2` (하락) 등 |
| **`STR_CMP_PRC`** | 전일 대비 변동폭 | String | `"11,000"` / `"-12,000"` | 전일 종가 대비 등락폭액 |
| **`FLUC_RT`** | 등락률 (%) | String | `"3.41"` / `"-3.22"` | 소수점 표기율 |
| **`MKTCAP`** | 시가총액 | String | `"1,952,657,055,072,000"` | 원화 단위 시가총액 |
| **`IDX_ID`** | 지수 ID | String | `""` | 일반적으로 빈 문자열 반환 |

### JSON 응답 예시 (코스피 200 - 삼성전자)
```json
{
  "ISU_SRT_CD": "005930",
  "ISU_ABBRV": "삼성전자",
  "TDD_CLSPRC": "334,000",
  "FLUC_TP_CD": "1",
  "STR_CMP_PRC": "11,000",
  "FLUC_RT": "3.41",
  "MKTCAP": "1,952,657,055,072,000",
  "IDX_ID": ""
}
```

---

## 4. 참고 파일
* **임시 검증 스크립트**: [test_index_components.py](file:///c:/Users/user/Documents/최지석/Projects/weekly_gainers/scratch/test_index_components.py)
