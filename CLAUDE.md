# BookEngine — Claude Code 프로젝트 지침

## 프로젝트 개요
AI 기반 도서 자동 집필 플랫폼. 로컬 설치형 Tauri 데스크톱 앱.

- **제품명**: BookEngine
- **스택**: Python FastAPI + Next.js 16 + Tauri 2.x + Tailwind CSS
- **현재 활성 책**: `books/with the King` (17챕터)

## 디렉토리 구조
```
d:/solar_book/
├── CLAUDE.md               ← 이 파일
├── engine_core/            ← Python 핵심 엔진 (수정 금지 대상)
├── engine_api/             ← FastAPI 백엔드 (36개 엔드포인트)
├── frontend/               ← Next.js + Tauri 앱
│   ├── src/app/            ← 페이지 라우트
│   ├── src/lib/api.ts      ← API 클라이언트
│   └── src-tauri/          ← Tauri 설정 및 Rust 코드
├── books/                  ← 책 데이터 (운영 중)
├── tools/                  ← CLI 도구
├── platform/               ← 설계 문서 (수정 금지)
├── docs/                   ← 프로젝트 문서
└── design-system/          ← BookEngine UI 디자인 시스템
```

## 핵심 원칙
1. `engine_core/`, `platform/` 는 검증된 설계 문서 — 임의 수정 금지
2. 모든 스테이지 실행은 `engine.*` API를 통해서만
3. 에이전트 간 소통은 파일 계약 + shared memory

## 개발 환경
- **서버 기동**: `python tools/core_engine_cli.py run-server` (포트 8000)
- **앱 개발**: `cd frontend && npm run tauri dev`
- **앱 빌드**: `cd frontend && npm run tauri build`
- **결과물**: `frontend/src-tauri/target/release/bundle/`

## Windows 환경 주의사항
- npm native bindings 수동 설치 필요:
  `@tauri-apps/cli-win32-x64-msvc`, `lightningcss-win32-x64-msvc`, `@tailwindcss/oxide-win32-x64-msvc`
- node_modules 재설치 시 package-lock.json 삭제 후 `npm install`
- 포트 8000 충돌 시: `netstat -ano | findstr ":8000"` → `taskkill /PID <PID> /F`

## UI/UX 설계 원칙
- 스타일: Dark Mode + Glassmorphism
- 컴포넌트: shadcn/ui + Tailwind CSS
- 아이콘: Lucide React (이모지 사용 금지)
- 스크립트: `tools/ui-ux-pro-max/scripts/search.py` 활용
- 디자인 시스템: `design-system/MASTER.md` 참조

## 제품 방향
- 배포: 로컬 설치형 Installer (.exe / .msi)
- 인증: 라이선스 키 방식 (로컬 전용)
- AI: 사용자 본인 API 키 입력 (BYOK)
- 수익: Google AdSense + 프리미엄 라이선스 키
- 랜딩: GitHub Pages (BookEngine 소개 + 기술 도서 홍보)

## 활성 문서
- [프로젝트 리포트](docs/PROJECT_REPORT.md)
- [API 명세](platform/core_engine/API_SPEC.md)
- [디자인 시스템](design-system/MASTER.md)
