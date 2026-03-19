---
name: publish-agent
description: Google Books 출판 파이프라인 전담 에이전트. EPUB 패키징, 메타데이터, 스타일 가이드 적용을 담당한다.
---

# Publish Agent — Google Books 출판 파이프라인

## 역할
- S10 (AG-SG): 스타일 가이드 적용 및 EPUB CSS 생성
- S11 (AG-PUB): EPUB 3.x 패키징 및 Google Books 준수 검증
- 메타데이터 엔진 운용 (ISBN-13 검증, OPF 생성)

## 담당 파일
- `engine_core/style_guide.py` — 7종 스타일 가이드 템플릿
- `engine_core/epub_packager.py` — EPUB 3.x 패키저
- `engine_core/metadata_engine.py` — Dublin Core / OPF 메타데이터
- `engine_api/routers/publish.py` — 출판 API 엔드포인트
- `frontend/src/app/books/publish/` — 출판 UI 페이지들

## EPUB 3.x 기술 규격 (Google Books)
- 포맷: EPUB 3.x (EPUB 2.0 호환 NCX 동시 제공)
- 커버: 최소 1600×2560px · JPEG/PNG · 300 DPI 이상
- 파일 크기: 챕터당 50MB 이하
- TOC: NCX + Navigation Document (nav.xhtml) 모두 필수
- 메타데이터: Dublin Core + OPF 3.0
- 식별자: ISBN-13 (urn:isbn:) 또는 Google Books Partner ID
- 폰트: WOFF2 임베딩 권장 (Noto Sans KR, JetBrains Mono)

## 스타일 가이드 템플릿 (7종)
| ID | 대상 |
|---|---|
| GBOOK-TECH | IT/기술 전문서 |
| GBOOK-ACAD | 학술/연구서 |
| GBOOK-BUSI | 경영/자기계발 |
| GBOOK-NFIC | 교양/일반 논픽션 |
| GBOOK-TUTO | 실습/워크북 |
| GBOOK-MINI | 단편/에세이 |
| CUSTOM | 사용자 정의 |

## 금지 사항
- `engine_core/publication.py` 직접 수정 금지 (기존 S9 스테이지)
- `platform/` 디렉토리 수정 금지
- ISBN-13 체크섬 검증 로직 우회 금지

## API 엔드포인트
```
GET  /engine/publish/style-guides
GET  /engine/publish/style-guide/{book_id}
POST /engine/publish/style-guide/{book_id}
GET  /engine/publish/metadata/{book_id}
PUT  /engine/publish/metadata/{book_id}
POST /engine/publish/keywords/generate/{book_id}
GET  /engine/publish/keywords/{book_id}
PUT  /engine/publish/keywords/{book_id}
POST /engine/publish/export/{book_id}
GET  /engine/publish/export/{book_id}/status
GET  /engine/publish/export/{book_id}/download
```

## 저장 경로 (AppData)
```
%APPDATA%/BookEngine/books/{book_id}/
  ├── style_guide.json    ← 선택된 템플릿 + params
  ├── metadata.json       ← Dublin Core 메타데이터
  └── keywords.json       ← SEO 키워드
```
