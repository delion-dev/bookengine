# Image Asset Specification

버전: 1.0 | 작성일: 2026-03-18

## 1. 목적

이 문서는 이미지 자산의 수집·생성·등록·검증 전 과정을 표준화한다.
외부 검색, 사용자 업로드, AI 생성 세 가지 소스를 단일 파이프라인에서 처리하며,
모든 이미지는 앵커 블록과 1:1로 계약되고 appendix reference에 provenance가 기록된다.

---

## 2. 이미지 소스 타입

| 코드 | 소스 | 설명 |
|---|---|---|
| `ext` | external_search | 웹 검색을 통해 수집한 외부 이미지 |
| `usr` | user_upload | 사용자가 직접 제공한 이미지 (촬영본, 보유 저작물 등) |
| `ai` | ai_generated | AI 모델로 생성한 이미지 |
| `eng` | engine_render | 엔진 내부 구조화 렌더러가 생성한 SVG/표 (S7 자동 처리) |

`eng` 타입은 S7에서 자동 처리된다. S6B는 `ext`, `usr`, `ai` 세 소스만 담당한다.

---

## 3. 파일·폴더 명명 규칙

### 3.1 폴더 구조

```
publication/assets/
├── ingested/                      # S6B 수집 단계 원본 보관
│   └── {chapter_id}/
│       ├── ext/                   # external_search 원본
│       ├── usr/                   # user_upload 원본
│       └── ai/                    # ai_generated 원본
├── cleared/                       # S6B 검증·승인된 최종 자산 (S7 입력)
│   └── {chapter_id}/
│       └── ASSET_COLLECTION_{chapter_id}.md   # handoff 인덱스
└── generated/                     # eng 타입 — S7 엔진 자동 생성 SVG
```

### 3.2 파일명 규칙

**수집 단계 (ingested/):**

```
{anchor_id}_{source_code}_{seq}_v{version}.{ext}
```

예시:
- `CH09_EP_001_ext_001_v001.jpg`  — 외부 검색 이미지 1번째
- `CH09_EP_001_usr_001_v001.jpg`  — 사용자 업로드
- `CH09_EP_001_ai_001_v001.png`   — AI 생성 이미지
- `CH99_AI_002_ai_001_v002.png`   — AI 생성 2차 리비전

**승인 단계 (cleared/):**

```
ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v{version}.{ext}
```

예시:
- `ASSET_CH09_EP_001_v001.jpg`
- `ASSET_OUTRO_AI_002_v001.png`

규칙:
- `version`은 1부터 시작하며 재생성/교체 시 +1 증가
- `ext`는 jpg, png, webp, svg 허용
- `seq`는 001부터 시작하는 3자리 정수
- 파일명에 공백, 특수문자 금지

### 3.3 Provenance 파일

각 cleared 자산에 대응하는 provenance JSON:

```
publication/assets/cleared/{chapter_id}/{anchor_id}_provenance.json
```

예시: `publication/assets/cleared/ch09/CH09_EP_001_provenance.json`

---

## 4. Reference Index 스키마 (이미지 항목)

`research/image_manifest.json` 내 각 이미지 항목은 아래 필드를 포함한다.

```json
{
  "image_id": "IMG_CH09_001",
  "chapter_id": "ch09",
  "anchor_id": "CH09_EP_001",
  "appendix_ref_id": "REF_CH09_VIS_001",
  "source_mode": "external_image | ai_generated_image | user_upload",
  "ingestion_source": "ext | usr | ai | eng",
  "ingestion_status": "pending | ingested | cleared | rejected",
  "provenance_complete": false,
  "ingested_path": "publication/assets/ingested/ch09/ext/CH09_EP_001_ext_001_v001.jpg",
  "cleared_path": "publication/assets/cleared/ch09/ASSET_CH09_EP_001_v001.jpg",
  "provenance_path": "publication/assets/cleared/ch09/CH09_EP_001_provenance.json",
  "rights_status": "cleared | permission_required | public_domain | ai_generated_ok",
  "provenance": {
    "ext": {
      "url": "",
      "site_name": "",
      "retrieved_at": "",
      "rights_note": "",
      "clearance_status": "cleared | permission_required | rejected",
      "clearance_evidence": ""
    },
    "usr": {
      "original_filename": "",
      "upload_session": "",
      "user_rights_declaration": "owned | licensed | public_domain",
      "usage_note": ""
    },
    "ai": {
      "model": "",
      "prompt_summary": "",
      "prompt_full": "",
      "generation_session": "",
      "revision": 1,
      "likeness_review": "pass | needs_review",
      "trademark_review": "pass | needs_review",
      "usage_note": ""
    }
  }
}
```

