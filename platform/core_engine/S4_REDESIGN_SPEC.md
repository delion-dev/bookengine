# S4 Redesign Spec

## Purpose

이 문서는 `S4 / AG-01`을 단순 초고 골격 생성 단계가 아니라
`목표 분량 90% 이상`을 안정적으로 향해 가는 초고 작성 엔진으로 재설계하기 위한 기준 명세다.

핵심 원칙은 두 가지다.

1. 초고 작성은 `chapter one-shot`이 아니라 `step-aligned live orchestration`으로 수행한다.
2. `completed`는 단순 파일 생성이 아니라 `coverage`, `live contribution`, `structure`를 함께 충족해야 한다.

---

## Current Limitation

현재 구현의 한계는 다음과 같다.

- `S4`가 planning, drafting, expansion, fallback을 한 함수에 함께 품고 있다.
- 챕터당 `Hook/Context/Insight/Takeaway` 4 node만으로 긴 장을 안정적으로 밀어 올리기 어렵다.
- `template_fallback`이 stage completion에 흡수될 수 있어, 완료와 실제 live 기여가 분리된다.
- 사용자 기대는 `실질 초고`인데, 현재 결과는 `초고 골격 + 부분 라이브 생성`에 가깝다.

---

## Target Architecture

`S4`는 외부 stage id를 유지하되, 내부 실행은 아래 5개 표준 함수로 분해한다.

### Step 1. `f_plan_segment`

- 목표: 장을 실제 집필 가능한 segment node로 분해
- 입력:
  - raw guide
  - word targets
  - source queue
  - chapter context pack
- 출력:
  - `_draft1/{chapter_id}_segment_plan.json`
- 필수 포함:
  - segment id
  - section key
  - target words
  - claim intent
  - evidence slot
  - anchor obligation
  - reader payoff

### Step 2. `f_design_narrative`

- 목표: segment별 서사 역할과 연결 구조 설계
- 입력:
  - segment plan
  - blueprint digest
  - style guide digest
- 출력:
  - `_draft1/{chapter_id}_narrative_design.json`
- 필수 포함:
  - opening tactic
  - continuity bridge
  - tension/release note
  - tone guardrail
  - forbidden drift topics

### Step 3. `f_implement_uhd`

- 목표: node 단위 라이브 호출로 실제 1차 초고 작성
- 입력:
  - segment plan
  - narrative design
  - node context pack
  - source queue slice
- 출력:
  - `_draft1/{chapter_id}_draft1.md`
  - `_draft1/{chapter_id}_node_manifest.json`
- 규칙:
  - node 단위 순차 호출
  - section 전체가 아니라 segment별 호출
  - fallback은 허용하되, live contribution 비율을 기록
  - anchor block은 draft assembly 시점에 주입

### Step 4. `f_verify_density`

- 목표: 물리 파일 시스템 기준 초고 밀도 감사
- 입력:
  - draft1
  - node manifest
  - word targets
- 출력:
  - `_draft1/{chapter_id}_density_audit.json`
- 필수 검사:
  - draft coverage ratio
  - live node success ratio
  - fallback-only 여부
  - required sections 존재
  - anchor block insertion 여부

### Step 5. `f_report_session`

- 목표: `S4` 승격 여부를 명시적으로 판정
- 입력:
  - density audit
  - node manifest
  - draft1
- 출력:
  - `_draft1/{chapter_id}_session_report.json`
- 판정:
  - `completed`
  - `completed_with_alert`
  - `gate_failed`

---

## AG-01 Capability Upgrade

`AG-01`은 아래 기능을 강화해야 한다.

### 1. Segment Granularity Upgrade

- 기본 4 section node에서 `8~16 segment node` 기준으로 확장
- 장 길이와 복잡도에 따라 segment 수를 동적으로 결정

### 2. Step-Specific Live Calls

- `plan`은 structured generation
- `narrative`는 structured/high-quality generation
- `implement`는 prose generation
- `verify`는 rule-based audit 우선

### 3. Coverage-Driven Drafting

- 목표: `draft1 >= target_words * 0.90`
- 예외: review-heavy or quote-light chapter는 chapter policy에 따라 완화 가능

### 4. Stronger Runtime Semantics

- `all_nodes_fallback`이면 기본적으로 `completed`가 아니라 `completed_with_alert` 또는 `gate_failed`
- `live_node_success_ratio`를 반드시 기록

### 5. Safer Expansion Policy

- loop cap: 최대 `3회`
- growth per pass: 이전 분량의 `1.5x` 이내
- 전체 `draft1`은 chapter target의 `1.1x`를 넘기지 않음

---

## Proposed AG-01 API Surface

- `engine.writer.plan_segments(book_id, chapter_id)`
- `engine.writer.design_narrative(book_id, chapter_id)`
- `engine.writer.implement_uhd(book_id, chapter_id)`
- `engine.writer.verify_density(book_id, chapter_id)`
- `engine.writer.report_session(book_id, chapter_id)`
- `engine.stage.run(S4)`는 위 다섯 함수를 오케스트레이션하는 wrapper로 유지

---

## Draft1 Gate Upgrade

향후 `draft1_complete` gate는 아래 조건을 함께 봐야 한다.

- `chapter_structure_complete`
- `required_sections_present`
- `anchor_blocks_inserted`
- `draft_coverage_ratio >= 0.90`
- `live_node_success_ratio >= 0.60`
- `fallback_only_completion == false`
- `s4_expansion_cap_respected`
- `context_budget_within_policy`

---

## Review Guidance

사용자가 `S4`를 육안 검수할 때는 아래 순서로 본다.

1. `segment_plan.json`: 무엇을 쓰려 했는가
2. `narrative_design.json`: 어떻게 읽히게 하려 했는가
3. `draft1.md`: 실제 본문이 나왔는가
4. `density_audit.json`: 목표 분량과 live 기여가 충분한가
5. `session_report.json`: 왜 통과/경고/실패했는가

이 다섯 산출물이 있어야 `S4`는 사람이 검수 가능한 stage가 된다.
