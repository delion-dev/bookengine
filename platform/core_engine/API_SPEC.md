# Core Engine API Specification

## 1. 범위

이 명세서는 새 책 집필 시스템의 전역 API와 지역 API를 정의한다.

목표:

- 모든 주요 로직을 API로 래핑
- 검증된 API를 Core Engine으로 고정
- 에이전트가 자유 편집이 아니라 안정된 엔진을 재사용하게 함

---

## 2. 핵심 개체

### 2.1 BookIdentity

```json
{
  "book_id": "with_the_king",
  "display_name": "with the King",
  "book_root": "D:/solar_book/books/with the King"
}
```

### 2.2 ArtifactRef

```json
{
  "artifact_id": "draft1.ch03",
  "book_id": "with_the_king",
  "stage_id": "S4",
  "path": "manuscripts/_draft1/ch03_draft1.md",
  "schema": "draft_markdown@1.0",
  "checksum": "sha256:..."
}
```

### 2.3 StageRunRequest

```json
{
  "book_id": "with_the_king",
  "stage_id": "S4",
  "chapter_id": "ch03",
  "input_artifacts": ["raw.ch03", "research_pack.ch03"],
  "policy_bundle": ["book.style", "book.quality", "book.domain"]
}
```

### 2.4 GateDecision

```json
{
  "book_id": "with_the_king",
  "stage_id": "S8",
  "chapter_id": "ch03",
  "decision": "pass",
  "return_to_stage": null,
  "issues": []
}
```

---

## 3. 전역 API

전역 API는 Core Engine이 소유한다.
책 내용을 품지 않으며, 절차와 실행 메커니즘만 제공한다.

### 3.1 Constitution API

#### `engine.constitution.load`

- 목적: Core Engine 헌법과 고정 규칙 로드
- 입력: `engine_version`
- 출력: `constitution_bundle`

#### `engine.constitution.assert_compliance`

- 목적: 요청이 헌법 위반인지 점검
- 입력: `operation`, `book_id`, `stage_id`
- 출력: `compliance_result`

---

### 3.2 Registry API

#### `engine.registry.list_books`

- 목적: 등록된 책 목록 조회
- 입력: 없음
- 출력: `BookIdentity[]`

#### `engine.registry.get_book`

- 목적: 특정 책 컨텍스트 조회
- 입력: `book_id`
- 출력: `BookIdentity + registry metadata`

#### `engine.registry.register_book`

- 목적: 새 책 등록
- 입력: `BookIdentity`, `bootstrap_result`
- 출력: `registry_ack`

---

### 3.3 Bootstrap API

#### `engine.bootstrap.create_book`

- 목적: 기획안과 목차 초안으로 새 책 구조 생성
- 입력:
  - `book_id`
  - `display_name`
  - `proposal_path`
  - `toc_seed_path`
- 출력:
  - `bootstrap_manifest`
  - `created_paths[]`

#### `engine.bootstrap.normalize_inputs`

- 목적: 원본 입력 문서를 표준 입력 아티팩트로 정규화
- 입력: `source_files[]`
- 출력: `proposal.md`, `toc_seed.md`, `intake_manifest.json`

---

### 3.4 Blueprint API

#### `engine.blueprint.generate`

- 목적: 기획안과 목차 초안을 BOOK_BLUEPRINT로 변환
- 입력:
  - `proposal_artifact`
  - `toc_seed_artifact`
  - optional `author_note`
- 출력:
  - `BOOK_CONFIG.json`
  - `BOOK_BLUEPRINT.md`
  - `STYLE_GUIDE.md`
  - `QUALITY_CRITERIA.md`

#### `engine.blueprint.validate`

- 목적: blueprint 완결성 검증
- 입력: `book_id`
- 출력: `blueprint_validation_report`

---

### 3.5 Artifact Contract API

#### `engine.contract.resolve_inputs`

- 목적: 특정 stage의 공식 입력 아티팩트 조회
- 입력: `book_id`, `stage_id`, `chapter_id`
- 출력: `ArtifactRef[]`

#### `engine.contract.validate_input`

- 목적: 입력 아티팩트가 계약에 맞는지 검사
- 입력: `stage_id`, `ArtifactRef[]`
- 출력: `contract_validation_result`

