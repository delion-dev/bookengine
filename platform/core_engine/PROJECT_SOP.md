# Project SOP

## 목적

이 문서는 `with_the_king`를 포함한 모든 신규 책 프로젝트가
MetaGPT 기반 작업 메커니즘으로 운영되기 위한 표준 운영 절차를 정의한다.

이 SOP는 사람이 읽는 설명 문서이면서, Core Engine 구현의 기준 문서다.

---

## 1. 설계 철학

이 시스템은 다음 5원칙을 반드시 따른다.

1. 역할 분리
2. 산출물 계약
3. 상태 추적
4. 검증 게이트
5. 오케스트레이션 우선

의미:

- 역할 분리: 에이전트는 단일 책임만 수행한다.
- 산출물 계약: 단계 간 전달은 입력/출력 아티팩트 계약으로만 이뤄진다.
- 상태 추적: 완료 여부는 DB와 stage state로만 판단한다.
- 검증 게이트: Gate를 통과하지 못하면 다음 단계로 넘어가지 않는다.
- 오케스트레이션 우선: AG-OM이 전체 우선순위와 병렬 가능 여부를 통제한다.

추가 원칙:

- reader-facing prose와 운영 메타를 분리한다.
- 운영 메타가 본문 파일 안에 꼭 필요하면 meta block 문법으로만 삽입한다.
- meta block은 anchor와 다르며, 출판 전 제거되어야 한다.

---

## 2. 프로젝트 생명주기

```text
사용자 입력
  -> S-1 Intake
  -> S0 Architecture
  -> S1 Orchestration
  -> S2 Research Plan
  -> S3 Raw Guides
  -> S4 Draft1 Prose
  -> S4A Draft1 Anchor Injection
  -> S5 Draft2 Review
  -> S6 Draft3 Visual Plan
  -> S6A Asset Collection Handoff
  -> S7 Draft4 Visual Render
  -> S8 Draft5 Copyedit + Gate
  -> S8A Optional Editorial Polish
  -> S9 Publication
  -> Release Package
```

---

## 3. 공식 입력

필수 입력:

- `_inputs/proposal.md`
- `_inputs/toc_seed.md`

선택 입력:

- `_inputs/author_note.md`
- `_inputs/market_positioning.md`
- `_inputs/reference_sources/*`

입력 문서가 들어오면 반드시 S-1 Intake를 먼저 거친다.

---

## 4. 표준 디렉터리 구조

```text
books/{display_name}/
  _inputs/
  _master/
  db/
  research/
    assets/
  shared_memory/
  manuscripts/
    _raw/
    _draft1/
    _draft2/
    _draft3/
    _draft4/
    _draft5/
    _draft6/
  publication/
    metadata/
    assets/
    output/
  verification/
  skills/
    local/
```

---

## 4A. Context Pack Layer

모든 AI 호출은 아래 4계층 컨텍스트 구조를 따른다.

### Global Layer

- `policy_pack`
- 소유자: `core_engine`
- 변경성: `immutable`
- 특징:
  - stage/gate/constitution 기반
  - 책별 문체나 도메인 지식과 분리
  - 어떤 책에도 재사용 가능

### Local Layer

- `book_context_digest`
- `chapter_context_pack`
- `node_context_pack`
- 소유자: `book_local` 또는 `runtime`
- 변경성: `mutable`
- 특징:
  - 책/장/노드 상태를 반영
  - shared memory, 연구 산출물, 목표 분량, 앵커 의무를 distill
  - 책이 바뀌면 local pack만 바뀐다

저장 위치:

```text
books/{display_name}/shared_memory/context_packs/
  global/
  local/
  runtime/
```

### Core Postprocess Candidate Registry

검증 과정에서 발견되는 후처리 규칙은 곧바로 코어 엔진에 승격하지 않는다.

- 후보 레지스트리: `platform/core_engine/postprocess_rule_candidates.json`
- 원칙:
  - 먼저 `candidate`로 축적
  - 다중 챕터 검증 후에만 immutable core rule로 승격
  - 책별 예외 처리는 local rule로 남기고, 전역 규칙만 core에 편입

