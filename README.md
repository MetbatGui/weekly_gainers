# Weekly Gainers

KRX(한국거래소) 전종목 데이터를 매일 수집해, 주간/월간 단위로 등락률 20% 이상 급등 종목을
추려 코스피200·코스닥150 소속 여부까지 표시한 엑셀 리포트를 만들고 구글 드라이브에
자동 업로드하는 배치 프로그램입니다.

## 무엇을 하는가

1. 지정된 기간(주간: 월~금, 월간: 1일~말일)의 실제 거래일 범위를 KRX 공식 휴장일 달력으로 계산
2. 그 기간 전종목의 등락 데이터를 KRX에서 수집
3. 등락률 20% 이상 종목만 필터링
4. 기간 시작일·종료일 기준 코스피200/코스닥150 구성종목 합집합을 조회해, 각 종목이 그 기간에
   지수에 속했는지 플래그로 표시
5. `전체_등락종목` / `KOSPI_200` / `KOSDAQ_150` 3개 시트로 구성된 엑셀 리포트를 생성해 구글
   드라이브에 업로드
6. 모든 수집 결과는 구글 드라이브의 연도별 SQLite 파일(`db/{weekly,monthly}/{year}.db`)이
   SSOT이며, 매 실행마다 DB와 거래소 달력을 대조해 누락되거나 미확정인 기간을 자동으로
   찾아 복구

## 아키텍처

포트-어댑터(Ports & Adapters) 구조로, 비즈니스 로직이 외부 인프라(KRX, SQLite, 구글 드라이브)에
직접 의존하지 않습니다.

```
src/
├── domain/            # 순수 도메인 로직 (필터, 완전성 계산, 포트 인터페이스, 모델)
├── application/        # 서비스 오케스트레이션 (수집 흐름, 엑셀 빌더)
└── infra/
    ├── adapters/       # KRX API, 거래소 달력
    └── storage/        # SQLite 저장소, DbSyncSession(GDrive 세션), Parquet(레거시), 구글 드라이브
```

- `CollectionOrchestratorService`: DB에 저장된 이벤트와 거래소 달력을 대조해 매일 실행 시
  누락/불완전 기간을 계산하고 재수집합니다. 별도의 `last_sync_date` 같은 동기화 상태값은
  두지 않습니다.
- `WeeklyGainerService`: 실제 수집·필터링·저장·업로드 흐름을 담당합니다.
- **구글 드라이브가 시스템의 SSOT(단일 진실 공급원)입니다.** 로컬 `db/{weekly,monthly}/{year}.db`는
  영속 저장소가 아니라 `DbSyncSession`(`infra/storage/db_sync_session.py`)이 실행마다
  `tempfile.mkdtemp()`로 만드는 작업 사본입니다 — GDrive에서 받아와 수집·갱신 후 다시
  업로드하고, 실행이 끝나면(성공/실패 무관) 통째로 삭제됩니다. 자세한 원칙은
  `Projects/db_ssot_guide.md` §6.1 참고.

## 요구 사항

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (의존성 관리)
- KRX 정보데이터시스템 계정
- 구글 드라이브 API OAuth 토큰(`secrets/token.json`) — 발급은 이 저장소 밖에서 이뤄짐

## 설치 및 설정

```bash
uv sync
```

`.env` 파일에 다음 값을 설정합니다.

```
KRX_USERNAME=...
KRX_PASSWORD=...
GOOGLE_DRIVE_WEEKLY_CHANGE_FOLDER_ID=...
```

`secrets/token.json`(구글 OAuth 토큰)이 있어야 합니다. 이 코드는 만료된 토큰의 **리프레시**만
처리하며(`google.auth.transport.requests.Request`), 최초 발급(브라우저 동의 흐름)은 이
저장소에 포함돼 있지 않습니다 — 같은 GDrive OAuth 클라이언트를 쓰는 다른 자매 프로젝트에서
발급받은 `token.json`을 복사해 사용하세요.

## 사용법