#### `engine.contract.register_output`

- 목적: 출력 아티팩트 등록
- 입력: `ArtifactRef`
- 출력: `artifact_registry_ack`

---

### 3.5A Context API

Context API는 전역 정책과 책/장/노드 지역 정보를 분리해 모델 호출용 팩으로 컴파일한다.

전역 특성:

- `policy_pack`은 Core Engine 소유
- stage/gate/constitution 기반
- 책별 override 금지

지역 특성:

- `book_context_digest`, `chapter_context_pack`, `node_context_pack`
- 책/장/노드 상태에 따라 갱신
- shared memory와 book artifact를 distill한 결과

#### `engine.context.build_policy_pack`

- 목적: stage별 전역 정책팩 생성
- 입력: `stage_id`
- 출력: `policy_pack`

#### `engine.context.build_book_digest`

- 목적: 책 전체 컨텍스트를 distill한 지역 digest 생성
- 입력: `book_id`
- 출력: `book_context_digest`

#### `engine.context.build_chapter_pack`

- 목적: 장별 목표/기억/연구/앵커 의무를 묶은 지역 팩 생성
- 입력: `book_id`, `chapter_id`, `stage_id`
- 출력: `chapter_context_pack`

#### `engine.context.build_node_pack`

- 목적: subsection/block 단위의 최소 실행 컨텍스트 생성
- 입력: `book_id`, `chapter_id`, `stage_id`, `node_payload`
- 출력: `node_context_pack`

#### `engine.context.materialize`

- 목적: policy/book/chapter/node pack을 model context_artifacts로 조립
- 입력: `stage_id`, optional `chapter_id`, optional `node_payload`
- 출력: `context_bundle`

#### `engine.context.measure`

- 목적: prompt + context pack의 토큰 예산을 추정
- 입력: `prompt_text`, `context_artifacts`
- 출력: `context_budget_report`

---

### 3.6 Work Order API

#### `engine.work_order.issue`

- 목적: AG-OM이 작업 지시 생성
- 입력: `pipeline_snapshot`
- 출력: `WORK_ORDER`

#### `engine.work_order.get_next`

- 목적: 다음 실행 작업 반환
- 입력: `book_id`, optional `agent_id`
- 출력: `work_item`

#### `engine.work_order.ack`

- 목적: 작업 수락/완료/반환 기록
- 입력: `work_item_id`, `status`, `note`
- 출력: `ack_result`

---

### 3.7 Stage Runtime API

#### `engine.stage.run`

- 목적: stage executor 진입점
- 입력: `StageRunRequest`
- 출력: `StageRunResult`

#### `engine.stage.get_definition`

- 목적: stage 계약 조회
- 입력: `stage_id`
- 출력: `stage_definition`

#### `engine.stage.transition`

- 목적: 상태 전이 실행
- 입력: `book_id`, `chapter_id`, `from`, `to`
- 출력: `transition_result`

---

### 3.8 Research API

#### `engine.research.plan`

- 목적: 조사 계획 수립
- 입력: `book_id`, `chapter_id`, `blueprint`, `proposal`
- 출력: `research_plan.json`

#### `engine.research.collect`

- 목적: 출처 수집
- 입력: `research_plan`
- 출력: `source_pack.json`

#### `engine.research.citations`

- 목적: 인용 구조화
- 입력: `raw_sources`
- 출력: `citations.json`

#### `engine.research.refresh`

- 목적: 오래된 출처 재검증
- 입력: `citation_set`, `max_age_days`
- 출력: `refresh_report`

---

### 3.9 Target Planning API

#### `engine.targets.plan`

- 목적: 목차 확정 이후 chapter별 목표 분량과 stage별 진행 하한선 계산
- 입력: `book_id`, `intake_manifest`, `book_blueprint`
- 출력: `WORD_TARGETS.json`

#### `engine.targets.get_chapter_target`

- 목적: 특정 장의 목표 분량 조회
- 입력: `book_id`, `chapter_id`
- 출력: `chapter_target`

---

### 3.10 Anchor API

#### `engine.anchor.load_catalog`

