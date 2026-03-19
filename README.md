# BookEngine — AI 기반 도서 자동 집필 플랫폼

> AI로 책을 씁니다. Google Gemini / OpenAI를 활용한 17단계 자동 집필 파이프라인.

[![License](https://img.shields.io/badge/license-proprietary-red)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)]()
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20Next.js%20%2B%20Tauri-blueviolet)]()

---

## 개요

BookEngine은 로컬 설치형 데스크톱 앱으로, AI를 활용해 기획안 하나로 챕터 초안부터 QA, EPUB 출판까지 자동화합니다.

- **BYOK**: 본인 Gemini / OpenAI API 키 사용 (외부 전송 없음)
- **로컬 전용**: 원고 데이터는 PC에만 저장
- **Google Books**: EPUB 3.x 자동 생성 + SEO 키워드 최적화

## 스택

| 레이어 | 기술 |
|---|---|
| 데스크톱 | Tauri 2.x (Rust + WebView2) |
| 프론트엔드 | Next.js 16 + Tailwind CSS v4 + shadcn/ui |
| 백엔드 | Python FastAPI (포트 8000) |
| AI | Google Gemini Flash / OpenAI GPT-4o |

## 파이프라인 (13 → 15 스테이지)

```
S-1 사전구성 → S0 초기화 → S1 기획 → S2 목차 → S3 개요 → S4 초안
→ S5 자료수집 → S6 이미지 → S6B 보정 → S7 편집 → S8 교정
→ S8A 심화교정 → S9 출판원고
→ S10 스타일가이드 선택 → S11 EPUB 패키징 (Google Books 출판)
```

## 빠른 시작

```bash
# 1. FastAPI 서버 기동
python tools/core_engine_cli.py run-server

# 2. 앱 개발 모드
cd frontend && npm run tauri dev

# 3. TypeScript 검증
cd frontend && npx tsc --noEmit
```

## 디렉토리 구조

```
bookengine/
├── engine_core/     # AI 파이프라인 엔진 (Python)
├── engine_api/      # FastAPI 백엔드
├── frontend/        # Next.js + Tauri 앱
├── landing/         # GitHub Pages 랜딩 사이트
├── design-system/   # UI 디자인 시스템
├── platform/        # 플랫폼 설계 문서
├── docs/            # 프로젝트 문서
└── tools/           # CLI 도구
```

## 랜딩 사이트

[https://delion-dev.github.io/bookengine/](https://delion-dev.github.io/bookengine/)

## 라이선스

Proprietary — All rights reserved.
상업적 사용 및 배포는 라이선스 키 구매 후 허용됩니다.