즉 지금 단계의 후처리 규칙은 `수집 -> 검증 -> 승격`의 3단계를 반드시 거친다.

---

## 5. Stage 정의

### S-1 Intake

- 담당: AG-IN
- 목적: 입력 정규화와 intake manifest 생성
- 입력: proposal, toc seed
- 출력: `intake_manifest.json`
- Gate: `input_contract_pass`

### S0 Architecture

- 담당: AG-AR
- 목적: 책 구조와 품질 기준 설계
- 입력: intake manifest
- 출력:
  - `BOOK_CONFIG.json`
  - `WORD_TARGETS.json`
  - `ANCHOR_POLICY.json`
  - `BOOK_BLUEPRINT.md`
  - `STYLE_GUIDE.md`
  - `QUALITY_CRITERIA.md`
- Gate: `blueprint_complete`

### S1 Orchestration

- 담당: AG-OM
- 목적: 실행 우선순위, 병렬성, 블록 항목 결정
- 입력: book state, blueprint
- 출력:
  - `WORK_ORDER.local.json`
  - `PIPELINE_STATUS.local.json`
- 운영 규칙:
  - `WORK_ORDER.local.json`은 `runtime_alerts`로 medium/high runtime warnings를 함께 노출한다.
- Gate: `work_order_issued`

### S2 Research Plan

- 담당: AG-RS
- 목적: 필요한 조사 범위와 출처 전략 수립
- 입력: book config, blueprint, word targets, anchor policy, proposal, toc
- 출력:
  - `research_plan.json`
  - `source_queue.json`
  - `reference_index.json`
  - `image_manifest.json`
  - `publication/appendix/REFERENCE_INDEX.md`
- Gate: `research_plan_complete`

### S3 Raw Guides

- 담당: AG-00
- 목적: 챕터별 집필 가이드 생성
- 입력: book config, blueprint, word targets, anchor policy, research plan
- 출력:
  - `_raw/{chapter}_raw.md`
  - `_raw/{chapter}_anchor_plan.json`
- Gate: `raw_guides_complete`

### S4 Draft1 Prose

- 담당: AG-01
- 목적: 목표 분량 90%를 향한 실질 초고 작성
- 입력: raw guide, word targets, source queue
- 출력:
  - `_draft1/{chapter}_draft1_prose.md`
  - `_draft1/{chapter}_node_manifest.json`
  - `_draft1/{chapter}_segment_plan.json`
  - `_draft1/{chapter}_narrative_design.json`
  - `_draft1/{chapter}_density_audit.json`
  - `_draft1/{chapter}_session_report.json`
- 실행 규칙:
  - 장 전체를 한 번에 쓰지 않고 내부 표준 함수로 분해한다.
  - `f_plan_segment`
  - `f_design_narrative`
  - `f_implement_uhd`
  - `f_verify_density`
  - `f_report_session`
  - `policy_pack + book_context_digest + chapter_context_pack + node_context_pack`만 모델에 전달한다.
  - 모델 route는 `resolve_stage_route`가 stage/section 정책에 따라 결정한다.
  - section expansion loop는 최대 `3`회까지만 허용한다.
  - live model 호출은 `VERTEX_REQUEST_MIN_INTERVAL_MS` 간격을 준수한다.
  - 장 완료 판정은 단순 파일 생성이 아니라 coverage, live contribution, structure를 함께 본다.
  - 이 stage는 "책을 어떻게 쓸 것인가"를 설명하는 메타 문장을 쓰지 않는다.
  - 영화 책의 경우 장면, 인물, 연기, 스틸컷, 실제 장소 감각을 직접 서술하는 reader-facing prose를 우선한다.
  - 영화 속 장면과 실제 장소를 잇는 성지순례 동기는 초고 단계에서 이미 자연스럽게 심어야 한다.
  - `스틸컷 vs 실제 장소 비교`, `현장 동선`, `인생샷/관람 포인트`, `실용 팁`은 후속 앵커 설계에만 넘기지 말고 초고 본문에도 서사적 동력으로 반영한다.
  - reader-facing prose와 직접 관련 없는 운영 메모는 본문 산문으로 쓰지 않는다.
  - 꼭 필요한 경우에만 `META_START ... META_END` 문법을 사용한다.