- 목적: 전역 앵커 타입 카탈로그 조회
- 입력: 없음
- 출력: `anchor_type_catalog`

#### `engine.anchor.plan_policy`

- 목적: book-level anchor policy 생성
- 입력: `book_id`, `WORD_TARGETS`, `BOOK_BLUEPRINT`
- 출력: `ANCHOR_POLICY.json`

#### `engine.anchor.plan_chapter`

- 목적: chapter별 anchor budget, 타입, 위치, appendix ref 예약
- 입력: `book_id`, `chapter_id`, `chapter_target`, `anchor_policy`
- 출력: `{chapter_id}_anchor_plan.json`

#### `engine.anchor.inject`

- 목적: 표준 anchor block 문법으로 원고에 anchor 삽입
- 입력: `draft1_prose_artifact`, `anchor_plan`
- 출력: `draft_artifact_with_anchors`
- 실행 규칙:
  - prose block 바깥 문장은 바꾸지 않는다.
  - 섹션 heading은 `도입 (Hook)`, `맥락 (Context)`, `통찰 (Insight)`, `실전 포인트 (Takeaway)` 규칙을 따른다.

---

### 3.11 Reference / Appendix API

#### `engine.references.index`

- 목적: 외부 텍스트/시각 자료 참조 인덱스 생성
- 입력: `book_id`, `research_plan`, `anchor_policy`
- 출력: `reference_index.json`

#### `engine.references.image_manifest`

- 목적: 외부 이미지 및 AI 생성 이미지 수요 계획 생성
- 입력: `book_id`, `anchor_policy`
- 출력: `image_manifest.json`

#### `engine.assets.collect`

- 목적: 오프라인 실자산 수집 라운드를 위한 appendix ref, 파일명, 저장 경로, binding 상태를 고정
- 입력:
  - `draft3_artifact`
  - `visual_plan_artifact`
  - `visual_support_artifact`
  - `reference_index`
  - `image_manifest`
- 출력:
  - `asset_collection_manifest.json`
  - `asset_collection_handoff.md`
- 실행 규칙:
  - 저작권 해결 자체는 offline round에서 수행한다.
  - `appendix_ref`, `target_filename`, `target_dir`는 이 API가 정식으로 고정한다.
  - 이후 `engine.visual.render`는 cleared asset이 있으면 그것을 우선 바인딩한다.
- 실행 규칙:
  - 실제 자산 수집은 offline acquisition round에서 수행한다.
  - manifest에는 `appendix_reference_id`, 파일명 stub, 예정 저장 경로가 예약된다.

#### `engine.references.build_appendix`

- 목적: 출판 부록용 reference index 문서 생성
- 입력: `reference_index`, `image_manifest`
- 출력: `publication/appendix/REFERENCE_INDEX.md`

---

### 3.12 Model Gateway API

모든 AI 모델 연동은 이 API를 통해서만 수행한다.

전역 특성:

- stage/task/section별 모델 선택 규칙은 Core Engine이 소유한다.
- 책 로컬 설정은 route 입력값만 바꾸고, 정책 본문은 바꾸지 않는다.

지역 특성:

- chapter part
- section key
- node 목적

이 값들은 전역 정책 해석에 쓰이는 지역 입력이다.

#### `engine.model.route_provider`

- 목적: 공급자 및 모델 선택
- 입력: `task_type`, `cost_profile`, `grounding_required`
- 출력: `provider_route`

#### `engine.model.resolve_stage_route`

- 목적: stage/task/section별 전역 모델 라우팅 정책 해석
- 입력: `stage_id`, `task_type`, optional `chapter_part`, optional `section_key`
- 출력: `provider_route + routing_policy`

#### `engine.model.generate_text`

- 목적: 일반 텍스트 생성
- 입력:
  - `provider_route`
  - `system_policy_ref`
  - `prompt`
  - `context_artifacts[]`
- 출력: `generated_text`
- 실행 규칙:
  - live API 호출은 `VERTEX_REQUEST_MIN_INTERVAL_MS` 간격을 반드시 준수한다.
  - `429` 또는 timeout은 `VERTEX_MAX_RETRIES`, `VERTEX_RETRY_BACKOFF_SECONDS` 정책으로 자동 재시도한다.
  - 대형 chapter payload 대신 subsection node 단위 호출을 기본 전략으로 사용한다.

