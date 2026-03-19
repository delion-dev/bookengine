# Stage Agent Maintenance Map

Date: 2026-03-16
Scope: `with_the_king` MetaGPT SOP pipeline maintenance view

## Why This Exists

유지보수 관점에서 필요한 것은 "현재 stage가 무엇을 책임지는가"와 "문제가 났을 때 어디부터 다시 해야 하는가"를 빠르게 판단하는 기준이다.

특히 이 프로젝트는 다음 원칙이 중요하다.

1. 초고 본문은 독자용 원고다.
2. `ANCHOR_START ... ANCHOR_END` 블록은 후속 stage를 위한 작업 지시 범위다.
3. anchor block 바깥 본문은 후속 stage에서 훼손되면 안 된다.

---

## Current Pipeline

기준 정의:

- [stage_definitions.json](/d:/solar_book/platform/core_engine/stage_definitions.json)
- [AGENT_SOPS.md](/d:/solar_book/platform/core_engine/AGENT_SOPS.md)
- [API_SPEC.md](/d:/solar_book/platform/core_engine/API_SPEC.md)
- [contracts.py](/d:/solar_book/engine_core/contracts.py)
- [stage_api.py](/d:/solar_book/engine_core/stage_api.py)

| Stage | Agent | Core R&R | Working Folder | Key Artifact Contract | If Broken, Restart From |
| --- | --- | --- | --- | --- | --- |
| `S-1` | `AG-IN` | intake normalization | `_inputs` | `intake_manifest.json` | `S-1` |
| `S0` | `AG-AR` | architecture, book policy, quality policy | `_master` | `BOOK_CONFIG`, `WORD_TARGETS`, `ANCHOR_POLICY`, `BOOK_BLUEPRINT`, `STYLE_GUIDE`, `QUALITY_CRITERIA` | `S0` |
| `S1` | `AG-OM` | orchestration, work order, stage state | `db` | `WORK_ORDER.local.json`, `PIPELINE_STATUS.local.json` | `S1` |
| `S2` | `AG-RS` | research plan, appendix refs, image manifest | `research`, `publication/appendix` | `research_plan.json`, `source_queue.json`, `citations.json`, `reference_index.json`, `image_manifest.json`, `REFERENCE_INDEX.md` | `S2` |
| `S3` | `AG-00` | chapter raw guide + anchor planning | `manuscripts/_raw` | `{chapter}_raw.md`, `{chapter}_anchor_plan.json` | `S3` |
| `S4` | `AG-01` | prose-only draft + stage telemetry | `manuscripts/_draft1` | `{chapter}_draft1_prose.md`, `node_manifest`, `segment_plan`, `narrative_design`, `density_audit`, `session_report` | `S4` |
| `S4A` | `AG-01B` | anchor location/type decision + canonical block injection | `manuscripts/_draft1` | `{chapter}_draft1.md`, `anchor_injection_report`, `anchor_scope_report` | `S4A` |
| `S5` | `AG-02` | fact/rights/freshness review | `manuscripts/_draft2` | `{chapter}_draft2.md`, `review_report`, `rights_review`, `review_nodes` | `S5` |
| `S6` | `AG-03` | anchor interpretation + visual planning | `manuscripts/_draft3` | `{chapter}_draft3.md`, `visual_plan.json`, `visual_support.json` | `S6` |
| `S6A` | `AG-AS` | offline asset collection handoff + naming/binding contract | `research/assets`, `publication/assets/cleared` | `{chapter}_asset_collection_manifest.json`, `ASSET_COLLECTION_{chapter}.md` | `S6A` |
| `S7` | `AG-04` | visual rendering and manuscript integration | `manuscripts/_draft4` | `{chapter}_draft4.md`, `visual_bundle.json` | `S7` |
| `S8` | `AG-05` | copyedit / technical QA | `manuscripts/_draft5` | `{chapter}_draft5.md`, `proofreading_report.md` | `S8` |
| `S8A` | `AG-05A` | optional editorial polish | `manuscripts/_draft6` | `{chapter}_draft6.md`, `amplification_report.md`, `amplification_nodes.json` | optional |
| `S9` | `AG-06` | publication assembly | `publication/output` | `html`, `epub`, `pdf`, `frontcover`, `publication_manifest`, `seo_metadata`, `store_listing` | `S9` |

