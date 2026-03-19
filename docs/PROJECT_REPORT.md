# Project Report

## 1. Active Structure

```text
d:\solar_book
├── books/
│   └── with the King/
├── docs/
├── engine_core/
├── platform/
├── tools/
└── _archive/
```

`_archive/legacy_workspace_20260314/`에는 기존 태양광 집필 실험, 예전 MCP/EPUB 도구, 레거시 문서와 자산을 모두 이동했다.

---

## 2. Stage Sequence

| Stage | Agent | Public API | 목적 | 대표 출력 |
|---|---|---|---|---|
| `S-1` | `AG-IN` | `engine.bootstrap.normalize_inputs` | 입력 정규화 | `intake_manifest.json` |
| `S0` | `AG-AR` | `engine.stage.run(S0)` | 책 설계 | `BOOK_CONFIG.json`, `WORD_TARGETS.json`, `ANCHOR_POLICY.json`, `BOOK_BLUEPRINT.md` |
| `S1` | `AG-OM` | `engine.stage.run(S1)` | 오케스트레이션 | `WORK_ORDER.local.json` |
| `S2` | `AG-RS` | `engine.stage.run(S2)` | 조사 계획 | `research_plan.json`, `reference_index.json`, `image_manifest.json` |
| `S3` | `AG-00` | `engine.stage.run(S3)` | 챕터 raw guide | `_raw/{chapter}_raw.md`, `_raw/{chapter}_anchor_plan.json` |
| `S4` | `AG-01` | `engine.stage.run(S4)` | 초고 | `_draft1/{chapter}_draft1.md`, `_draft1/{chapter}_node_manifest.json` |
| `S5` | `AG-02` | `engine.stage.run(S5)` | 검증/리뷰/권리 점검 | `_draft2/{chapter}_draft2.md`, `_draft2/{chapter}_review_report.md`, `_draft2/{chapter}_rights_review.json`, `_draft2/{chapter}_review_nodes.json` |
| `S6` | `AG-03` | `engine.stage.run(S6)` | 시각 설계 | `_draft3/{chapter}_visual_plan.json` |
| `S6B` | `AG-IM` | `engine.stage.run(S6B)` | 이미지 자산 수집·생성·등록 | `cleared/{chapter}/ASSET_*`, `{anchor_id}_provenance.json`, `{chapter}_ingestion_report.json` |
| `S7` | `AG-04` | `engine.stage.run(S7)` | 시각 통합 | `_draft4/{chapter}_draft4.md`, `_draft4/{chapter}_visual_bundle.json` |
| `S8` | `AG-05` | `engine.stage.run(S8)` | 교정/Gate | `_draft5/{chapter}_draft5.md`, `_draft5/{chapter}_proofreading_report.md` |
| `S8A` | `AG-05A` | `engine.stage.run(S8A)` | 톤/가치 증폭 | `_draft6/{chapter}_draft6.md`, `_draft6/{chapter}_amplification_report.md`, `_draft6/{chapter}_amplification_nodes.json` |
| `S9` | `AG-06` | `engine.stage.run(S9)` | 출판 | `publication/output/{book_id}.epub`, `publication/output/{book_id}.pdf`, `publication/output/{book_id}_frontcover.png`, `publication/output/publication_manifest.json` |

정의 원본: [stage_definitions.json](/d:/solar_book/platform/core_engine/stage_definitions.json)

---

## 3. Agent Allocation

- `AG-IN`: proposal/toc를 공식 intake artifact로 고정
- `AG-AR`: 목적, 독자, 장 구조, 장별 목표 분량, 앵커 정책, 스타일, 품질 기준을 정의
- `AG-OM`: pending/blocked/gate_failed 상태를 읽고 work order 발행
- `AG-RS`: 최신성 기준, source queue, reference index, image manifest를 설계
- `AG-00`: 장 목표와 anchor budget을 반영한 raw guide와 chapter anchor plan 생성
- `AG-01`: raw guide를 따라 draft1 작성 후 표준 anchor block 주입
- `AG-01`: raw guide를 따라 draft1 작성 후 표준 anchor block 주입, live mode에서는 subsection node 순차 호출과 grounded brief 사용
- `AG-01`: 향후 `f_plan_segment -> f_design_narrative -> f_implement_uhd -> f_verify_density -> f_report_session` 구조로 강화
- `AG-02`: citations, freshness, appendix linkage를 review report로 구조화, live mode에서는 subsection review node별 `engine.model.grounded_research`를 순차 수행
- `AG-02`: 저작권/초상권/상업 이용 리스크를 `rights_review.json`으로 명시하고 appendix reference index와 연결
- `AG-03`~`AG-05`: 챕터 단위 병렬 처리
- `AG-05A`: `draft5`를 보존한 채 `draft6`에 reader-centered rewrite, tone/value amplification, 현장감 강화 적용
- `AG-06`: 책 단위 publication build 및 플랫폼 검증

