# Context Pack Specification

## 목적

이 문서는 Core Engine의 AI 컨텍스트 계층을 전역 특성과 지역 특성으로 분리해 정의한다.

핵심 원칙:

- 모델은 원문 파일을 직접 읽지 않는다.
- 에이전트는 `engine.context.*` API로 컴파일된 팩만 사용한다.
- 전역 정책은 불변이고, 책/장/노드는 지역 팩으로만 바뀐다.
- 컨텍스트는 stage 목적에 맞게 작게 유지한다.

---

## 1. 계층

### 1.1 Global Layer

- 소유자: `core_engine`
- 변경성: `immutable`
- 대상:
  - `policy_pack`
  - stage 계약
  - gate 계약
  - 토큰 예산 기본 규칙

전역 특성:

- 책이 바뀌어도 동일하게 재사용된다.
- 헌법, SOP, stage/gate 정의를 기준으로 생성된다.
- 책 로컬 문체나 도메인 지식을 직접 담지 않는다.

### 1.2 Local Layer

- 소유자: `book_local`
- 변경성: `mutable`
- 대상:
  - `book_context_digest`
  - `chapter_context_pack`
  - `node_context_pack`

지역 특성:

- 특정 책, 특정 장, 특정 노드에 종속된다.
- 기획안, BOOK_CONFIG, BOOK_BLUEPRINT, shared memory, research artifact를 요약한다.
- 같은 Core Engine을 다른 책에 재사용해도 지역 팩만 바뀐다.

---

## 2. Pack Types

### `policy_pack`

- 범위: 전역
- 입력:
  - `CONSTITUTION.md`
  - `PROJECT_SOP.md`
  - `stage_definitions.json`
  - `gate_definitions.json`
- 역할:
  - stage 목적
  - 실행 규칙
  - gate 핵심 체크
  - 토큰 budget 기본값

### `book_context_digest`

- 범위: 책 지역
- 입력:
  - `BOOK_CONFIG.json`
  - `BOOK_BLUEPRINT.md`
  - `WORD_TARGETS.json`
  - `shared_memory.book_memory`
- 역할:
  - 독자
  - core message
  - tone profile
  - structural strategy
  - writing rules

### `chapter_context_pack`

- 범위: 장 지역
- 입력:
  - `book_db.json`
  - `WORD_TARGETS.json`
  - `research_plan.json`
  - `reference_index.json`
  - `anchor_plan.json`
  - `shared_memory.chapter_memory`
- 역할:
  - 장 목표 분량
  - unresolved issues
  - source shortlist
  - anchor obligations
  - chapter-local memory

### `node_context_pack`

- 범위: 노드 지역
- 입력:
  - runtime node payload
- 역할:
  - 현재 section / block 목적
  - source excerpt
  - continuity excerpt
  - local goal

---

## 3. 전역 API

- `engine.context.build_policy_pack(stage_id)`
- `engine.context.build_book_digest(book_id)`
- `engine.context.build_chapter_pack(book_id, chapter_id, stage_id)`
- `engine.context.build_node_pack(book_id, chapter_id, stage_id, node_id)`
- `engine.context.materialize(stage_id, chapter_id, node_payload)`
- `engine.context.measure(prompt, context_artifacts)`

구현 파일:

- [context_packs.py](/d:/solar_book/engine_core/context_packs.py)

---

## 4. Stage 적용 규칙

### `S4`

- `policy_pack + book_context_digest + chapter_context_pack + node_context_pack`
- raw 원문 전체가 아니라 section node 목적 중심

### `S5`

- `policy_pack + book_context_digest + chapter_context_pack + node_context_pack`
- grounded review는 chapter-local freshness/source rule 위주

### `S8A`

- `policy_pack + book_context_digest + chapter_context_pack + node_context_pack`
- `Grounded Update / Sources / Supplemental`은 node 대상에서 제외
- 증폭 대상은 canonical prose section only

---

## 5. 예산 원칙

- `S4`: 중간 크기 입력 허용
- `S5`: grounded 조사 중심, source-heavy
- `S8A`: 가장 작은 컨텍스트

정책:

- 큰 마스터 문서 원문 직접 주입 금지
- distill된 pack 우선
- 노드 호출은 가능한 한 chapter-local 정보만 사용
- 토큰 예산 초과 시 pack distill을 먼저 적용하고, stage 로직은 그대로 둔다

---

## 6. 저장 위치

컨텍스트 팩은 책별 재현성을 위해 아래 경로에 저장한다.

```text
books/{display_name}/shared_memory/context_packs/
  global/
  local/
  runtime/
```

의미:

- `global/`: 책 기준으로 저장된 전역 팩 스냅샷
- `local/`: 책/장 digest
- `runtime/`: node pack 및 budget 계측 결과
