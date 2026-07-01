
---

name: xp-methodology
description: "Use this skill when starting a new milestone, writing tests, planning a refactor, fixing a bug, or any situation involving TDD, Walking Skeleton, Stub/Mock strategy, or test-level decisions. Triggers on: 'start milestone', 'write tests', 'refactor', 'fix bug', 'stub', 'integration test', 'walking skeleton', 'outside-in', 'characterization test'."
---

# XP Methodology: Walking Skeleton + Outside-In TDD

## Core Philosophy

> "테스트가 의도를 먼저 선언하고, 구현이 그걸 따라간다."

구현보다 테스트가 먼저다. Stub이든 실제 구현이든, 코드 전에 "무엇이 되어야 하는가"를 테스트로 고정한다.

---

## 1. Walking Skeleton (신규 기능)

마일스톤을 시작할 때 항상 이 순서를 따른다.

```
1. 마일스톤 정의 (무엇이 완료 상태인가)
2. 통합 테스트 먼저 작성 (예상 동작을 코드로 선언)
3. Stub으로 일단 통과시킴 (뼈대만 통과)
4. TDD로 각 Stub을 실제 구현으로 점진 교체
5. 교체할 때마다 통합 테스트가 회귀 안전망 역할
6. 모든 Stub 제거 = 마일스톤 완료
```

### Stub 제거 순서

의존성 역순 (leaf 모듈부터 제거). 다른 모듈이 의존하는 것을 먼저 제거하면 중간에 막힌다.

```
예: News → Market → Betting → Alert 의존 구조라면
    Alert Stub 먼저 제거 → Betting → Market → News 순
```

---

## 2. Stub vs Mock — 반드시 구분

```
Stub  = 고정값 리턴 (상태 기반)     ← Walking Skeleton에서 씀
Mock  = 호출 여부/방식 검증 (행위 기반)

# Stub 예시
class StubGeminiClient:
    async def classify(self, text: str) -> list[str]:
        return ["interest_rate", "fed"]  # 무조건 고정값

# Mock 예시 (남용 금지)
mock_publisher.publish.assert_called_once_with(NewsTagged(...))
```

**Mock 남용 금지**: Mock은 구현 디테일에 결합된다. 리팩토링할 때마다 테스트가 깨지는 원인이 된다. 행위 검증이 꼭 필요한 경우에만 Mock을 쓴다.

---

## 3. 테스트 레벨별 전략

### Unit Test

- 네트워크 없음, 완전 Stub
- 비즈니스 로직만 격리해서 검증
- 속도: 수 ms, CI 매 커밋마다 실행

### Integration Test

- 외부 서드파티 API (Gemini, Polymarket 등) → 가짜 서버 (WireMock, pytest-httpserver)
- 내부 인프라 (DB, Kafka 등) → Testcontainers로 실제 인스턴스
- **SQLite 주의**: PostgreSQL과 동시성 모델이 다름
  - `FOR UPDATE SKIP LOCKED`, JSONB, 트리거 등 → Testcontainers 필수
  - 단순 CRUD 검증만 → SQLite 인메모리 허용
- 속도: 수 초, CI 매 PR마다 실행

### E2E Test

- 진짜 외부 서버 호출
- 비용/속도 문제로 CI 매 커밋 아님, 배포 전/주기적으로만
- `@pytest.mark.e2e` 로 마킹해서 분리

---

## 4. Refactor (리팩토링)

리팩토링 전 반드시 이 순서를 지킨다.

```
1. 기존 테스트 커버리지 확인
2. 커버리지 부족 시 → Characterization Test 먼저 작성
3. 구조 변경
4. 같은 테스트 통과 = 리팩토링 성공
```

### Characterization Test 적용 기준

모든 코드에 다 쓰지 않는다. 아래 세 조건을 모두 만족할 때만 작성한다.

```
□ 지금 이 코드를 리팩토링할 계획인가?
□ 기존 테스트 커버리지가 부족한가?
□ radon cc grade C 이상 (복잡도 높음)인가?
```

작성 시: 핵심 경로 1~2개만, 전체 분기 100% 커버 X. 리팩토링 후 의도가 명확한 단위 테스트로 교체/통합 가능.

---

## 5. Fix (버그 수정)

```
1. 코드 먼저 고치지 않는다
2. 버그를 재현하는 실패 테스트 먼저 작성
3. 수정 후 테스트 통과 확인
4. 이 테스트는 영구 보존 (같은 버그 재발 방지)
```

---

## 6. Docs / Chore

- 새 테스트 작성 불필요 (동작 비변경)
- **예외**: 의존성 메이저 업그레이드, 인프라 설정 변경 등
  → 새 테스트는 불필요, 기존 전체 테스트 스위트 통과 여부는 CI에서 확인

---

## 7. Spike (기술적 불확실성 제거)

Walking Skeleton 시작 전, "이게 가능한가"를 먼저 검증해야 하면 Spike를 쓴다.

```
규칙:
  - 시간 제한 고정 (예: 최대 2시간, 반나절)
  - 결과물은 코드가 아니라 "답" (가능/불가능, 비용 수치 등)
  - 코드 품질 신경 X, 버려도 됨
  - 정식 저장소에 포함 안 함 (spikes/ → .gitignore)
  - 결과는 docs/adr/ 에 한 페이지로 이관

종류:
  Technical Spike  → 기술적 불확실성 ("이 API 비용이 얼마나 드는가?")
  Research Spike   → 도메인 불확실성 ("어떤 판정 기준이 맞는가?")
```

---

## Gotchas

- SQLite로 Outbox 워커 동시성 테스트하면 `FOR UPDATE SKIP LOCKED`가 조용히 무시됨. 에러 없이 동시성 버그를 못 잡는다. Testcontainers 필수.
- Mock을 Stub 대신 쓰면, 리팩토링 시 테스트가 우르르 깨진다. Walking Skeleton 단계에서는 Stub만.
- Characterization Test를 사전에 전체 코드베이스에 다 깔면 시간을 다 쓴다. 리팩토링 직전 + 해당 코드에만.
- Stub 제거를 의존성 순서 무시하고 하면 중간에 "아직 실제 구현이 없는 모듈에 의존"하는 상황이 생긴다.