정의 원본: [AGENT_SOPS.md](/d:/solar_book/platform/core_engine/AGENT_SOPS.md)

---

## 4. Artifact Contracts

모든 단계는 아래 규칙을 따른다.

1. 입력은 `platform/core_engine/stage_definitions.json`에 선언된 파일만 사용한다.
2. 출력은 선언된 위치에만 쓴다.
3. `chapter_id`가 필요한 stage는 계약 해석 시 반드시 명시한다.
4. Gate를 통과하지 못하면 다음 단계로 넘어갈 수 없다.

예시:

- `S0` 입력: `_inputs/intake_manifest.json`
- `S0` 출력:
  - `_master/BOOK_CONFIG.json`
  - `_master/WORD_TARGETS.json`
  - `_master/ANCHOR_POLICY.json`
  - `_master/BOOK_BLUEPRINT.md`
  - `_master/STYLE_GUIDE.md`
  - `_master/QUALITY_CRITERIA.md`
- `S2` 출력:
  - `research/reference_index.json`
  - `research/image_manifest.json`
  - `publication/appendix/REFERENCE_INDEX.md`
- `S3` 출력:
  - `manuscripts/_raw/{chapter_id}_raw.md`
  - `manuscripts/_raw/{chapter_id}_anchor_plan.json`
- `S9` 출력:
  - `publication/output/{book_id}.epub`
  - `publication/output/{book_id}.pdf`
  - `publication/output/{book_id}_frontcover.png`
  - `publication/output/publication_manifest.json`
  - `publication/output/seo_metadata.json`
  - `publication/output/store_listing.md`
- node execution 원칙:
  - `S4`, `S5`, `S8A`는 chapter 일괄 호출 대신 subsection node 순차 호출을 사용한다.
  - live model 호출은 `VERTEX_REQUEST_MIN_INTERVAL_MS` 간격을 준수한다.
- 수동 검수 인덱스:
  - `python tools/core_engine_cli.py build-stage-review-index --book-id with_the_king --book-root "d:\solar_book\books\with the King"`
  - 출력:
    - `verification/stage_review_index.json`
    - `verification/stage_review_index.md`
  - 목적: stage별 산출물 위치, 상태, 검수 포인트, runtime alert를 한 번에 검토

앵커 계약 요약:

- 앵커 ID 표준: `CH{00}_{TYPE}_{000}`
- 전역 앵커 카탈로그: `22`개 유형
- 주입 문법: `ANCHOR_START -> ANCHOR_SLOT -> ANCHOR_END`
- refinement 계열 `ER`, `FS`, `TA`, `LC`, `CS`, `CX`는 기본적으로 process anchor로 취급
- 외부 자료와 AI 생성 자산은 모두 `reference_index.json` 및 appendix reference와 연결

정의 원본:

- [anchor_type_catalog.json](/d:/solar_book/platform/core_engine/anchor_type_catalog.json)
- [ANCHOR_SPEC.md](/d:/solar_book/platform/core_engine/ANCHOR_SPEC.md)
- [ANCHOR_PIPELINE.md](/d:/solar_book/platform/core_engine/ANCHOR_PIPELINE.md)

---

## 5. Shared Memory / State / Gate

- 공유 메모리: [shared_memory_schema.json](/d:/solar_book/platform/core_engine/shared_memory_schema.json)
- 컨텍스트 팩 명세: [CONTEXT_PACK_SPEC.md](/d:/solar_book/platform/core_engine/CONTEXT_PACK_SPEC.md)
- 모델 라우팅 정책: [MODEL_ROUTING_POLICY.md](/d:/solar_book/platform/core_engine/MODEL_ROUTING_POLICY.md)
- 작업 지시 스키마: [work_order_schema.json](/d:/solar_book/platform/core_engine/work_order_schema.json)
- Gate 정의: [gate_definitions.json](/d:/solar_book/platform/core_engine/gate_definitions.json)

현재 구현된 공용 상태 축:

- `db/book_db.json`
- `db/WORK_ORDER.local.json`
- `db/PIPELINE_STATUS.local.json`
- `shared_memory/shared_memory.json`
- `shared_memory/context_packs/global/*.json`
- `shared_memory/context_packs/local/*.json`
- `shared_memory/context_packs/runtime/*.json`
- `platform/core_engine/runtime_registry.json`