#### `engine.model.generate_structured`

- 목적: JSON 스키마 기반 생성
- 입력:
  - `provider_route`
  - `schema_id`
  - `prompt`
  - `context_artifacts[]`
- 출력: `structured_payload`

#### `engine.model.grounded_research`

- 목적: Google AI grounded mode 또는 동등 기능으로 조사 보강
- 입력:
  - `query_set`
  - `source_policy`
  - `citation_required=true`
- 출력:
  - `grounded_summary`
  - `source_links[]`

#### `engine.model.safety_check`

- 목적: 민감도/정책 위반 검사
- 입력: `text`
- 출력: `safety_report`

Google AI 연동 원칙:

- Google AI Studio, Gemini API, Vertex AI 중 어느 공급자를 쓰더라도 외부에 직접 노출하지 않는다.
- 책별 프롬프트는 지역 API가 공급하고, 호출 메커니즘은 Model Gateway가 고정한다.
- stage별 모델 선택은 [MODEL_ROUTING_POLICY.md](/d:/solar_book/platform/core_engine/MODEL_ROUTING_POLICY.md)와 [model_routing_policy.json](/d:/solar_book/platform/core_engine/model_routing_policy.json)에 따른다.
- `.env`는 오직 Model Gateway만 해석한다.
- Core Engine 표준 런타임 키:
  - `VERTEX_PROJECT_ID`
  - `VERTEX_REGION`
  - `VERTEX_AUTH_MODE`
  - `VERTEX_API_KEY` 또는 `VERTEX_ACCESS_TOKEN`
  - `VERTEX_ENABLE_LIVE_CALLS`
  - `VERTEX_REQUEST_MIN_INTERVAL_MS`
  - `VERTEX_MAX_RETRIES`
  - `VERTEX_RETRY_BACKOFF_SECONDS`
- 엔진 표준 엔드포인트:
  - `api_key` 모드: express endpoint
  - `access_token` 모드: standard endpoint

---

### 3.12A Telemetry API

#### `engine.telemetry.build_dashboard`

- 목적: 모델 호출, context budget, node manifest를 책 단위로 집계
- 입력: `book_id`, `book_root`
- 출력:
  - `verification/runtime_telemetry_dashboard.json`
  - `verification/runtime_telemetry_dashboard.md`

---

### 3.13 Writer/Review/Copyedit API

#### `engine.writer.compose`

- 목적: raw guide와 조사 패키지로 초고 생성
- 입력: `book_id`, `chapter_id`, `raw_artifact`, `source_pack`
- 출력: `draft1_artifact`, `section_node_manifest`
- 실행 규칙:
  - `도입 (Hook)/맥락 (Context)/통찰 (Insight)/실전 포인트 (Takeaway)`를 독립 작업 노드로 순차 호출한다.
  - 각 노드는 이전 섹션 요약과 grounded brief를 컨텍스트로 받는다.
  - 이 API는 prose-only draft를 생성한다.
  - 책 내용을 어떻게 써야 하는지 설명하는 메타 문장을 금지한다.
  - 영화 장은 장면, 연기, 스틸컷 감각, 실제 장소 감각, 성지순례 동기를 직접 서술한다.

#### `engine.writer.anchor_inject`

- 목적: prose-only draft에 canonical anchor block 삽입
- 입력: `draft1_prose_artifact`, `anchor_plan`, `ANCHOR_POLICY`
- 출력: `draft1_with_anchors`, `anchor_injection_report`, `anchor_scope_report`
- 실행 규칙:
  - anchor block은 후속 stage의 작업 지시 범위다.
  - prose block 바깥 문장은 바꾸지 않는다.

#### `engine.review.run`

- 목적: 사실 검증/현행화/톤 정제
- 입력: `draft1_artifact`, `citations`, `style_policy`
- 출력: `draft2_artifact`, `review_report`, `review_node_manifest`
- 실행 규칙:
  - review는 section node별 grounded research를 순차 수행한 뒤 결과를 합친다.
  - 검토 메타는 sidecar로만 남기고, anchor block 바깥 본문은 불변을 유지한다.
  - 꼭 필요한 운영 메모는 `META_START ... META_END` 블록으로만 남긴다.

