# Agent SOPs

## 목적

이 문서는 각 에이전트의 핵심 작업 SOP를 정의한다.
모든 에이전트는 이 문서와 [PROJECT_SOP.md](/d:/solar_book/platform/core_engine/PROJECT_SOP.md),
[API_SPEC.md](/d:/solar_book/platform/core_engine/API_SPEC.md)를 함께 준수한다.

---

## 공통 규칙

모든 에이전트 공통:

1. `engine.session.open`으로 시작한다.
2. `engine.contract.resolve_inputs`로 공식 입력만 조회한다.
3. 직접 경로 추론을 금지한다.
4. 출력은 `engine.contract.register_output`으로 등록한다.
5. 상태 전이는 `engine.stage.transition`으로만 처리한다.
6. 종료 전 `engine.session.close`를 호출한다.

### Anchor Scope Rule

`AG-01`이 독자용 초고와 canonical anchor block을 확정한 뒤에는, 후속 stage가 anchor block 바깥 본문을 임의로 재작성하면 안 된다.

- 허용 범위: `ANCHOR_START ... ANCHOR_END` 블록 내부 해석/치환
- 금지 범위: block 바깥 문단 재서술, 검토 메타 삽입, 운영 summary 본문 혼입
- 검토/권리/시각 설계 정보는 sidecar artifact에 남긴다.

### Reader Annotation Rule

- 시각화 제목, 표 머리글, callout 문구는 한국어 우선으로 작성한다.
- section heading은 `도입 (Hook)`, `맥락 (Context)`, `통찰 (Insight)`, `실전 포인트 (Takeaway)` 규칙을 따른다.
- `appendix_ref`, `support_gaps`, `anchor_id`, `renderer_hint`는 독자용 본문이 아니라 comment/sidecar로 관리한다.

### Meta Block Rule

운영상 메모가 본문 파일 안에 꼭 필요하다면 별도 meta block 문법을 사용한다.

- 문법: `META_START ... META_END`
- 목적: 검토 힌트, 시각 설계 힌트, rights note, repair note
- 성격: anchor가 아니라 제거 대상 운영 블록
- 원칙: 가능한 경우 sidecar artifact를 우선하고, meta block은 최소화한다.

---

## AG-IN Intake Agent

### 책임

- 사용자 입력을 정식 intake artifact로 정규화

### 입력

- `_inputs/proposal.md`
- `_inputs/toc_seed.md`

### 출력

- `_inputs/intake_manifest.json`

### SOP

1. 입력 파일 존재 확인
2. 파일 형식 정규화
3. 필수 섹션 추출
4. intake manifest 작성
5. `input_contract_pass` Gate 요청

### 실패 시

- 입력 문서 누락
- proposal/toc 추출 불가

---

## AG-AR Architect

### 책임

- 책 구조, 정책, 품질 기준 설계

### 입력

- intake manifest

### 출력

- BOOK_CONFIG
- WORD_TARGETS
- ANCHOR_POLICY
- BOOK_BLUEPRINT
- STYLE_GUIDE
- QUALITY_CRITERIA

### SOP

1. 책 목적과 독자 정의
2. 파트/챕터 구조 설계
3. 장별 목표 분량과 stage 하한선 계산
4. 품질 기준과 Gate 기준 정의
5. 앵커 타입/위치/문법 정책 정의
6. 산출물 저장과 blueprint validation 수행

### 실패 시

- 챕터 구조 불명확
- 품질 기준 누락
- 지역 API 정책 미정

---

## AG-OM Orchestrator

### 책임

- 전체 파이프라인 상태 감시
- 우선순위와 병렬성 통제
- 재작업 지시

### 입력

- book state
- blueprint
- gate 결과

### 출력

- WORK_ORDER.local.json
- PIPELINE_STATUS.local.json

### SOP

1. 각 stage 상태 스냅샷 생성
2. 병목 단계 계산
3. pending item 우선순위 계산
4. 병렬 가능 항목 분류
5. blocked/gate_failed 재배정
6. work order 발행

### 실패 시

- state snapshot 불일치
- 병렬 금지 항목 충돌

---

## AG-RS Research Strategist

### 책임

- 조사 전략과 source queue 설계

### 입력

- BOOK_CONFIG
- blueprint
- proposal
- toc seed

### 출력

- research_plan.json
- source_queue.json
- reference_index.json
- image_manifest.json
- publication/appendix/REFERENCE_INDEX.md

### SOP

