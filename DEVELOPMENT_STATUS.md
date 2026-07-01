# 프로젝트 개발 현황 및 향후 이정표 (DEVELOPMENT STATUS)

이 문서는 포트-어댑터 아키텍처 도입 및 주간/월간 등락률 수집 확장 작업의 **현재 완료 상태**와 **다음 단계의 구체적인 설계 가이드**를 정의합니다.

---

## 1. 현재 완료된 성과 (Milestones 1 ~ 3 완료)

### ① 포트 & 어댑터(Ports & Adapters) 아키텍처 약결합 적용
* **포트 선언 (`src/domain/ports.py`)**:
  * 비즈니스 서비스 레이어가 외부 인프라 기술에 종속되지 않도록 추상 포트 인터페이스(`CalendarPort`, `StockDataPort`, `ReportStoragePort`, `CloudUploadPort`)를 선언했습니다.
* **의존성 주입**:
  * `WeeklyGainerService`의 생성자가 구체 클래스가 아닌 추상 포트에 의존하게 수정하여 결합도를 완전히 제거하고 유닛 테스트 작성을 용이하게 바꿨습니다.
* **어댑터 포트 상속**:
  * `KrxStockDataAdapter`, `ParquetWeeklyGainerRepository`, `GoogleDriveAdapter`, `CalendarService`가 포트 규격을 상속 및 만족하도록 일치시켰습니다.

### ② KRX 공식 API 연동 달력 서비스 고도화
* **실시간 동적 휴장일 수집**:
  * 외부 `holidays` 패키지 의존성을 완전히 제거하고, 한국거래소 공식 포탈 `OPN99000001.jspx` API에 OTP 발급 과정을 거쳐 실시간 증시 휴장일 데이터를 받아와 캐싱하는 로직을 내장했습니다. (임시 공휴일, 선거일, 연말 휴장일 완벽 자동 반영)
* **미래 연도 법정휴일 폴백**:
  * 너무 먼 미래 연도(예: 2035년) 등 거래소 데이터베이스 고시가 나기 이전 시점에 대한 방어 목적으로 **5월 1일 근로자의 날 강제 보정 폴백(Fallback)** 로직을 심어두었습니다.
* **범용 영업일 범위 계산**:
  * 임의의 입력 기간(주간 월~금, 월간 1~31일, 혹은 5/1~오늘) 내에서 휴장일을 비껴가며 실제 거래가 발생한 첫 거래일과 마지막 거래일을 찾는 `get_trading_range_in_period` 범용 메서드를 완성했습니다.

### ③ 저장소 물리 격리 및 다중 시트 업로더 구축
* **주간/월간 저장소 격리 (`ParquetWeeklyGainerRepository`)**:
  * 생성자 인자 `period_type`에 따라 `weekly_event_manifest.json`과 `monthly_event_manifest.json` 매니페스트 파일을 다르게 저장하며, 데이터도 `weekly/`와 `monthly/` 하위 폴더에 독립 보관되도록 물리적으로 완벽히 격리했습니다. (생성자 인자 생략 시 기존 `event_manifest.json`에 저장하는 **하위 호환** 완비)
  * 월간 수집(`week=0`) 시 ISO 주차 계산 에러를 우회하고 월간 파일명(`monthly_gainers_YYYY_MM월.parquet`)으로 자동 수렴되도록 방어 처리했습니다.
* **다중 시트 Excel 업로더 (`GoogleDriveAdapter`)**:
  * `upload_excel` 메서드가 `Union[pd.DataFrame, Dict[str, pd.DataFrame]]`를 지원하도록 확장하여, 딕셔너리로 여러 개의 데이터프레임이 들어올 경우 각 키를 개별 엑셀 시트명으로 결합하여 단일 파일로 컴파일합니다. (단일 DataFrame 입력 시 기존 `'WeeklyGainers'` 시트명으로 폴백 처리하는 **하위 호환** 완비)

---

## 2. 테스트 아키텍처 정비 결과 (12 Passed)
설계 위반 상태였던 `scratch/` 내의 레거시 통합 테스트 및 E2E 코드를 완벽하게 청소하였으며, **스텁 대체 원칙(Stub Substitution)**을 철저히 지키는 12개 테스트 안전망을 확립했습니다:

* **단위 테스트 (8개) - `tests/unit/`**:
  * `test_ports_decoupling.py` (완전 Mock/Stub을 활용한 서비스 약결합 라이프사이클 테스트)
  * `test_calendar_service.py` (2035년 근로자의 날 강제 휴일 및 임의 기간 영업일 범위 산출 로직)
  * `test_parquet_repository.py` / `test_parquet_repository_extension.py` (저장소 입출력, Manifest 격리, 하위 호환)
  * `test_google_drive_adapter_extension.py` (다중 시트 및 단일 시트 데이터프레임 다형성 Excel 컴파일러 단위 테스트)