---

## Current Weak Spot

현재는 `S4/S4A` 분리가 반영됐고, 남은 유지보수 약점은 `S7`이 reader-facing 시각 출력과 기술 주석을 같은 결과물 안에 섞기 쉬웠다는 점이다.

1. 시각 카드 자체
2. appendix ref / support gap / provenance 메타

이 둘이 독자용 출력에서 섞이면 이런 문제가 생긴다.

- 표와 callout이 기술 진단 표처럼 보일 수 있다.
- `Support gaps`, `Appendix ref`가 출판 본문에 섞일 수 있다.
- 독자용 본문과 운영용 메타의 경계가 흐려진다.
- 오프라인 자산 수집 라운드와 출판 라운드의 역할 구분이 모호해진다.

---

## AG-01 Review

### Option A. Keep One Stage, Split Outputs

구조:

- `S4 / AG-01`
- 출력:
  - `{chapter}_draft1_prose.md`
  - `{chapter}_draft1.md` anchored manuscript
  - 기존 telemetry artifact

장점:

- stage id 변경이 적다.
- 기존 orchestration 수정 폭이 작다.
- 빠른 패치가 가능하다.

단점:

- stage 상태는 여전히 하나라 resume granularity가 떨어진다.
- prose만 바꾸는 재작업과 anchor만 바꾸는 재작업을 gate 수준에서 분리하기 어렵다.
- 유지보수자가 `S4` 내부 substep을 항상 알아야 한다.

### Option B. Split AG-01 Into Two Stages

구조:

- `S4 / AG-01 Writer`
- `S4A / AG-01B Anchor Injector`

권장 출력:

- `S4`
  - `manuscripts/_draft1/{chapter}_draft1_prose.md`
  - `manuscripts/_draft1/{chapter}_node_manifest.json`
  - `manuscripts/_draft1/{chapter}_segment_plan.json`
  - `manuscripts/_draft1/{chapter}_narrative_design.json`
  - `manuscripts/_draft1/{chapter}_density_audit.json`
  - `manuscripts/_draft1/{chapter}_session_report.json`
- `S4A`
  - `manuscripts/_draft1/{chapter}_draft1.md`
  - `manuscripts/_draft1/{chapter}_anchor_injection_report.json`
  - `manuscripts/_draft1/{chapter}_anchor_scope_report.json`

장점:

- prose와 anchor insertion 책임이 명확히 분리된다.
- 유지보수 시 `본문 문제 -> S4`, `앵커 문제 -> S4A`로 바로 판단 가능하다.
- 후속 stage의 입력 기준이 더 선명해진다.
- anchor-safe contract를 gate로 강제하기 쉽다.
- stage별 agent R&R이 문서와 코드에서 더 일치한다.

단점:

- stage id 하나가 늘어난다.
- orchestration, gate, contract, CLI를 함께 수정해야 한다.

### Recommendation

`Option B`, 즉 `S4`와 `S4A` 분리를 권장한다.

이유:

1. 이 프로젝트는 maintenance-driven pipeline이다.
2. 문제 발생 시 "어디부터 다시 할지"가 곧 운영 비용이다.
3. anchor block은 본문과 성격이 다른 artifact이므로 stage도 분리하는 편이 맞다.

즉 `AG-01 workflow상 하나의 작업으로 묶는 것`보다 `두 개의 stage/agent 책임으로 분리하는 것`이 더 안전하다.

---

## Recommended Target Pipeline