#### `engine.copyedit.run`

- 목적: 최종 교정
- 입력: `draft4_artifact`, `style_policy`, `quality_policy`
- 출력: `draft5_artifact`, `proofreading_report`
- 실행 규칙:
  - anchor-safe mode에서는 검수/리포트 우선, 본문 재서술 최소화

#### `engine.gate.decide`

- 목적: 합격/반환 판정
- 입력: `stage_output_bundle`
- 출력: `GateDecision`

#### `engine.amplify.run`

- 목적: 기존 원고를 보존한 채 tone/value amplification 수행
- 입력: `draft5_artifact`, `style_policy`, `quality_policy`, `blueprint`
- 출력: `draft6_artifact`, `amplification_report`, `amplification_node_manifest`
- 실행 규칙:
  - prose block을 rewrite node로 쪼개 순차 호출한다.
  - 노드 실패 시 전체 중단보다 부분 fallback을 우선한다.
  - anchor-safe mode에서는 선택적 stage로만 쓰고, 기본 출판 경로에서는 `draft5`를 우선한다.

---

### 3.14 Visual API

#### `engine.visual.plan`

- 목적: 시각 앵커 설계
- 입력: `draft2_artifact`, `ANCHOR_POLICY`, `image_manifest`
- 출력: `visual_plan.json`, `draft3_artifact`
- 실행 규칙:
  - anchor block의 metadata와 surrounding prose를 읽어 visual plan만 정의한다.
  - 본문은 다시 쓰지 않는다.
  - meta block은 plan 입력 전 제거하거나 sidecar로 승격한다.

#### `engine.visual.render`

- 목적: Mermaid/표 렌더링
- 입력: `draft3_artifact`, `visual_plan.json`
- 출력: `visual_bundle`, `draft4_artifact`
- 실행 규칙:
  - renderer dispatch는 anchor block 단위로 실행한다.
  - `ANCHOR_SLOT` 치환은 반드시 `ANCHOR_START ... ANCHOR_END` 범위 안에서만 수행한다.
  - `META_START ... META_END`는 렌더 대상이 아니라 제거 대상이다.
  - `appendix_ref`, `support_gaps`, `anchor_id`는 기본적으로 HTML comment 또는 sidecar artifact로 남기고 reader-facing prose에는 직접 노출하지 않는다.

#### `engine.visual.integrate`

- 목적: 시각 산출물과 본문 통합
- 입력: `draft3_artifact`, `visual_bundle`
- 출력: `draft4_artifact`
- 실행 규칙:
  - block 바깥 prose는 byte-level에 가깝게 보존하는 것이 원칙이다.

---

### 3.15 Publication API

#### `engine.publish.build_epub`

- 목적: EPUB 생성
- 입력: `book_id`, `draft5_bundle`, `metadata_bundle`
- 출력: `epub_artifact`
- 실행 규칙:
  - unresolved anchor slot, raw Mermaid, 운영 메타가 남으면 실패 처리한다.
  - meta block이 남아 있어도 실패 처리한다.

#### `engine.publish.build_pdf`

- 목적: PDF 생성
- 입력: `book_id`, `draft5_bundle`, `metadata_bundle`
- 출력: `pdf_artifact`
- 실행 규칙:
  - 출판 단계는 원고 재작성 단계가 아니라 조립/렌더/검증 단계다.

#### `engine.publish.validate_metadata`

- 목적: 메타데이터 적합성 검사
- 입력: `epub_artifact`
- 출력: `metadata_validation_report`

#### `engine.publish.validate_google_play`

- 목적: Google Play/Books 호환성 검사
- 입력: `epub_artifact`
- 출력: `platform_validation_report`

#### `engine.publish.package_release`

- 목적: 최종 배포 패키지 조립
- 입력: `publication_artifacts[]`
- 출력: `publication_manifest.json`

---

### 3.16 Session/Runtime API

#### `engine.session.open`

- 목적: 책/에이전트/단계 컨텍스트 초기화
- 입력: `book_id`, optional `agent_id`
- 출력: `session_bundle`

