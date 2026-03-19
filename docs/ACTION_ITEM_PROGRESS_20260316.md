# Action Item Progress

Date: 2026-03-16
Book: `with_the_king`

## 이번 라운드에서 반영한 내용

### 1. S4 초고 작성 원칙 강화

- 영화 장 초고는 "책 쓰는 방법"이 아니라 장면, 연기, 시선, 침묵, 실제 장소 감각을 직접 서술하도록 강화
- 메타성 금지 문구를 프롬프트와 fallback prose 모두에 반영
- section heading은 `도입 (Hook)`, `맥락 (Context)`, `통찰 (Insight)`, `실전 포인트 (Takeaway)` 규칙으로 통일

### 2. S7 시각화 주석 원칙 정리

- `appendix_ref`, `support_gaps`, `anchor_id`, `renderer_hint`를 reader-facing output에서 제거
- 위 정보는 HTML comment, `visual_bundle.json`, `reference_index.json`, `image_manifest.json`에 남기도록 정리
- 표, 요약 박스, 콜아웃, 링크 텍스트를 한국어 중심으로 정리

### 3. 오프라인 자산 수집 분리

- 실제 외부 이미지, 스틸컷, 유튜브, AI 렌더 수집은 별도 offline round로 분리
- 파일명 규칙: `ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext`
- 기본 저장 경로: `publication/assets/cleared/{chapter_id}/`
- 관련 문서: `docs/OFFLINE_ASSET_COLLECTION_PROTOCOL.md`

### 4. S8A 역할 재정의

- `S8A`는 기본 출판 경로가 아닌 optional editorial polish stage로 정리
- 기본 출판 입력은 `draft5`
- `draft6`은 명시적으로 완료된 챕터만 선택적으로 사용

## 실제 재빌드한 범위

- `S7` 전 챕터 재렌더
- `S8` 전 챕터 재검수
- `S9` 출판 재빌드

산출물:

- `publication/output/with_the_king.html`
- `publication/output/with_the_king.epub`
- `publication/output/with_the_king.pdf`
- `publication/output/publication_manifest.json`

## 아직 남은 핵심 과제

### A. 초고 본문 자체 재생성

이번 라운드에서는 `S4` 엔진 로직을 먼저 바로잡았고, 전 챕터 `draft1` 재생성은 아직 수행하지 않았다.

즉:

- 앞으로 생성될 초고는 개선된 규칙을 따른다.
- 하지만 현재 저장된 `draft1~draft5` 본문은 기존 생성분의 흔적이 일부 남아 있을 수 있다.

### B. 영화 본문 보강 재실행

다음 실작업은 `S4 -> S4A -> S5`를 중심으로 다시 돌리는 것이다.

우선순위:

1. `PART 1 [CINEMA]` 챕터군
2. 메타성 흔적이 컸던 챕터
3. 이후 `TRAVEL/TASTE` 챕터

### C. 오프라인 자산 수집 라운드

- 외부 이미지 7건
- AI 이미지 1건
- 부록 인덱스와 실제 자산 파일의 1:1 정합성 마감

## 현재 확인 상태

- 코드 컴파일: 통과
- 출판 재빌드: 완료
- HTML 기준 raw Mermaid residue: `0`
- HTML 기준 anchor slot residue: `0`
- HTML 기준 meta block residue: `0`
- placeholder 자산: `8`건 유지
- 최신 `WORK_ORDER.local.json` 기준 gate failure: `17`건
- 최신 `WORK_ORDER.local.json` 기준 runtime alert: `32`건
- 현재 gate failure는 `S5` review pass 미충족에 집중
- 현재 runtime alert는 `S4/S5`의 fallback-heavy 실행 이력에 집중

## 다음 실행 묶음 권고

1. `PART 1 [CINEMA]` 전 챕터 `S4 -> S4A -> S5` 재실행
2. 결과 육안 검수
3. 필요 시 `S6 -> S7 -> S8 -> S9` 재동기화
4. 별도 offline asset round 수행