1. 검증이 필요한 주장 식별
2. BOOK_CONFIG의 audience segment와 rights policy를 조사 계획에 반영
3. 챕터별 조사 질문 생성
4. source policy 정의
5. 최신성 기준 정의
6. citation 구조 설계
7. 외부 자료/AI 이미지 reference index scaffold 생성

### 실패 시

- 검색 질문 누락
- 최신성 기준 부재

---

## AG-00 Planner

### 책임

- 챕터별 raw guide 생성

### 입력

- BOOK_CONFIG
- blueprint
- WORD_TARGETS
- ANCHOR_POLICY
- research plan

### 출력

- `_raw/{chapter}_raw.md`
- `_raw/{chapter}_anchor_plan.json`

### SOP

1. 챕터 목표와 독자 가정 확인
2. `BOOK_BLUEPRINT.md`의 mission, structural strategy, part lens, chapter notes를 직접 해석
3. "책 내용을 쓸 것"과 "책 쓰는 방법을 설명하지 말 것" 규칙을 raw guide에 명시
4. BOOK_CONFIG의 segment/payoff/rights policy를 챕터 가이드에 반영
5. 장 논리 흐름 설계
6. 절별 핵심 논점 작성
7. 장 목표 분량과 anchor budget 반영
8. 포함/제외 항목 정리
9. 예상 근거/시각 자료와 appendix ref 예약

### 실패 시

- 장 흐름 누락
- blueprint 해석 누락
- 절별 지침 누락

---

## AG-AS Asset Collection Steward

### 책임

- 오프라인 자산 수집 라운드를 위한 공식 handoff artifact 생성
- appendix ref, 파일명 규칙, 저장 경로, binding 상태를 고정

### 입력

- `_draft3/{chapter}_draft3.md`
- `_draft3/{chapter}_visual_plan.json`
- `_draft3/{chapter}_visual_support.json`
- `research/reference_index.json`
- `research/image_manifest.json`

### 출력

- `research/assets/{chapter}_asset_collection_manifest.json`
- `publication/assets/cleared/{chapter}/ASSET_COLLECTION_{chapter}.md`

### SOP

1. visual plan의 anchor별 source mode 확인
2. appendix ref와 image manifest를 1:1로 정합
3. 오프라인 수집 대상 anchor에 canonical 파일명과 저장 경로 확정
4. 이미 수집된 cleared asset이 있으면 binding 상태 기록
5. handoff artifact를 저장하고 `S7`이 소비할 수 있게 등록

### 실패 시

- appendix ref 누락
- target filename/path 누락
- offline binding 상태 추적 불가

---

## AG-IM Image Asset Manager

### 책임

- 이미지 자산 수집·생성·검증·등록
- 소스별(ext/usr/ai) provenance 기록
- cleared 자산을 S7 입력 경로에 확정

### 입력

- `research/assets/{chapter_id}_asset_collection_manifest.json`
- `research/image_manifest.json`
- `manuscripts/_draft3/{chapter_id}_visual_plan.json`
- `publication/assets/ingested/{chapter_id}/ext/` — 외부 검색 이미지 원본
- `publication/assets/ingested/{chapter_id}/usr/` — 사용자 업로드 이미지
- `publication/assets/ingested/{chapter_id}/ai/` — AI 생성 이미지

### 출력

- `publication/assets/cleared/{chapter_id}/ASSET_{chapter_id}_*_v*.{ext}` — 최종 승인 자산
- `publication/assets/cleared/{chapter_id}/{anchor_id}_provenance.json` — provenance 레코드
- `research/assets/{chapter_id}_ingestion_report.json` — 처리 결과 요약

### SOP

1. `asset_collection_manifest`에서 `ext`, `usr`, `ai` 대상 anchor 목록 확인
2. 소스별 처리:
   - `ext`: `ingested/ext/`에서 원본 파일 확인 → 권리 검토 → `cleared/`로 복사 + provenance 기록
   - `usr`: `ingested/usr/`에서 원본 파일 확인 → 사용자 권리 선언 확인 → `cleared/`로 복사 + provenance 기록
   - `ai`: `image_manifest.json`의 prompt/model 확인 → AI 모델 호출 → `ingested/ai/`에 저장 → `cleared/`로 복사 + provenance 기록
3. 각 자산에 대해 `{anchor_id}_provenance.json` 생성
4. `image_manifest.json`의 `ingestion_status` 갱신 (`pending` → `cleared` 또는 `rejected`)
5. `ingestion_report.json` 작성
6. `image_asset_ingestion_pass` Gate 요청

### 명명 규칙