#### `engine.session.close`

- 목적: 세션 종료와 로그 정리
- 입력: `session_id`, `memo`
- 출력: `session_close_report`

#### `engine.runtime.diagnose`

- 목적: 환경 진단
- 입력: 없음
- 출력: `runtime_diagnostics`

---

## 4. 지역 API

지역 API는 책별 설정과 콘텐츠 정책을 제공한다.
전역 API와 동일한 형태를 갖되, 값은 책마다 다르다.

### 4.1 Book Profile API

#### `book.profile.get`

- 목적: 책 기본 설정 조회
- 입력: `book_id`
- 출력: `BOOK_CONFIG.json`

### 4.2 Outline API

#### `book.outline.get`

- 목적: 표준 목차 조회
- 입력: `book_id`
- 출력: `toc_seed.md` 또는 정제된 TOC

### 4.3 Style API

#### `book.style.get`

- 목적: 책별 문체/톤/표기 규칙 조회
- 입력: `book_id`
- 출력: `STYLE_GUIDE.md`

### 4.4 Quality API

#### `book.quality.get`

- 목적: 책별 품질 기준 조회
- 입력: `book_id`
- 출력: `QUALITY_CRITERIA.md`

### 4.5 Domain Knowledge API

#### `book.domain_knowledge.resolve`

- 목적: 책별 도메인 지식 패키지 조회
- 입력: `book_id`, `chapter_id`
- 출력: `knowledge_pack`

### 4.6 Word Target API

#### `book.word_target.get`

- 목적: 책별 장 분량 계획 조회
- 입력: `book_id`, optional `chapter_id`
- 출력: `WORD_TARGETS.json` 또는 `chapter_target`

### 4.7 Visual Policy API

#### `book.visual_policy.get`

- 목적: 책별 anchor policy와 visual rule 조회
- 입력: `book_id`
- 출력: `ANCHOR_POLICY.json`

### 4.8 Reference Policy API

#### `book.reference_policy.get`

- 목적: 책별 외부 자료 및 appendix 정책 조회
- 입력: `book_id`
- 출력: `reference_policy_bundle`

### 4.9 Metadata API

#### `book.metadata.get`

- 목적: 책별 출판 메타데이터 조회
- 입력: `book_id`
- 출력: `metadata_bundle`

### 4.10 Local Asset API

#### `book.assets.list`

- 목적: 책별 표지/이미지/부가 자산 조회
- 입력: `book_id`
- 출력: `asset_manifest`

---

## 5. 전역/지역 경계 규칙

전역 API가 가져서는 안 되는 것:

- 특정 책 제목
- 특정 챕터 개수
- 특정 도메인 용어
- 특정 독자층
- 특정 스타일 상수

지역 API가 가져도 되는 것:

- 제목과 부제
- 챕터/파트 구조
- 톤앤매너
- 전문 용어
- 이미지 정책
- 메타데이터 정책

---

## 6. `with_the_king` 적용 예

공식 입력:

- `books/with the King/_inputs/proposal.md`
- `books/with the King/_inputs/toc_seed.md`

공식 출력 예:

- `books/with the King/_master/BOOK_CONFIG.json`
- `books/with the King/_master/WORD_TARGETS.json`
- `books/with the King/_master/ANCHOR_POLICY.json`
- `books/with the King/_master/BOOK_BLUEPRINT.md`
- `books/with the King/db/book_db.json`
- `books/with the King/research/reference_index.json`
- `books/with the King/publication/appendix/REFERENCE_INDEX.md`
- `books/with the King/manuscripts/_draft1/ch01_draft1.md`
- `books/with the King/publication/output/*.epub`

---

## 7. 구현 규칙

1. 에이전트는 직접 파일 경로를 계산하지 않는다.
2. 파일 I/O는 모두 `ArtifactRef`와 API를 통해서만 수행한다.
3. Core Engine API는 버전 필드를 반드시 가진다.
4. Core Engine API는 구조화된 응답(JSON)을 기본 출력으로 사용한다.
5. Markdown 문서는 사람이 읽는 설명이며, 실행 기준은 API와 스키마다.