* **통합 테스트 (4개) - `tests/integration/`**:
  * `test_krx_adapter.py` (`unittest.mock`으로 HTTP 세션을 가로채어 파싱/세션만료 재로그인 통합 검증)
  * `test_parquet_repository.py` (`tmp_path` 피스처로 격리된 디렉토리상 파일 생성 및 복원 통합 검증)
  * `test_weekly_gainer_service_integration.py` (**종합 통합**: 실제 서비스와 실제 인프라 어댑터들을 주입하고 외부 HTTP만 모킹하여, 수집-필터-저장-업로드 전 과정이 한 몸으로 굴러가는지 보증)

---

## 3. 향후 이정표 및 구현 가이드 (Milestones 4 ~ 6)

다음에 작업을 이어서 시작할 때 개발해야 할 남은 태스크들의 설계 가이드라인입니다.

### 마일스톤 4: 도메인 필터 및 엑셀 리포트 빌더 분리 (TDD)
* **이유**: 지수 구성종목 합집합 필터링과 판다스 엑셀 가독성 스타일링 뷰(set_column 등)를 서비스 레이어 밖으로 던져 관심사를 분리해야 합니다.

#### ① 지수구성종목 합집합 필터 (`src/domain/gainer_filter.py`)
* **기능**: 코스피 200 / 코스닥 150 지수 수시 편출입 기간의 정합성을 위해, 시작일 기준 구성종목 목록과 종료일 기준 구성종목 목록을 받아 **합집합(Union)** 처리한 구성종목 풀을 기준으로, 20% 이상 등락한 전종목 데이터를 걸러내는 필터 객체를 작성합니다.
* **TDD 테스트 설계**:
  ```python
  def test_union_filter():
      start_components = {"A", "B", "C"}
      end_components = {"C", "D", "E"}
      # 합집합 풀: {"A", "B", "C", "D", "E"}
      
      filter_logic = GainerFilter(start_components, end_components)
      # 등락률이 20% 이상이면서 합집합 풀에 포함된 종목만 통과
  ```

#### ② 엑셀 가독성 뷰 빌더 (`src/application/services/excel_report_builder.py`)
* **기능**: 판다스 데이터프레임들을 받아 엑셀 스타일 가이드(너비 조절, 헤더 색상 등)를 적용한 Excel 바이너리를 조립해 돌려주는 순수 빌더 서비스를 구축합니다. `GoogleDriveAdapter`는 단지 전송 역할만 수행하게 정돈합니다.

---

### 마일스톤 5: 서비스 오케스트레이션 및 파이프라인 통합 (TDD)
* **이유**: 주간 수집(`collect_week`)과 월간 수집(`collect_month`)을 수집 주기 파라미터(`period_type`)에 따라 공통 메서드를 통과하도록 수집 서비스를 확장해야 합니다.

* **수집 흐름 통합 명세**:
  1. 수집 서비스는 `period_type`("WEEKLY" 또는 "MONTHLY")에 따라 날짜 범위(`start_date`, `end_date`)를 입력받습니다.
  2. `CalendarPort.get_trading_range_in_period(start_date, end_date)`를 통과시켜 `시작 거래일`과 `마지막 거래일`을 산출합니다.
  3. `StockDataPort`를 호출해 해당 범위의 전종목 등락 데이터를 수집합니다.
  4. 시작일과 마지막일 각각의 지수구성종목(K200, K150) 목록을 `StockDataPort.fetch_index_components`로 조회해 합집합 필터를 구성합니다.
  5. 필터링된 등락 데이터를 로컬 `ReportStoragePort.save`에 저장합니다.
  6. 가독성 엑셀 빌더로 다중 시트(전체 등락, 코스피200, 코스닥150) 통합 엑셀 문서를 생성하여 `CloudUploadPort.upload_excel`로 클라우드에 업로드합니다.

---

### 마일스톤 6: 데일리 스케줄러 배치 기동 및 과거 백필 테스트
* **이유**: `main.py`에 주간/월간 수집 옵션(예: `--period weekly`, `--period monthly`) 및 타겟 날짜/주차 인수 지정을 연동하고, 배치가 주기적으로 기동될 때 오늘이 휴장일인 경우 수집을 조기 스킵(`is_today_holiday`)하는 제어 메커니즘을 연동합니다.