- 수집 단계: `{anchor_id}_{source_code}_{seq}_v{version}.{ext}`
- 승인 단계: `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v{version}.{ext}`
- Provenance: `{anchor_id}_provenance.json`
- 전체 규칙 원본: [IMAGE_ASSET_SPEC.md](/d:/solar_book/platform/core_engine/IMAGE_ASSET_SPEC.md)

### 실패 시

- ingested 파일 없음 (소스 미도착)
- 권리 검토 실패 (`clearance_status: rejected`)
- AI 생성 모델 오류
- provenance 필수 필드 미기재

---

## AG-01 Writer

### 책임

- raw guide 기반 실질 초고 작성
- 내부 step orchestration을 통한 coverage 확보
- 영화/역사/장소/여행 감각이 직접 살아 있는 reader-facing prose 작성

### 입력

- raw guide
- WORD_TARGETS
- source queue

### 출력

- `_draft1/{chapter}_draft1_prose.md`
- `_draft1/{chapter}_node_manifest.json`
- `_draft1/{chapter}_segment_plan.json`
- `_draft1/{chapter}_narrative_design.json`
- `_draft1/{chapter}_density_audit.json`
- `_draft1/{chapter}_session_report.json`

### 실행 메커니즘

- `plan_segments -> design_narrative -> implement_segments -> verify_density -> report_session`
- chapter one-shot이 아니라 segment node 순차 실행
- context는 section/segment brief 중심으로 절감
- live가 전부 실패해도 fallback draft는 생성하되, `session_report`에 alert를 남김
- 책 내용을 쓰는 대신 집필 방식을 해설하는 메타 문장을 금지
- 영화 장의 경우 장면, 연기, 스틸컷, 실제 장소 감각, 성지순례 동기를 직접 서술
- 실용 팁과 여행 유도력은 후속 앵커에만 미루지 않고 prose 안에도 자연스럽게 심음

### SOP

1. `f_plan_segment`로 장을 segment node로 분해
2. `f_design_narrative`로 독자 payoff와 연결 구조 설계
3. `f_implement_uhd`로 segment node를 순차 집필
4. blueprint 구조 적용
5. 장면-감정-장소-실용 정보가 실제 내용으로 쓰였는지 점검
6. `f_verify_density`로 분량/라이브 기여/구조 감사
7. `f_report_session`으로 stage 판정
8. chapter memory 업데이트
9. prose-only draft 저장

## AG-01B Anchor Injector

### 책임

- prose를 훼손하지 않고 canonical anchor block 삽입
- 후속 stage 작업 범위를 `ANCHOR_START ... ANCHOR_END`로 고정

### 입력

- `_draft1/{chapter}_draft1_prose.md`
- `_raw/{chapter}_anchor_plan.json`
- `ANCHOR_POLICY`

### 출력

- `_draft1/{chapter}_draft1.md`
- `_draft1/{chapter}_anchor_injection_report.json`
- `_draft1/{chapter}_anchor_scope_report.json`

### SOP

1. prose와 anchor plan을 로드
2. placement와 anchor type을 검증
3. prose 바깥 본문 불변을 유지한 채 anchor block 삽입
4. anchor scope report 생성
5. `draft1_anchor_complete` Gate 요청

### 실패 시

- 구조 누락
- 분량 미달
- 근거 없는 주장 다수
- fallback-only completion

---

## AG-02 Reviewer

### 책임

- 사실 검증
- 최신성 반영
- 톤/표현 정제
- 저작권/초상권/상업 이용 리스크 리뷰
- 본문 불변 유지

### 입력

- draft1
- citations
- reference index
- research plan
- image manifest
- WORD_TARGETS
- style policy

### 출력

- draft2
- review report
- rights review json

### SOP

1. 검증 포인트 추출
2. section별 grounded review node 생성
3. research/citation 재확인
4. appendix reference linkage 확인
5. freshness rule 적용
6. 오래된 주장 갱신
7. 외부 텍스트와 시각 자산의 rights/clearance 리스크 판정
8. 뉴스/기사/UGC/영화 스틸/외부 사진/AI 이미지의 사용 정책 분류
9. 문체/톤 정제
10. review report와 rights review 작성

### 범위 제한

- `draft1`의 anchor block 바깥 본문은 훼손하지 않는다.
- review 결과는 `review_report`, `rights_review`, `review_nodes`에 기록한다.
- 본문에는 검토 메타 heading을 삽입하지 않는다.
- 필요한 운영 메모는 meta block 또는 sidecar에만 남긴다.

### 실패 시

- 출처 불충분
- 검증 불가 주장 잔존
- 고위험 rights item 미표시

---

## AG-03 Visual Architect

### 책임

- 시각화 포인트 설계
- anchor block 해석 규칙 정의