- Gate 보강:
  - `context_budget_within_policy`
  - `s4_expansion_cap_respected`
- Gate: `draft1_complete`

### S4A Draft1 Anchor Injection

- 담당: AG-01B
- 목적: prose를 훼손하지 않고 canonical anchor block을 주입
- 입력: `draft1_prose`, `anchor_plan`, `ANCHOR_POLICY`
- 출력:
  - `_draft1/{chapter}_draft1.md`
  - `_draft1/{chapter}_anchor_injection_report.json`
  - `_draft1/{chapter}_anchor_scope_report.json`
- 실행 규칙:
  - anchor block 바깥 본문은 byte-for-byte 보존을 원칙으로 한다.
  - placement는 내부 canonical section key를 따르되, 독자 노출 heading은 한국어 표기 규칙을 따른다.
  - anchor block은 후속 stage의 작업 지시서이므로, `START + SLOT + END` 경계를 반드시 유지한다.
- Gate: `draft1_anchor_complete`

상세 재설계 명세: [S4_REDESIGN_SPEC.md](/d:/solar_book/platform/core_engine/S4_REDESIGN_SPEC.md)

### S5 Draft2 Review

- 담당: AG-02
- 목적: 사실 검증, 현행화, 톤 정제, 저작권/초상권/상업 이용 리스크 리뷰
- 입력: draft1, citations, reference index, research plan, image manifest, word targets
- 출력:
  - `_draft2/{chapter}_draft2.md`
  - `_draft2/{chapter}_review_report.md`
  - `_draft2/{chapter}_rights_review.json`
- 실행 규칙:
  - review는 section별 grounded review node를 순차 실행한 뒤 합산한다.
  - grounded review는 distilled chapter context와 node context를 우선 사용한다.
  - 모델 route는 전역 `model_routing_policy`를 따른다.
  - 모든 외부 텍스트/시각 자료는 부록 reference index와 연결되어야 한다.
  - S5는 사실 검증 외에 아래 상업 출판 리스크를 함께 리뷰한다.
  - 뉴스/기사: verbatim 복사 금지, 재구성 중심
  - UGC/SNS: 동의, 익명화, 통계화 여부 확인
  - 영화 스틸/보도사진/외부 이미지: 허가 또는 대체 자산 필요 여부 판정
  - 장소/맛집/지자체 이미지: 직접 촬영, 공공저작물, 상업 이용 조건 점검
  - review 메타는 sidecar artifact 우선, 본문 파일 안에 남길 경우 meta block으로만 기록한다.
- Gate 보강:
  - `context_budget_within_policy`
  - `rights_review_exists`
  - `grounded_body_evidence_attached`
  - `rights_provenance_complete`
- Gate: `review_pass`

### S6 Draft3 Visual Plan

- 담당: AG-03
- 목적: 시각 앵커와 visual plan 설계
- 입력: draft2, review report, rights review, anchor plan, anchor policy, citations, image manifest, reference index
- 출력:
  - `_draft3/{chapter}_draft3.md`
  - `_draft3/{chapter}_visual_plan.json`
  - `_draft3/{chapter}_visual_support.json`
- 실행 규칙:
  - `draft3.md`는 사람이 읽는 시각 설계 인계본만 남긴다.
  - `Review Layer`, `Grounded Update`, `Grounded Sources` 등 검토 메타는 `visual_support.json`으로 분리한다.
  - `visual_support.json`은 S5 검토 결과와 시각 설계 근거를 구조화해 보존한다.
  - `DS` 계열 앵커는 반드시 `numeric_source_packet`을 가져야 한다.
  - meta block이 남아 있으면 visual planning 전에 제거한다.
- Gate: `visual_plan_complete`

### S6A Asset Collection Handoff

