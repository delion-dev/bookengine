# Anchor Pipeline

## 1. Answer First

현재 실행 카탈로그는 이제 `22`개 유형 기준으로 정의된다.

중요한 점:

- 원고에 삽입되는 구조는 단순 `start-end` 2점이 아니라 `START + SLOT + END` 3요소다.
- 논리적 쌍은 `ANCHOR_START` 와 `ANCHOR_END`다.
- `ANCHOR_SLOT`은 추후 자동 시각화 결과가 꽂히는 렌더링 포인트다.

## 2. Canonical Grammar

```md
<!-- ANCHOR_START id="CH09_EP_001" type="EP" placement="after_section:Context" asset_mode="external_image" priority="high" reference_ids="REF_CH09_VIS_001" appendix_ref="REF_CH09_VIS_001" caption="..." -->
[ANCHOR_SLOT:CH09_EP_001]
<!-- ANCHOR_END id="CH09_EP_001" -->
```

규칙:

- `START`와 `END`는 반드시 같은 `anchor_id`를 가져야 한다.
- `SLOT`은 반드시 pair 내부에 1개만 존재해야 한다.
- 자동 시각화 단계는 `SLOT`을 렌더된 결과로 치환하고 `START/END` 메타데이터는 보존하거나 주석 처리한다.
- `START ... END` 전체 블록은 "시각화 작업 범위"다.
- 이 블록 바깥의 본문은 anchor injection 이후 stage에서 훼손하면 안 된다.

## 2.1 Anchor Scope Contract

앵커 계약의 핵심은 문법보다 범위다.

1. `draft prose`는 독자용 본문이다.
2. `anchor block`은 후속 stage를 위한 작업 지시서이자 교체 가능 영역이다.
3. `non-anchor prose`는 시각화 stage 이후에도 의미와 흐름이 보존되어야 한다.

즉 후속 stage는 다음만 할 수 있다.

- anchor block 내부 `SLOT`을 해석한다.
- `START/END` 메타를 읽어 renderer dispatch를 결정한다.
- block 내부를 표, Mermaid, HTML, 이미지 참조, SVG 등으로 치환한다.

후속 stage가 하면 안 되는 일:

- anchor block 바깥 문단 재서술
- 검토 메타를 독자용 본문에 삽입
- visual summary 같은 운영 섹션을 원고 본문에 추가

## 3. Pipeline Stages

### S0: Book-Level Anchor Policy

출력:

- `_master/WORD_TARGETS.json`
- `_master/ANCHOR_POLICY.json`

역할:

- 장별 anchor budget 확정
- 사용할 anchor family와 대표 타입 우선순위 결정
- 표준 문법과 appendix 정책 고정

### S2: Reference Reservation

출력:

- `research/reference_index.json`
- `research/image_manifest.json`
- `publication/appendix/REFERENCE_INDEX.md`

역할:

- 각 anchor에 대응하는 appendix reference id 예약
- 외부 이미지 / AI 생성 / 표 / 맵 / 다이어그램의 소스 모드 정의
- 권리 검토와 provenance requirement 미리 선언

### S3: Chapter Anchor Plan

출력:

- `manuscripts/_raw/{chapter_id}_anchor_plan.json`

역할:

- chapter별 anchor id 생성
- placement, asset mode, caption, appendix ref 매핑
- 삽입용 `START + SLOT + END` 블록 생성

### S4: Draft1 Prose

출력:

- `manuscripts/_draft1/{chapter_id}_draft1_prose.md`

역할:

- 초고 본문을 먼저 완성한다.
- 영화 장은 장면, 연기, 스틸컷, 실제 장소 감각, 성지순례 동기를 직접 서술한다.
- 이 시점의 원고는 독자용 prose이며, 후속 stage 작업 지시가 본문 바깥에 새로 끼어들면 안 된다.

### S4A: Anchor Injection

출력:

- `manuscripts/_draft1/{chapter_id}_draft1.md`

역할:

- 초고 본문을 훼손하지 않고 section 기준으로 canonical anchor block을 실제 삽입
- 이 시점부터 앵커는 원고 계약의 일부가 된다
- 이 시점 이후 후속 stage는 anchor block 범위 안에서만 시각 작업을 수행한다

### S5: Review / Reference Integrity

출력:

- `manuscripts/_draft2/{chapter_id}_review_report.md`
- `research/citations.json`

역할:

- 본문 anchor와 appendix reference linkage 검증
- freshness 정책과 citation attachment 기록
- 검토 메타는 sidecar artifact에만 남기고, 본문은 불변을 유지

### S6: Visual Planning

출력:

- `manuscripts/_draft3/{chapter_id}_visual_plan.json`

