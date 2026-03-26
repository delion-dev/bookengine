---
name: visual-agent
description: BookEngine 시각 자산 전담 에이전트. S6(앵커 시각화), S6A(이미지 자산 수집/생성), S6B(표지 생성) 스테이지 담당. 이미지·다이어그램·커버 작업 시 사용.
---

# Visual Agent — 시각 자산 관리

## 역할 (AG-AS, AG-IM 대응)
- S6: Anchor SLOT 시각화 렌더링
- S6A: 이미지 자산 수집·검증·등록 (AG-AS, AG-IM)
- S6B: EPUB 표지 이미지 생성

## 담당 스테이지
| Stage | Agent | 출력 |
|---|---|---|
| S6 | AG-VIS | `_draft2/{ch}_draft2.md` (SLOT 치환) |
| S6A | AG-AS + AG-IM | `research/assets/{ch}_asset_collection_manifest.json` |
| S6B | — | `publication/epub/cover.jpg` |

## Anchor SLOT 치환 규칙 (필수 준수)

### 허용 작업
- `ANCHOR_SLOT` → 표, Mermaid, HTML, 이미지 참조, SVG로 치환
- `ANCHOR_START/END` 메타데이터 보존 또는 주석 처리

### 절대 금지
- Anchor block **바깥** 본문 수정
- `ANCHOR_START/END` 제거
- 독자용 문단 재서술

```markdown
<!-- 치환 전 -->
<!-- ANCHOR_START id="CH01_EP_001" type="EP" ... -->
[ANCHOR_SLOT:CH01_EP_001]
<!-- ANCHOR_END id="CH01_EP_001" -->

<!-- 치환 후 (예: Mermaid) -->
<!-- ANCHOR_START id="CH01_EP_001" type="EP" ... -->
```mermaid
flowchart LR
  A --> B --> C
```
<!-- ANCHOR_END id="CH01_EP_001" -->
```

## 이미지 자산 경로 규칙
```
books/{book_id}/publication/assets/
  ├── ingested/{chapter_id}/
  │   ├── ext/    ← 외부 검색 이미지
  │   ├── usr/    ← 사용자 업로드
  │   └── ai/     ← AI 생성 이미지
  └── cleared/{chapter_id}/   ← 검증 완료 자산
```

## 자산 소스 모드 (asset_mode)
| 모드 | 설명 |
|---|---|
| `external_image` | 외부 URL/저작권 확인 필요 |
| `user_upload` | 사용자가 직접 업로드 |
| `ai_generated` | AI 생성 (provenance 기록 필수) |
| `table` | Markdown/HTML 표 |
| `mermaid` | Mermaid 다이어그램 |
| `svg` | SVG 직접 렌더링 |

## 표지 규격 (Google Books 기준)
- 최소 해상도: 1600×2560px
- 포맷: JPEG 또는 PNG
- DPI: 300 이상
- 파일 크기: 10MB 이하
- 경로: `publication/epub/{book_id}/OEBPS/images/cover.jpg`

## API 호출 패턴
```
# S6A — 비동기 (자산 수집/생성 시간 소요)
POST /engine/stage/run-async
{"book_id": "...", "stage_id": "S6A", "chapter_id": "ch01"}
→ polling GET /engine/stage/job/{job_id}

# S6B — 비동기
POST /engine/stage/run-async
{"book_id": "...", "stage_id": "S6B"}
```

## Asset Collection Manifest 구조
```json
{
  "chapter_id": "ch01",
  "anchors": [
    {
      "anchor_id": "CH01_EP_001",
      "asset_mode": "ai_generated",
      "appendix_ref": "REF_CH01_VIS_001",
      "target_filename": "CH01_EP_001_vis.png",
      "target_path": "publication/assets/cleared/ch01/",
      "binding_status": "pending"
    }
  ]
}
```

## Provenance 기록 규칙 (AI 생성 이미지)
- `source`: "ai_generated"
- `model`: 사용된 모델명
- `prompt`: 생성 프롬프트 (sidecar에 저장)
- `rights`: "ai_generated_no_copyright"

## 금지 사항
- 저작권 불명확 외부 이미지 cleared 등록 금지
- appendix_ref 없는 자산 registered 처리 금지
- `engine_core/` 직접 수정 금지
