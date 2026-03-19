# Anchor Specification

## 1. Purpose

이 문서는 원고 집필 과정에서 사용하는 표준 앵커 주입 문법, 앵커 유형, 앵커 결정 규칙을 정의한다.

핵심 원칙:

- 앵커는 장식이 아니라 시각 보조 계약이다.
- 모든 앵커는 타입, 위치, 자산 모드, 레퍼런스 추적 정보를 가져야 한다.
- 외부 자료와 AI 생성 이미지는 모두 부록 레퍼런스 인덱스에 기록되어야 한다.
- 운영 메타는 anchor로 표현하지 않고 별도 meta block 문법을 사용한다.

## 2. Standard Injection Grammar

표준 주입 문법은 HTML comment block 기반이다.

```md
<!-- ANCHOR_START id="CH09_EP_001" type="EP" placement="after_section:Context" asset_mode="external_image" ingestion_source="ext" priority="high" reference_ids="REF_CH09_VIS_001" appendix_ref="REF_CH09_VIS_001" provenance_ref="PROV_CH09_VIS_001" caption="청령포 실경: 단종이 유배된 강가 섬의 현재 전경" -->
[ANCHOR_SLOT:CH09_EP_001]
<!-- ANCHOR_END id="CH09_EP_001" -->
```

필수 속성:

- `id`: 전역적으로 유일한 anchor identifier
- `type`: `anchor_type_catalog.json`에 정의된 타입
- `placement`: `after_section:Hook|Context|Insight|Takeaway` 또는 `after_heading:*`
- `asset_mode`: `external_image`, `ai_generated_image`, `table`, `timeline`, `chart`, `map`, `diagram`, `design_card`
- `ingestion_source`: `ext`(외부검색) | `usr`(사용자업로드) | `ai`(AI생성) | `eng`(엔진렌더) — 이미지 앵커 필수, 구조화 앵커 생략 가능
- `priority`: `high`, `medium`, `low`
- `reference_ids`: 부록 인덱스에 연결되는 reference id 목록
- `appendix_ref`: 대표 reference id
- `provenance_ref`: `PROV_{CHAPTER}_{SEQ}` — 이미지 앵커 필수, provenance JSON 포인터
- `caption`: 시각 요소의 독자용 설명 (한국어 우선, 최대 50자, 운영 메타 미포함)

이미지 앵커 캡션 suffix 규칙:
- `ext`: `(출처: {site_name})` 추가
- `usr`: suffix 없음
- `ai`: `(AI 생성 이미지, {model})` 추가
- `eng`: suffix 없음

이미지 자산 명세 원본: [IMAGE_ASSET_SPEC.md](/d:/solar_book/platform/core_engine/IMAGE_ASSET_SPEC.md)

## 2A. Reader-Facing Annotation Rule

독자에게 보이는 앵커 결과물의 표기 원칙:

- 시각화 제목, 표 머리글, 요약 박스 문구는 한국어 우선으로 작성한다.
- 섹션 표기는 `도입 (Hook)`처럼 한국어 + 괄호 영문 규칙을 따른다.
- `appendix_ref`, `support_gaps`, `anchor_id`, `renderer_hint`는 reader-facing prose에 직접 노출하지 않는다.
- 위 운영 정보는 HTML comment, `visual_bundle.json`, `reference_index.json`, `image_manifest.json`에서 관리한다.

즉 `Support gaps: numeric_series_unparsed` 같은 문구는 출판 본문이 아니라 렌더 진단 정보다.

## 3. Decision Rule

앵커 결정은 아래 순서로 이뤄진다.

1. `WORD_TARGETS.json`에서 chapter target과 anchor budget을 읽는다.
2. `ANCHOR_POLICY.json`에서 chapter별 preferred anchor types를 읽는다.
3. chapter part와 title signal을 보고 타입 우선순위를 확정한다.
4. 타입별 기본 placement를 적용한다.
5. 외부 참조 또는 AI 생성 필요 여부를 `asset_mode`로 명시한다.
6. 모든 앵커는 `REF_{chapter}_VIS_*` 형식의 appendix reference id를 즉시 예약한다.

## 4. Type Catalog

정의 원본은 [anchor_type_catalog.json](/d:/solar_book/platform/core_engine/anchor_type_catalog.json)이다.

현재 표준 카탈로그는 `22`개 유형이다.

코드 기준 22개 유형:

- `BT` Block Table
- `PF` Process Flow
- `HN` Hierarchy Node
- `TL` Time Line
- `DS` Data Stat
- `RM` Relation Map
- `AI` AI Illust
- `EP` External Photo
- `TD` Technical Drawing
- `VE` Video Embed
- `SB` Summary Box
- `CO` Call Out
- `FN` Foot Note
- `MF` Math Formula
- `CB` Code Block
- `HL` Hyper Link
- `ER` AI Eraser
- `FS` Fact Sync
- `TA` Tone Adjust
- `LC` Logic Check
- `CS` Censorship
- `CX` Context Bridge

## 5. Pairing Rule

앵커는 start-end pair를 기본으로 한다.

정확히는:

- `ANCHOR_START`
- 내부 `ANCHOR_SLOT`
- `ANCHOR_END`

즉 pair의 경계 안에 slot이 들어가는 구조다.

이유:

- `START/END`는 메타데이터와 범위를 정의한다.
- `SLOT`은 추후 자동 시각화 산출물이 대체될 위치를 고정한다.

주의:

- `ER`, `FS`, `TA`, `LC`, `CS`, `CX`는 refinement category라서 기본적으로 process anchor로 운용한다.
- 즉 이 6개는 카탈로그에는 포함되지만, 일반적인 시각 슬롯 삽입보다 `S5/S8` 품질 파이프라인에서 주로 사용된다.

## 6. Appendix Rule

- 외부 이미지: URL, 출처명, 접근일, 사용 목적을 기록한다.
- AI 생성 이미지: 모델명, 프롬프트 요약, 리비전, 사용 목적을 기록한다.
- 어떤 시각 자료도 appendix reference가 없는 상태로 출판 단계에 들어갈 수 없다.
- 오프라인 자산 수집 파일명은 `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext` 규칙을 기본으로 한다.
- `Appendix ref` 번호는 `REFERENCE_INDEX.md`의 실제 행과 1:1로 대응해야 한다.
- placeholder 자산의 권리/provenance 마감은 별도 offline acquisition round에서 처리한다.

## 7. Meta Block Boundary

anchor와 meta는 분리해야 한다.

- anchor: 시각화/구조화 치환 대상
- meta block: 운영상 힌트, 검토 메모, 제거 대상

meta block 문법은 [META_BLOCK_SPEC.md](/d:/solar_book/docs/META_BLOCK_SPEC.md)를 따른다.