| Stage | Agent | Core R&R | Working Folder | Artifact Contract | Restart Rule |
| --- | --- | --- | --- | --- | --- |
| `S3` | `AG-00` | raw guide, anchor plan | `manuscripts/_raw` | `{chapter}_raw.md`, `{chapter}_anchor_plan.json` | structure/anchor spec 이슈면 `S3` |
| `S4` | `AG-01` | 독자용 초고 작성 | `manuscripts/_draft1` | `{chapter}_draft1_prose.md` + node/session artifacts | 본문 품질/분량/구조 이슈면 `S4` |
| `S4A` | `AG-01B` | anchor 위치 결정, anchor type 확정, canonical block 삽입 | `manuscripts/_draft1` | `{chapter}_draft1.md`, `anchor_injection_report.json`, `anchor_scope_report.json` | anchor 위치/범위/문법 이슈면 `S4A` |
| `S5` | `AG-02` | review, rights, freshness, appendix linkage | `manuscripts/_draft2` | `draft2.md`는 본문 불변, sidecar review artifacts 생성 | 근거/권리 이슈면 `S5` |
| `S6` | `AG-03` | anchor block 해석, visual plan 생성 | `manuscripts/_draft3` | `draft3.md`는 본문 불변, `visual_plan.json`, `visual_support.json` | visual brief/renderer mapping 이슈면 `S6` |
| `S6A` | `AG-AS` | 오프라인 실자산 수집용 handoff와 파일명/경로 계약 고정 | `research/assets`, `publication/assets/cleared` | `asset_collection_manifest.json`, `ASSET_COLLECTION_{chapter}.md` | 자산 파일명/appendix ref/binding 이슈면 `S6A` |
| `S7` | `AG-04` | anchor block 내부를 실제 시각 블록으로 렌더 | `manuscripts/_draft4` | `draft4.md`, `visual_bundle.json` | 시각 렌더/markup 이슈면 `S7` |
| `S8` | `AG-05` | publication QA, structure check, artifact QA | `manuscripts/_draft5` | validation/report 중심 | 시각 통합/형식 검증 이슈면 `S8` |
| `S8A` | `AG-05A` | optional editorial enhancement or report-only mode | `manuscripts/_draft6` | optional branch | 선택적 stage |
| `S9` | `AG-06` | HTML/EPUB/PDF build | `publication/output` | final publication bundle | 출판 조립/검증 이슈면 `S9` |

---

## Artifact Boundary Rule

### Prose Artifact

- 독자가 읽는 원고
- anchor block 바깥 본문
- 후속 stage에서 의미/흐름/문장 손상을 허용하지 않음

### Anchor Block Artifact

- 후속 stage를 위한 작업 지시 범위
- 위치, 유형, placement, source mode, appendix ref, caption을 가짐
- 후속 stage는 이 범위 안에서만 작업

### Sidecar Artifact

- review report
- rights review
- visual plan
- visual support
- visual bundle
- publication manifest

이들은 본문을 설명하거나 검증하는 자료이지, 본문을 덮어쓰는 자료가 아니다.

---

## Gate Recommendation

분리 구조를 채택하면 아래 gate가 추가되는 편이 좋다.

### `S4` Gate

- prose structure complete
- min length reached
- no anchor block inserted yet

### `S4A` Gate

- canonical anchor pair inserted
- anchor ids unique
- slot count valid
- anchor scope integrity pass

### `S6` Gate

- body text unchanged outside anchor blocks
- visual plan exists
- renderer mapping complete

### `S6A` Gate

- asset collection manifest exists
- appendix ref, target filename, target dir defined
- offline handoff packet exists

### `S7` Gate

- all anchor slots resolved
- rendered markup publication-safe
- body text unchanged outside anchor blocks

---

## Practical Maintenance Rule

문제 유형별로 재시작 지점은 이렇게 잡는다.

- 초고 내용 자체가 잘못됨: `S4`
- anchor 위치/범위/유형이 잘못됨: `S4A`
- 시각 설계가 잘못됨: `S6`
- 자산 파일명/부록 ref/수집 경로가 잘못됨: `S6A`
- Mermaid/표/이미지 렌더가 잘못됨: `S7`
- EPUB/PDF 조립이나 폰트/메타 문제: `S9`

이렇게 분리해야 유지보수 담당자가 "전체를 다시" 하지 않고 최소 범위만 재작업할 수 있다.

---

## Final Decision

유지보수성과 resume clarity를 우선하면:

- `AG-01`을 단일 stage로 유지하는 것보다
- `AG-01 Writer`와 `AG-01B Anchor Injector`로 분리하는 편이 더 적합하다.

최소 변경 패치가 목표라면 먼저 `S4` 안에서 `draft1_prose.md`와 `draft1.md`를 분리해도 된다.

하지만 운영 모델을 오래 가져갈 생각이라면 최종 목표는 분명하다.

- `S4 = prose`
- `S4A = anchor injection`
- `S6A = asset collection handoff`
- `S5+ = anchor-safe downstream`
