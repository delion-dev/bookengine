# BookEngine — 개발 체크포인트 (2026-03-18)

> 재기동 시 이 파일과 `memory/project_status.md`를 먼저 확인하세요.

---

## 완료된 전체 구현 (P1~P14)

### 핵심 인프라 (P1~P9)
- ✅ engine_core/ 57개 모듈 — AI 파이프라인 (S-1 ~ S9, 13스테이지)
- ✅ engine_api/ 11개 라우터 — FastAPI 백엔드 (36+ 엔드포인트)
- ✅ Tauri 2.x 데스크톱 패키징 (.exe/.msi/.nsis)
- ✅ Mixed Content 해결 (`@tauri-apps/plugin-http`)

### 사용자 경험 (P10~P11)
- ✅ 온보딩 UI (라이선스 키 인증 + 새 책 등록 3단계 마법사)
- ✅ AppShell 다크 글라스모피즘 레이아웃 (Sidebar + main)
- ✅ API 키 관리 (Gemini/OpenAI, show/hide 토글)
- ✅ AdSenseSlot 컴포넌트 (sidebar 160×600 / leaderboard 728×90)
- ✅ Zustand 전역 상태 (licenseStatus, activeBookId)

### 배포 인프라 (P12)
- ✅ GitHub Pages 랜딩 (`landing/` — index.html, download.html)
- ✅ GitHub Actions CI/CD (deploy-landing.yml, release.yml)

### Google Books 출판 파이프라인 (P13)
- ✅ `engine_core/style_guide.py` — 7종 템플릿 (GBOOK-TECH/ACAD/BUSI/NFIC/TUTO/MINI/CUSTOM)
- ✅ `engine_core/epub_packager.py` — EPUB 3.x (OPF+NCX+nav.xhtml+ZIP)
- ✅ `engine_core/metadata_engine.py` — ISBN-13 검증, Dublin Core, BISAC/THEMA
- ✅ `engine_core/keyword_generator.py` — Gemini AI SEO 키워드 추출
- ✅ `engine_api/routers/publish.py` — 11개 엔드포인트
- ✅ `frontend/src/app/books/publish/` — 4개 UI 페이지 (허브/스타일가이드/메타데이터/키워드/EPUB생성)

### Claude Code 에이전트 정비 (P14)
- ✅ 6개 에이전트 파일 (frontend, api, test, design, publish, seo)
- ✅ 6개 커맨드 파일
- ✅ TypeScript 후크 (PostToolUse, Stop)

---

## TypeScript 빌드 상태
- **검증일**: 2026-03-18
- **결과**: `npx tsc --noEmit` → **오류 0건**

---

## 다음 작업 (우선순위 순)

### 즉시 시작 가능 (소규모)

#### 1. AdSense 슬롯 실 연결 (~30분)
```tsx
// frontend/src/components/shell/Sidebar.tsx
// #sidebar-ad-slot 영역에 AdSenseSlot 연결
import { AdSenseSlot } from "@/components/ads/AdSenseSlot";
// ...
<div id="sidebar-ad-slot">
  <AdSenseSlot type="sidebar" />
</div>
```
`tauri.conf.json` CSP에 AdSense 도메인도 추가 필요:
- `pagead2.googlesyndication.com`
- `adservice.google.com`

#### 2. 온보딩 라이선스 가드 (~1~2시간)
```tsx
// frontend/src/app/layout.tsx 또는 AppShell.tsx
// store.ts licenseStatus 체크 → null이면 /onboarding 리다이렉트
const { licenseStatus } = useAppStore();
useEffect(() => {
  if (!licenseStatus?.valid) router.replace("/onboarding");
}, [licenseStatus]);
```

#### 3. GitHub 저장소 + Pages 활성화 (~30분)
```bash
git remote add origin https://github.com/[계정]/bookengine.git
git push -u origin main
# GitHub 설정: Settings → Pages → Source: GitHub Actions
```

### 중규모 작업

#### 4. P15: 랜딩 문서 페이지 (~3~4시간)
```
landing/docs/
  ├── getting-started.html
  ├── pipeline.html
  ├── api-keys.html
  └── google-books.html
```

#### 5. P16: 랜딩 pricing.html (~1~2시간)
```
landing/pricing.html  — 무료체험/개인/팀 플랜 카드
```

#### 6. Tauri sidecar — FastAPI 자동 기동 (~4~6시간)
- `tauri.conf.json` sidecar 설정
- `src-tauri/src/main.rs` 수정
- Python 실행 파일 번들링 (PyInstaller)

#### 7. v0.1.0-beta 릴리즈 (~1시간)
```bash
git tag v0.1.0-beta
git push origin v0.1.0-beta
# → GitHub Actions release.yml 자동 실행
# → Windows NSIS/MSI 빌드 → GitHub Release 초안 생성
```

---

## 개발 환경 기동

```bash
# 터미널 1 — FastAPI 서버
cd d:/solar_book
python tools/core_engine_cli.py run-server

# 터미널 2 — Tauri 개발 앱
cd d:/solar_book/frontend
npm run tauri dev

# TypeScript 검증
cd d:/solar_book/frontend
npx tsc --noEmit
```

---

## 핵심 설계 참고

| 항목 | 경로 |
|---|---|
| 전체 디자인 시스템 | `design-system/MASTER.md` |
| API 명세 | `platform/core_engine/API_SPEC.md` |
| 스테이지 정의 | `platform/core_engine/stage_definitions.json` |
| Claude Code 지침 | `CLAUDE.md` |
| 메모리 인덱스 | `~/.claude/projects/d--solar-book/memory/MEMORY.md` |