컨텍스트 계층 원칙:

- 전역 특성은 `policy_pack`으로 고정한다.
- 지역 특성은 `book_context_digest`, `chapter_context_pack`, `node_context_pack`으로 분리한다.
- `S4`, `S5`, `S8A`는 더 이상 마스터 문서 원문을 직접 모델에 넣지 않고 distill된 context pack을 우선 사용한다.
- `S4` section expansion은 최대 `3`회로 제한한다.
- `S8A`는 canonical prose block만 대상으로 하며 장당 최대 `10`개 node만 허용한다.
- `S8A`는 `draft6 <= draft5 * 2.0` 가드레일을 따른다.
- `S4`, `S5`, `S8A`는 stage/section별 전역 모델 라우팅 정책을 따른다.
- `S4`, `S5`, `S8A` Gate는 이제 `context_budget_within_policy`를 포함한다.
- `S4` Gate는 `s4_expansion_cap_respected`를 포함한다.
- `S8A` Gate는 `s8a_rewrite_target_cap_respected`, `s8a_amplification_ratio_within_cap`를 포함한다.
- runtime telemetry는 `verification/runtime_telemetry_dashboard.json`에 집계된다.
- runtime telemetry는 `all_nodes_fallback`, `partial_node_fallback`, `context_budget_distilled` 경고를 함께 집계한다.
- work order는 이제 `runtime_alerts` 필드로 medium/high runtime 경고를 오케스트레이터에 노출한다.

모델 런타임 진단:

- [VERTEX_MODEL_GATEWAY.md](/d:/solar_book/docs/VERTEX_MODEL_GATEWAY.md)
- [`.env.example`](/d:/solar_book/.env.example)
- CLI:
  - `python tools\core_engine_cli.py show-model-config`
  - `python tools\core_engine_cli.py preview-model-request --task-type generate_structured --prompt "테스트"`

---

## 6. Current Validation Target

검증 대상 책은 [books/with the King](/d:/solar_book/books/with%20the%20King) 하나다.

현재 상태:

- intake bootstrap 완료
- chapter detection 완료: `17`개
- parts detection 완료: `4`개
- `S0 / AG-AR` 완료
- `S1 / AG-OM` 완료
- `S2 / AG-RS` 완료
- `S3 / AG-00` 완료
- `S4 / AG-01` 완료
- `S5 / AG-02` 완료
- `S6 / AG-03` 완료
- `S7 / AG-04` 완료
- `S8 / AG-05` 완료
- `S8A / AG-05A` 완료 (2026-03-18 전 챕터 재실행, gate=True)
- `S9 / AG-06` 마지막 출판 스냅샷 생성 완료
- `S6B / AG-IM` 신규 정의됨 — placeholder 8건 처리를 위한 독립 이미지 자산 스테이지
- 현재 pending stage: `S6B` (이미지 자산 수집 대기)
- 2026-03-15 live runtime update:
  - `VERTEX_API_KEY` 기반 express auth probe 통과
  - `structured JSON` 통과
  - `grounded research` 통과
  - `S4 ch01` live rerun 완료
  - `S5 ch01` live rerun 완료
- `S8A ch01` live rerun 완료
- `S8A` telemetry 기록: `request_variant`, token usage, fallback detail
- live model pacing: `VERTEX_REQUEST_MIN_INTERVAL_MS` 기반
- execution mode: `S4/S5/S8A subsection_nodes_sequential`
- `S4` draft1 budget tuned for realistic subsection-node runtime
- `ch01`, `ch02`에서 개선된 `S4` live drafting 검증 완료
- `ch02` end-to-end rerun 완료: `S4 -> S5 -> S6 -> S7 -> S8 -> S8A -> S9`
- `2026-03-15 ch04` rerun 완료: `S4 -> S5 -> S8A`
- `ch04` telemetry refresh 결과:
  - `S4` context budget: `4711 / 6000`, within budget
  - `S5` context budget: `4010 / 6500`, within budget
  - `S8A` context budget: `4177 / 5000`, within budget
  - `S8A` live rewrite는 `WinError 10013` 소켓 권한 오류로 heuristic fallback
- `2026-03-15 ch02 S8A` 재정규화 결과:
  - rewrite target node: `17 -> 10`
  - `S8A` context budget: `4166 / 5000`, within budget
  - fast remediation 이후 gate 결과: `completed`
  - 최종 잔여 이슈: `generic_phrase:먼저 보여주는 편이 좋다` 경고만 유지