- 담당: AG-AS
- 목적: 오프라인 실자산 수집을 위한 appendix ref, 파일명, 저장 경로, binding 상태를 chapter 단위로 고정
- 입력: draft3, visual plan, visual support, reference index, image manifest
- 출력:
  - `research/assets/{chapter}_asset_collection_manifest.json`
  - `publication/assets/cleared/{chapter}/ASSET_COLLECTION_{chapter}.md`
- 실행 규칙:
  - 저작권 해결 자체는 offline round에서 수행한다.
  - 이 stage는 오프라인 수집자가 바로 작업할 수 있도록 `appendix_ref`, `target_filename`, `target_dir`, `binding_status`를 확정한다.
  - 파일명 규칙은 `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext`를 기본으로 한다.
  - `S7`은 cleared asset이 존재하면 placeholder보다 실제 자산 바인딩을 우선한다.
- Gate: `asset_collection_handoff_complete`

### S7 Draft4 Visual Render

- 담당: AG-04
- 목적: 시각 자료 렌더링과 본문 통합
- 입력: draft3, visual plan, visual support, asset collection manifest
- 출력:
  - `_draft4/{chapter}_draft4.md`
  - `_draft4/{chapter}_visual_bundle.json`
- 실행 규칙:
  - `visual_support.json`의 anchor packet을 실제 렌더에 사용한다.
  - `asset_collection_manifest.json`에 cleared asset이 있으면 해당 파일을 우선 바인딩한다.
  - `summary_box_packet`은 summary box 문안을 생성해야 한다.
  - `numeric_source_packet`은 차트/데이터 스탯의 축과 수치 series를 생성해야 한다.
  - support packet의 gap은 visual bundle에 그대로 남겨 후속 검수에 사용한다.
  - meta block은 시각 렌더 입력으로 해석하지 않고 제거 대상으로 본다.
- Gate: `visual_render_pass`

### S8 Draft5 Copyedit + Gate

- 담당: AG-05
- 목적: 최종 교정과 품질 판정
- 입력: draft4, style guide, quality criteria
- 출력:
  - `_draft5/{chapter}_draft5.md`
  - `_draft5/{chapter}_proofreading_report.md`
  - `verification/gate_{chapter}.json`
- Gate: `copyedit_gate_pass`

### S8A Optional Editorial Polish

- 담당: AG-05A
- 목적: 사용자 승인 또는 편집상 필요가 있을 때만 선택적으로 polish를 수행
- 입력: draft5, style guide, quality criteria, blueprint
- 출력:
  - `_draft6/{chapter}_draft6.md`
  - `_draft6/{chapter}_amplification_report.md`
- 실행 규칙:
  - 기본 출판 경로의 필수 stage가 아니다.
  - prose block을 rewrite node로 쪼개 순차 실행한다.
  - `Grounded Update`, `Grounded Findings`, `Grounded Sources`, `Supplemental / Low-Trust Signals`는 rewrite 대상에서 제외한다.
  - 증폭은 canonical prose section만 대상으로 하며, 재앵커링이나 후속 stage 재루프를 유발하면 안 된다.
  - rewrite target은 장당 최대 `10`개로 제한한다.
  - `draft6`는 `draft5` 대비 `2.0x`를 넘기면 gate fail 처리한다.
  - 모델 route는 section별로 `balanced/high_quality` 프로필을 분기한다.
  - live rewrite가 너무 짧으면 heuristic fallback으로 의미 보존을 우선한다.
  - `gate_failed` 상태에서 잔여 이슈가 `takeaway_not_reader_oriented` 하나뿐이면, 전체 장 재실행 대신 `Takeaway`만 fast remediation 한다.
- Gate 보강:
  - `context_budget_within_policy`
  - `s8a_rewrite_target_cap_respected`
  - `s8a_amplification_ratio_within_cap`
- Gate: `amplification_pass`

### S9 Publication

