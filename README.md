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
6. 모든 수집 결과는 연도별 SQLite 파일(`db/{weekly,monthly}/{year}.db`)에 SSOT로 저장되고,
   매 실행마다 DB와 거래소 달력을 대조해 누락되거나 미확정인 기간을 자동으로 찾아 복구

## 아키텍처

포트-어댑터(Ports & Adapters) 구조로, 비즈니스 로직이 외부 인프라(KRX, SQLite, 구글 드라이브)에
직접 의존하지 않습니다.

```
src/
├── domain/            # 순수 도메인 로직 (필터, 완전성 계산, 포트 인터페이스, 모델)
├── application/        # 서비스 오케스트레이션 (수집 흐름, 엑셀 빌더)
└── infra/
    ├── adapters/       # KRX API, 거래소 달력
    └── storage/        # SQLite 저장소, Parquet(레거시), 구글 드라이브
```

- `CollectionOrchestratorService`: DB에 저장된 이벤트와 거래소 달력을 대조해 매일 실행 시
  누락/불완전 기간을 계산하고 재수집합니다. 별도의 `last_sync_date` 같은 동기화 상태값은
  두지 않습니다.
- `WeeklyGainerService`: 실제 수집·필터링·저장·업로드 흐름을 담당합니다.
- SQLite가 시스템의 SSOT(단일 진실 공급원)이며, 엑셀/구글 드라이브는 그 결과물일 뿐입니다.

## 요구 사항

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (의존성 관리)
- KRX 정보데이터시스템 계정
- 구글 드라이브 API OAuth 클라이언트(`secrets/client_secret.json`)

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

`secrets/client_secret.json`(구글 OAuth 클라이언트)이 있어야 하며, 최초 실행 시 인증을 거치면
`secrets/token.json`이 생성됩니다.

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
just deploy          # 빌드 후 재기동 (build + up)
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