- `runtime_telemetry_dashboard.md` 기준 model events: `178`
- `2026-03-15 ch03 S8A` rerun 결과:
  - `all_nodes_fallback -> partial_node_fallback`
  - `live_node_count: 0 -> 4`
  - gate 결과: `completed`
- `2026-03-15 ch04` 상태:
  - `S4`, `S5`, `S8A` 모두 `WinError 10013` 기반 `all_nodes_fallback` 경고 지속
  - gate는 heuristic fallback 경로로 통과하지만, 오케스트레이터는 `runtime_alerts`로 재시도 필요성을 인지한다.
- 새 core planning artifact:
  - `_master/WORD_TARGETS.json`
  - `_master/ANCHOR_POLICY.json`
  - `research/reference_index.json`
  - `research/image_manifest.json`
  - `publication/appendix/REFERENCE_INDEX.md`
  - `manuscripts/_draft1/{chapter}_node_manifest.json`
  - `manuscripts/_draft2/{chapter}_review_report.md`
  - `manuscripts/_draft2/{chapter}_review_nodes.json`
  - `manuscripts/_draft3/{chapter}_visual_plan.json`
  - `manuscripts/_draft4/{chapter}_draft4.md`
  - `manuscripts/_draft4/{chapter}_visual_bundle.json`
  - `manuscripts/_draft5/{chapter}_draft5.md`
  - `manuscripts/_draft5/{chapter}_proofreading_report.md`
  - `manuscripts/_draft6/{chapter}_draft6.md`
  - `manuscripts/_draft6/{chapter}_amplification_report.md`
  - `manuscripts/_draft6/{chapter}_amplification_nodes.json`
  - `publication/assets/generated/{anchor_id}.svg`
  - `publication/output/{book_id}.html`
  - `publication/output/google_books_book.css`
  - `publication/output/{book_id}.epub`
  - `publication/output/{book_id}.pdf`
  - `publication/output/{book_id}_frontcover.png`
  - `publication/output/publication_manifest.json`
  - `publication/output/seo_metadata.json`
  - `publication/output/store_listing.md`

출판 검증 메모:

- metadata validation: `pass`
- platform validation: `google_play_books_profile`
- EPUB: front cover image, embedded `NanumGothic`, toc nav, supported image types 검사
- PDF: portrait layout + `NanumGothic` 기반 렌더
- visual asset status: `structured_rendered=35`, `placeholder_rendered=8`
- placeholder 자산은 구조적으로 출판물에 반영됐지만, 외부 이미지/AI 최종 자산으로 교체되기 전까지는 운영상 경고로 남는다.

---

## 7. Cleanup Summary

정리 결과:

- 루트의 레거시 태양광 집필 자료, 예전 문서, 구형 빌드 스크립트, 보조 책 샘플을 `_archive/legacy_workspace_20260314/`로 이동
- `epub_builder_mcp.py`, `setup_epub_mcp.py`, `test_imports.py`는 레거시 도구로 분리
- `__pycache__`, Office 임시 잠금 파일은 제거

---

## 8. Next Runtime Step

다음 구현 단계는 `S6B 이미지 자산 수집 라운드 + S9 재빌드`이다.

목표 입력:

- `research/assets/{chapter_id}_asset_collection_manifest.json` (ch09~ch15, outro)
- `publication/assets/ingested/{chapter_id}/` — ext/usr/ai 소스별 이미지 배치 필요
- [IMAGE_ASSET_SPEC.md](/d:/solar_book/platform/core_engine/IMAGE_ASSET_SPEC.md)
- [GOOGLE_PLAY_BOOKS_PUBLICATION_GUIDE.md](/d:/solar_book/docs/GOOGLE_PLAY_BOOKS_PUBLICATION_GUIDE.md)

목표 출력:

- placeholder 8건 → 실자산 교체 (`cleared/{chapter}/ASSET_*`)
- 각 자산 `provenance.json` 완성
- S9 재빌드: EpubCheck 통과 출판본

S6B 이미지 소스 배치 방법:
- `ext` (외부 검색): `publication/assets/ingested/{chapter_id}/ext/{anchor_id}_ext_001_v001.jpg` 경로에 이미지 파일 배치
- `usr` (사용자 업로드): `publication/assets/ingested/{chapter_id}/usr/{anchor_id}_usr_001_v001.jpg` 경로에 배치
- `ai` (AI 생성): S6B AG-IM이 자동 호출 (IMAGEN_VISUAL_MODEL 기반)

현재 코어 파이프라인은 Google Play Books 친화 출력까지 end-to-end로 닫혔다.