### 입력

- draft2
- anchor plan
- ANCHOR_POLICY
- image manifest
- reference index

### 출력

- draft3
- visual_plan.json
- visual_support.json

### SOP

1. draft2와 anchor plan 정합성 확인
2. image manifest와 appendix ref 연결
3. visual type 분류
4. priority 지정
5. render/acquisition/generation brief 작성
6. review 메타와 시각 근거를 visual_support로 분리
7. visual plan 저장

### 범위 제한

- 본문 문단을 다시 쓰지 않는다.
- anchor block의 placement/type/caption/source contract를 해석해 `visual_plan`으로 내보낸다.
- meta block이 남아 있으면 visual planning 전에 제거한다.

### 실패 시

- anchor 중복
- visual plan 불완전

---

## AG-04 Visual Builder

### 책임

- 표/도식/시각 자산 생성 및 통합

### 입력

- draft3
- visual plan
- visual_support.json

### 출력

- draft4
- visual bundle

### SOP

1. visual plan 로드
2. visual_support packet 로드
3. 표/mermaid/이미지 플레이스홀더 생성
4. 본문 통합
5. 미처리 항목 기록
6. visual render Gate 요청

### 범위 제한

- 작업 범위는 `ANCHOR_START ... ANCHOR_END` 블록 내부다.
- block 바깥 prose는 보존한다.
- `ANCHOR_SLOT`은 출판 가능한 HTML/SVG/asset reference로 치환하는 것이 목표다.
- meta block은 렌더 대상이 아니라 제거 대상이다.

### 실패 시

- 렌더링 실패
- 미처리 anchor 다수

---

## AG-05 Copy Editor

### 책임

- 최종 교정
- 구조/스타일/기술 품질 최종 판정
- anchor-safe 운용 시 validation/report 중심 수행

### 입력

- draft4
- style guide
- quality criteria

### 출력

- draft5
- proofreading report
- gate decision payload

### SOP

1. 구조 검사
2. 내용 논리 검사
3. 언어/표기 검사
4. 기술 형식 검사
5. Gate pass/fail 판정

### 실패 시

- 반환 대상 stage 식별 불가
- 중대한 구조 결함

---

## AG-05A Optional Editorial Polish

### 책임

- 승인된 경우에만 선택적 polish 수행
- 기존 원고 보존
- tone/value 미세 보정

### 입력

- draft5
- style guide
- quality criteria
- book blueprint

### 출력

- draft6
- amplification report

### SOP

1. 구조와 앵커 보존 상태 확인
2. 정말 필요한 경우에만 rewrite block node 생성
3. reader-value 약한 문단 식별
4. 사실 변경 없이 제한적 polish 수행
5. 재앵커링이나 downstream 재루프를 유발하지 않도록 범위 제한
6. amplification report 작성
7. amplification Gate pass/fail 판정

### 실패 시

- 구조 보존 실패
- 의미 왜곡 위험
- 독자 가치 증폭 부족

### Anchor-Safe Note

anchor-safe 운용에서는 `AG-05A`를 publication 필수 경로로 두지 않고, report-only 또는 선택적 polish stage로 운용하는 것이 권장된다.

---

## AG-06 Publisher

### 책임

- 출판 파일 생성
- 플랫폼 호환성 검증
- 최종 원고 불변 상태 유지

### 입력

- draft5 bundle
- metadata bundle
- optional draft6 bundle

### 출력

- EPUB
- PDF
- publication manifest

### SOP

1. publication metadata 로드
2. 챕터별 publication source를 `draft5` 우선, `completed draft6` 선택 사용 규칙으로 결정
3. 출력 포맷별 빌드 실행
4. 메타데이터 검증
5. Google Books/Play 호환성 검증
6. release package 생성

### 범위 제한

- 출판 단계는 시각 블록이 통합된 원고를 조립하는 단계다.
- raw Mermaid, unresolved anchor slot, 운영 메타 heading이 남아 있으면 실패로 본다.
- meta block이 남아 있어도 실패로 본다.

### 실패 시

- 빌드 실패
- 메타데이터 불충분
- 플랫폼 검증 실패

---

## 에이전트 반환 규칙

- AG-05는 AG-01, AG-02, AG-04로 반환 가능
- AG-05A는 AG-05 또는 AG-02로 반환 가능
- AG-06은 AG-05 또는 AG-AR로 반환 가능
- AG-OM은 어떤 stage도 `pending` 또는 `blocked`로 재배정 가능

반환 시 필수:

- 반환 대상
- 반환 사유
- 수정 지시
- 재진입 조건