```bash
# 매일 실행하는 동기화 파이프라인 (누락/미확정 기간 자동 복구 포함)
python main.py --action sync

# 특정 주차/월 단일 수집
python main.py --action collect --period weekly --year 2026 --value 26
python main.py --action collect --period monthly --year 2026 --value 8

# 기존 상태(FINAL)를 무시하고 강제 재수집
python main.py --action collect --period weekly --year 2026 --value 26 --force

# 연도 전체 백필 (누락분 채우기)
python main.py --action backfill --period weekly --year 2024

# 연도 전체 강제 재수집 (스키마 변경 후 기존 데이터 갱신 등에 사용)
python main.py --action backfill --period weekly --year 2024 --force
```

## Docker로 실행

```bash
just docker-build     # 이미지 빌드
just docker-deploy    # 최신 이미지로 컨테이너 재기동
```

컨테이너 내장 cron이 스케줄에 따라 `--action sync`를 주기 실행합니다. 스케줄은
`docker/crontab`을 참고하세요.

```bash
docker-compose run --rm gainer python main.py --action sync
docker-compose run --rm gainer python main.py --action collect --period weekly --year 2026 --value 26
docker-compose run --rm gainer python main.py --action backfill --period weekly --year 2026
```

## 테스트

```bash
uv run pytest
```

Walking Skeleton + Outside-In TDD 방식을 따릅니다. 자세한 개발 방법론은
[CLAUDE.md](CLAUDE.md)를, DB/드라이브/도커 마이그레이션 배경은
[docs/db_drive_docker_migration_guide.md](docs/db_drive_docker_migration_guide.md)를
참고하세요.

## 인수인계 시 주의 사항

- **로컬 `db/`는 더 이상 신뢰할 입력이 아닙니다.** 위 아키텍처 절에서 설명한 대로 매 실행이
  GDrive에서 새로 받아온 임시 사본으로 동작합니다. 호스트에 남아있는 `db/` 디렉토리는 과거
  잔재일 뿐 코드 어디에서도 읽거나 쓰지 않으므로(`docker-compose.yml`에도 더 이상 마운트하지
  않음), 지워도 무방합니다.
- **다운로드 실패는 연도 단위로 부분 fail-closed 처리합니다.** GDrive에서 특정 연도 DB를
  받아오지 못하면(네트워크 오류 등) 그 연도만 이번 실행에서 건너뛰고(수집도 업로드도 안 함)
  나머지 정상 연도는 평소대로 처리합니다 — "원격에 아직 없음(최초 백필 전)"과 "원격에 있는데
  못 읽음"을 `GoogleDriveAdapter.path_exists()`로 구분해서, 후자를 빈 DB로 오인해 그대로
  덮어쓰는 사고를 막습니다. 이 정책을 크론 전체 중단으로 바꾸고 싶다면
  `db_ssot_guide.md` §6.1과 `CollectionOrchestratorService.failed_years`를 참고하세요 —
  일부러 가용성을 우선한 절충이라 기본값을 바꾸기 전에 트레이드오프를 이해할 것.
- **`path_exists()` 자체의 실패는 "없음"과 구분하지 못합니다** (`db_sync_session.py`의
  `ponytail:` 주석 참고) — 메타데이터 조회라 `get_file()`보다 실패 빈도/영향이 낮다고 보고
  의도적으로 남겨둔 한계입니다. 자주 걸리면 `path_exists`에 재시도를 추가할 것.
- **KRX 요청 속도 제한을 절대 풀지 말 것.** 과거 짧은 시간에 대량 요청을 보내 KRX가 소스 IP를
  약 2달간 차단한 사고가 있었습니다. `infra/adapters/krx_adapter.py`(또는 이식된
  `common/native_krx_adapter.py`)의 요청 간 최소 대기시간 로직은 디버깅/성능 이유로도
  제거하거나 완화하지 말 것.
- **`.env`는 파일 bind mount로 넘깁니다** (`env_file`이 아님) — cron이 스폰하는 잡은 컨테이너
  프로세스의 OS 환경변수를 상속받지 않지만, `main.py`의 `load_dotenv()`가 매번 파일을 직접
  읽으므로 정상 동작합니다. 단, 호스트에 `.env` 파일이 실제로 존재해야 합니다 — 없으면
  Docker가 빈 디렉토리를 대신 마운트해 로드가 조용히 실패합니다.