- 담당: AG-06
- 목적: 출판물 생성과 플랫폼 검증
- 입력: draft5 bundle, metadata
- 출력:
  - `publication/output/{book_id}.epub`
  - `publication/output/{book_id}.pdf`
  - `publication/output/publication_manifest.json`
  - `publication/output/seo_metadata.json`
  - `publication/output/store_listing.md`
- 실행 규칙:
  - 기본 출판 소스는 `draft5`다.
  - `S8A`가 명시적으로 완료된 챕터만 선택적으로 `draft6`를 우선 사용할 수 있다.
- 실패 조건 보강:
  - raw Mermaid 잔존
  - unresolved anchor slot 잔존
  - meta block 잔존
- Gate: `publication_pass`

---

## 6. 상태 전이 규칙

각 stage의 상태는 아래 집합만 사용한다.

- `not_started`
- `pending`
- `in_progress`
- `completed`
- `gate_failed`
- `blocked`

상태 전이 규칙:

- `not_started -> pending`
- `pending -> in_progress`
- `in_progress -> completed`
- `in_progress -> gate_failed`
- `gate_failed -> pending`
- `pending -> blocked`
- `blocked -> pending`

금지 전이:

- `completed -> in_progress`
- `completed -> not_started`
- `gate_failed -> completed` without rerun

---

## 7. 병렬 처리 규칙

허용:

- 다른 책의 작업
- 같은 책의 다른 챕터 작업
- 같은 단계의 여러 챕터 작업

금지:

- 같은 챕터의 인접 단계 동시 실행
- 같은 `book_db`에 대한 경쟁 쓰기
- Gate 판정 이전의 다음 단계 착수

---

## 8. 검증 체계

검증은 3층으로 분리한다.

### Layer 1. 계약 검증

- 입력 파일 존재
- 스키마 정합성
- 필수 필드 충족

### Layer 2. 품질 검증

- 스타일 가이드 준수
- 구조 완결성
- 분량 기준
- 인용/출처 적합성

### Layer 3. 출판 검증

- EPUB/PDF 빌드 성공
- 메타데이터 완결성
- Google Books/Play 호환성

---

## 9. Shared Memory 규칙

Shared Memory는 대화 로그가 아니라 구조화된 작업 기억이다.

메모리 계층:

- Global Memory: 전역 정책, 엔진 버전, registry snapshot
- Book Memory: 책 전략, 핵심 메시지, 장 의존 관계
- Chapter Memory: 챕터 요약, unresolved issues, citations summary
- Run Memory: 현재 세션의 관찰, 수정 내역, gate notes

Shared Memory는 다음 용도로만 사용한다.

- 재시작 복구
- 컨텍스트 압축
- unresolved issue 전달
- 검수/출판 전 누락 점검

---

## 10. 예외 처리

### Gate Failed

- Gate 결과를 기록
- 반환 대상 stage 지정
- 수정 지시를 작성
- 상태를 `gate_failed`로 변경
- AG-OM이 재배정

### Blocked

- 외부 자료 부족, 저자 판단 필요, API 장애 등은 `blocked`
- unblock 조건을 명시
- AG-OM이 다른 work item으로 우회

### Abort

- 책 루트나 Core Engine 헌법 위반 시 작업 중단
- `engine.constitution.assert_compliance` 실패 기록

---

## 11. Release 기준

출판 패키지는 다음을 모두 만족해야 한다.

- 모든 필수 챕터 `draft5` 완료
- 전체 Gate pass
- publication manifest 생성
- 플랫폼 검증 pass
- 핵심 메타데이터 누락 없음

---

## 12. `with_the_king` 적용 해석

이 책은 뉴스/트렌드/팬덤/여행/로컬 콘텐츠가 혼합된 책이다.
따라서 이 프로젝트에서는 특히 아래 두 점을 강화한다.

- S2 Research Plan을 필수 단계로 강제
- S5 Review에서 출처 최신성 검증을 강하게 적용
- S8A에서 독자 가치와 현장감을 최종 증폭

즉, 이 책의 Core 흐름은 "기획 -> 조사 -> 집필 -> 검증 -> 출판"이다.
"기획 -> 바로 집필"은 허용하지 않는다.
