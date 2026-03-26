# BookEngine — Claude Code 프로젝트 지침

## 프로젝트 개요
AI 기반 도서 자동 집필 플랫폼. 로컬 설치형 Tauri 데스크톱 앱.

- **제품명**: BookEngine
- **GitHub**: https://github.com/delion-dev/bookengine
- **랜딩**: https://delion-dev.github.io/bookengine/
- **스택**: Python FastAPI + Next.js 16 + Tauri 2.x + Tailwind CSS
- **현재 활성 책**: `books/with the King` (17챕터)

## 디렉토리 구조
```
/d/solar_book/                      ← 프로젝트 루트 (절대경로)
├── CLAUDE.md                       ← 이 파일
├── engine_core/                    ← Python 핵심 엔진 (기존 모듈 수정 금지)
│   ├── style_guide.py              ← [신규 허용] S10 스타일 가이드
│   ├── epub_packager.py            ← [신규 허용] S11 EPUB 패키저
│   ├── metadata_engine.py          ← [신규 허용] 메타데이터 엔진
│   └── keyword_generator.py        ← [신규 허용] SEO 키워드
├── engine_api/                     ← FastAPI 백엔드 (11개 라우터, 36+ 엔드포인트)
├── frontend/                       ← Next.js + Tauri 앱
│   ├── src/app/                    ← 페이지 라우트 (15개)
│   ├── src/lib/api.ts              ← API 클라이언트 (타입 포함)
│   ├── src/lib/store.ts            ← Zustand 전역 상태
│   ├── src/components/             ← 컴포넌트
│   └── src-tauri/                  ← Tauri 설정 + Rust (Python 서버 자동 기동)
├── books/                          ← 책 데이터 (운영 중, .gitignore 제외)
├── tools/                          ← CLI 도구
├── platform/                       ← 설계 문서 (수정 금지)
├── docs/                           ← 프로젝트 문서
├── design-system/                  ← BookEngine UI 디자인 시스템
├── landing/                        ← GitHub Pages 랜딩 사이트
└── .github/workflows/              ← CI/CD (deploy-landing, release)
```

## 핵심 원칙
1. `engine_core/` 기존 53개 모듈 — 임의 수정 금지 (신규 파일 추가는 허용)
2. `platform/` — 설계 문서, 수정 금지
3. 모든 스테이지 실행은 `engine.*` API를 통해서만
4. 에이전트 간 소통은 파일 계약 + shared memory
5. AppData 저장 경로: `%APPDATA%/BookEngine/` (Windows)

## 개발 환경 (절대경로 기준)
```bash
# FastAPI 서버 기동 (포트 8000)
cd /d/solar_book && python tools/core_engine_cli.py run-server

# Tauri 개발 앱
cd /d/solar_book/frontend && npm run tauri dev

# Tauri 릴리즈 빌드
cd /d/solar_book/frontend && npm run tauri build

# TypeScript 검증
cd /d/solar_book/frontend && npx tsc --noEmit

# 랜딩 배포 (GitHub Actions 자동)
cd /d/solar_book && git add landing/ && git commit -m "landing: ..." && git push origin main
```

## Windows 환경 주의사항
- npm native bindings 수동 설치 필요:
  `@tauri-apps/cli-win32-x64-msvc`, `lightningcss-win32-x64-msvc`, `@tailwindcss/oxide-win32-x64-msvc`
- node_modules 재설치 시 `package-lock.json` 삭제 후 `npm install`
- 포트 8000 충돌 (PowerShell): `netstat -ano | findstr ":8000"` → `taskkill /PID <PID> /F`
- 포트 8000 충돌 (Git Bash): `cmd.exe /c "netstat -ano | findstr :8000"`

## 스테이지 파이프라인
```
S-1(입력) → S0(설계) → S1(오케스트레이션) → S2(조사) → S3(가이드)
→ S4(초고) → S4A(앵커) → S5(검토) → S6(시각화) → S6A(자산수집)
→ S6B(이미지) → S7(렌더링) → S8(교정) → S8A(polish) → SQA(QA)
→ S9(출판) → S10(스타일가이드) → S11(EPUB최종)
```

## UI/UX 설계 원칙
- 스타일: Dark Mode + Glassmorphism (`#020203` 배경, `#5E6AD2` 강조)
- 컴포넌트: Tailwind CSS + Lucide React (이모지 사용 금지)
- 디자인 시스템: `design-system/MASTER.md` 단일 소스

## 제품 방향
- 배포: 로컬 설치형 Installer (.exe / .msi)
- 인증: 라이선스 키 방식 (로컬 전용, Trial: `BKENG-TRIAL-00000-00000-00000`)
- AI: 사용자 본인 API 키 입력 (BYOK — Gemini / OpenAI)
- 수익: Google AdSense + 프리미엄 라이선스 키
- 랜딩: GitHub Pages (BookEngine 소개 + 기술 도서 홍보)

## 활성 문서
- [체크포인트](docs/CHECKPOINT_20260319.md)
- [API 명세](platform/core_engine/API_SPEC.md)
- [디자인 시스템](design-system/MASTER.md)
- [메모리 인덱스](~/.claude/projects/d--solar-book/memory/MEMORY.md)
