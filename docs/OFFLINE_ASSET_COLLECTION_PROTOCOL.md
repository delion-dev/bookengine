# Offline Asset Collection Protocol

Date: 2026-03-16
Scope: visual placeholders, film stills, external photos, YouTube links, AI renders

## 목적

이 문서는 파이프라인 내부에서 예약만 해 두고, 실제 자산 수집은 별도 오프라인 라운드에서 처리해야 하는 시각 자료의 운영 규칙을 정의한다.

핵심 원칙:

- 파이프라인은 `appendix_ref`와 자산 수요를 예약한다.
- 실제 외부 이미지/스틸컷/유튜브/AI 렌더 수집은 offline round에서 수행한다.
- 수집 결과는 `reference_index.json`, `image_manifest.json`, `REFERENCE_INDEX.md`와 1:1로 맞물려야 한다.

## 대상 자산

- `EP`: 외부 사진, 영화 스틸컷, 장소 비교 이미지
- `AI`: 최종 AI 생성 이미지
- `VE`: 유튜브 클립, 영상 링크, QR 연결 자산
- `BT/PF/TL/DS/RM`: 구조 시각화에 쓰이는 보조 이미지가 필요할 경우의 후속 교체 자산

## 파일명 규칙

기본 파일명:

```text
ASSET_{CHAPTER}_{ANCHORTYPE}_{SEQ}_v001.ext
```

예시:

- `ASSET_CH01_EP_001_v001.jpg`
- `ASSET_CH04_VE_001_v001.txt`
- `ASSET_CH09_AI_001_v001.png`

## 저장 경로 규칙

기본 경로:

```text
books/{display_name}/publication/assets/cleared/{chapter_id}/
```

예시:

```text
books/with the King/publication/assets/cleared/ch01/ASSET_CH01_EP_001_v001.jpg
```

## 인덱스 연동 규칙

각 자산은 아래 3개를 동시에 맞춰야 한다.

1. `appendix_ref`
2. `image_manifest`의 `image_id`
3. 실제 수집 파일명

예시:

- `REF_CH01_VIS_001`
- `IMG_CH01_001`
- `ASSET_CH01_EP_001_v001.jpg`

## 필수 기록 항목

### 외부 이미지 / 스틸컷

- 출처명
- 원본 URL 또는 저장 위치
- 접근일
- 권리 검토 메모
- 사용 범위
- 캡션 초안

### AI 생성 이미지

- 모델명
- 프롬프트 요약
- 생성일
- 리비전
- 생성 주체
- 사용 메모

### 유튜브 / 영상 링크

- 채널명
- 영상 제목
- URL
- 접근일
- 인용/링크 사용 메모
- QR 생성 여부

## 독자 노출 원칙

- `appendix_ref`, `support_gaps`, `renderer_hint`, `anchor_id`는 독자용 본문에 직접 노출하지 않는다.
- 위 정보는 `REFERENCE_INDEX.md`, `reference_index.json`, `image_manifest.json`, `visual_bundle.json`에서 관리한다.
- 출판 본문에는 한국어 caption과 실제 시각 카드만 남긴다.

## 역할 분리

- `S2`: 자산 수요와 reference slot 예약
- `S6`: 어떤 자산이 필요한지 설계
- `S7`: 대체 시안 또는 구조 시각화 삽입
- `Offline Round`: 실제 자산 수집, 권리/provenance 마감
- `S9` 재빌드: 확정 자산 반영 출판본 생성

## 완료 정의

오프라인 자산 수집 라운드가 완료되려면:

- 파일이 실제로 존재해야 한다.
- `reference_index.json`의 해당 `appendix_ref`가 `planned`에서 더 진전된 상태여야 한다.
- `image_manifest.json`에 파일명/경로/권리 상태가 기록돼야 한다.
- `REFERENCE_INDEX.md`에서 해당 항목을 사람이 읽을 수 있게 확인할 수 있어야 한다.