역할:

- anchor별 `render_strategy`, `source_mode`, `renderer_hint` 확정
- `acquisition_brief`, `generation_brief`, `design_brief` 생성
- 이 파일이 자동 시각화의 직접 입력이 된다
- 본문은 재작성하지 않고 anchor block 해석 규칙만 확정한다

### S7: Auto Visualization

예정 출력:

- `manuscripts/_draft4/{chapter_id}_visual_bundle.json`
- `manuscripts/_draft4/{chapter_id}_draft4.md`

역할:

- `visual_plan.json`을 읽어 renderer dispatch
- `asset_mode`별 처리:
  - `external_image`: 오프라인 수집 라운드를 위한 대체 시안 연결
  - `ai_generated_image`: 오프라인 생성 라운드를 위한 대체 시안 연결
  - `table`, `timeline`, `chart`, `map`, `diagram`, `design_card`: 구조화 렌더러 호출
- 결과를 `visual_bundle`로 저장
- `ANCHOR_SLOT`을 최종 visual markup 또는 asset reference로 치환
- 치환 범위는 반드시 `ANCHOR_START ... ANCHOR_END` 블록 내부로 한정한다
- `appendix_ref`, `support_gaps`, `renderer_hint`는 sidecar/comment로만 남기고 reader-facing output에 직접 노출하지 않는다

### S8/S8A: Validation-Only Preference

anchor-safe operating model에서는 `S8`을 "검수/리포트" 중심으로 운용하고, `S8A`는 선택적 editorial polish stage로만 사용한다.

- 허용: 구조 검사, 시각 블록 완성도 검사, 출판 품질 점검
- 비권장: anchor block 바깥 문단을 다시 쓰는 증폭/재서술
- 주의: `S8A`를 기본 경로에 두면 재앵커링과 재검수 루프가 늘어나므로, 기본 출판 경로는 `draft5`를 우선한다.

## 3A. S6A Offline Asset Collection Handoff

실제 외부 이미지, 스틸컷, 유튜브, AI 렌더 수급은 파이프라인 내부 live render가 아니라 별도 offline round에서 다룬다.

- 예약 위치: `reference_index.json`, `image_manifest.json`, `REFERENCE_INDEX.md`
- 기본 파일명: `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext`
- 기본 저장 경로: `publication/assets/cleared/{chapter_id}/`
- 공식 handoff artifact:
  - `research/assets/{chapter_id}_asset_collection_manifest.json`
  - `publication/assets/cleared/{chapter_id}/ASSET_COLLECTION_{chapter_id}.md`
- 이 라운드의 결과는 이후 `S7` 또는 `S9` 재빌드 때 교체 자산으로 연결된다.

### S9: Publication

출판 stage는 원고를 다시 쓰는 단계가 아니다.

- 입력: anchor visual이 통합된 최종 원고
- 역할: EPUB/PDF/HTML 생성, 메타데이터 내장, 폰트/호환성 검증
- 금지: raw Mermaid 문법이나 unresolved anchor slot을 그대로 출판물에 남기는 행위

## 4. Renderer Dispatch Model

권장 dispatch key:

- `asset_mode`
- `renderer_hint`
- `source_mode`
- `render_strategy`

예시:

- `table + table_renderer` -> table composition service
- `timeline + timeline_renderer` -> timeline builder
- `map + map_renderer` -> map layout service
- `external_image + panel_renderer` -> external acquisition + panel composer
- `ai_generated_image + image_renderer` -> model gateway + provenance writer

## 5. 22 Anchor Families

대표 family:

- `visual`
- `asset`
- `structure`
- `refinement`

카탈로그 원본:

- [anchor_type_catalog.json](/d:/solar_book/platform/core_engine/anchor_type_catalog.json)

코드 묶음:

- `visual`: `BT`, `PF`, `HN`, `TL`, `DS`, `RM`
- `asset`: `AI`, `EP`, `TD`, `VE`
- `structure`: `SB`, `CO`, `FN`, `MF`, `CB`, `HL`
- `refinement`: `ER`, `FS`, `TA`, `LC`, `CS`, `CX`

## 6. Why This Matters

이 구조가 필요한 이유는 앵커를 "단순 표시"가 아니라 "자동 시각화 가능한 실행 계약"으로 만들기 위해서다.

즉:

1. 본문은 `anchor_id`를 가진다.
2. reference index는 provenance를 가진다.
3. visual plan은 renderer dispatch 정보를 가진다.
4. S7은 이를 읽어 자동 시각화를 수행한다.

이렇게 해야 사람이 중간에 판단을 덜 해도 파이프라인이 안정적으로 이어진다.