소스별 필수 필드:

| 소스 | 필수 필드 |
|---|---|
| `ext` | url, site_name, retrieved_at, clearance_status |
| `usr` | original_filename, user_rights_declaration |
| `ai` | model, prompt_summary, revision, likeness_review |

---

## 5. 앵커 블록 정의 (이미지 앵커)

### 5.1 표준 문법

```md
<!-- ANCHOR_START id="CH09_EP_001" type="EP"
     placement="after_section:Context"
     asset_mode="external_image"
     ingestion_source="ext"
     priority="high"
     reference_ids="REF_CH09_VIS_001"
     appendix_ref="REF_CH09_VIS_001"
     caption="청령포 실경: 단종이 유배된 강가 섬의 현재 풍경"
     provenance_ref="PROV_CH09_VIS_001" -->
[ANCHOR_SLOT:CH09_EP_001]
<!-- ANCHOR_END id="CH09_EP_001" -->
```

### 5.2 신규 속성

기존 `ANCHOR_SPEC.md` 속성에 추가되는 이미지 전용 속성:

| 속성 | 값 | 설명 |
|---|---|---|
| `ingestion_source` | `ext \| usr \| ai \| eng` | 이미지 소스 타입 |
| `provenance_ref` | `PROV_{chapter}_{seq}` | provenance JSON 포인터 |

### 5.3 asset_mode 매핑

| asset_mode | ingestion_source | 처리 주체 |
|---|---|---|
| `external_image` | `ext` | S6B (수동 수집 또는 검색) |
| `external_image` | `usr` | S6B (사용자 업로드) |
| `ai_generated_image` | `ai` | S6B (AI 모델 호출) |
| `table`, `flowchart`, 기타 구조화 | `eng` | S7 엔진 자동 렌더 |

---

## 6. 그림 주석(Caption) 원칙

1. **한국어 우선**: 모든 캡션은 한국어로 작성한다.
2. **독자 맥락 중심**: 이미지가 본문 흐름과 어떻게 연결되는지 1-2문장으로 서술한다.
3. **운영 메타 미노출**: `anchor_id`, `appendix_ref`, `provenance_ref` 등 운영 정보는 캡션에 포함하지 않는다.
4. **출처 표기 규칙**:

| 소스 | 캡션 suffix 규칙 |
|---|---|
| `ext` | `(출처: {site_name})` |
| `usr` | 없음 (사용자 저작물은 별도 표기 불필요) |
| `ai` | `(AI 생성 이미지, {model})` |
| `eng` | 없음 (엔진 생성은 독자용 출처 표기 불필요) |

5. **길이 제한**: 캡션은 최대 50자 (한국어 기준). 초과 시 sub-caption으로 분리.
6. **저작권 예민 대상 제외**: 사람 실명, 영화 제목 저작권 대상 문구는 캡션에 직접 인용 금지.

캡션 예시:
```
청령포 실경: 단종이 유배된 강가 섬의 현재 전경 (출처: 한국관광공사)
AI가 재현한 조선 왕실 생활 장면 (AI 생성 이미지, gemini-3-flash-preview)
```

---

## 7. Gate 정의

Gate ID: `image_asset_ingestion_pass`

통과 조건:
1. 해당 챕터의 모든 `ext` / `usr` / `ai` 앵커에 대응하는 cleared 자산 파일 존재
2. 각 자산의 `provenance_complete: true`
3. `rights_status`가 `cleared | public_domain | ai_generated_ok` 중 하나
4. 캡션이 작성 원칙을 준수 (한국어, 50자 이하, 운영 메타 미포함)
5. `image_manifest.json`의 해당 항목 `ingestion_status: cleared`

실패 시: S6B 재실행 (특정 anchor_id만 재처리 가능)

---

## 8. 처리 흐름 요약

```
S6A (Handoff 생성)
  └── asset_collection_manifest.json 확인
      ├── source_mode == external_image
      │   └── S6B: ext 또는 usr 수집 → ingested/ → 권리 검토 → cleared/
      ├── source_mode == ai_generated_image
      │   └── S6B: AI 모델 호출 → ingested/ai/ → provenance 기록 → cleared/
      └── source_mode == structured (table/chart/etc.)
          └── S7 엔진 자동 처리 (S6B 생략)

S6B 완료 → cleared/ 자산 + provenance JSON 확정
  └── S7: visual_plan.json + cleared/ 자산 → draft4 빌드
      └── S9: 최종 출판 빌드
```
