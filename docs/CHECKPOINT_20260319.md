# BookEngine — 개발 체크포인트 (2026-03-19)

> 재기동 시 이 파일과 `memory/project_status.md`를 먼저 확인하세요.

---

## 오늘 완료한 작업

| # | 작업 | 결과 |
|---|---|---|
| 1 | TypeScript 빌드 검증 | 오류 0건 ✅ |
| 2 | AdSense 슬롯 Sidebar 연결 | `<AdSenseSlot type="sidebar" />` 실 주입 |
| 3 | tauri.conf.json CSP | AdSense + Google Fonts 도메인 추가 |
| 4 | AppShell 라이선스 가드 | 서버 재시도 8회(1.5초), 미인증 → /onboarding |
| 5 | P15: landing/docs/ 4개 | getting-started / pipeline / api-keys / google-books |
| 6 | P16: pricing.html | 무료/개인($49)/팀($149) 플랜 |
| 7 | GitHub 저장소 생성 | https://github.com/delion-dev/bookengine |
| 8 | GitHub Pages 배포 | https://delion-dev.github.io/bookengine/ ✅ |
| 9 | release.yml 수정 | 서명 없이 빌드 가능, NSIS+MSI만 빌드 |
| 10 | v0.1.0-beta 릴리즈 태그 | 빌드 진행 중 → Actions 탭 확인 필요 |

---

## 재기동 시 즉시 확인할 것

### 1. v0.1.0-beta 빌드 결과
```
https://github.com/delion-dev/bookengine/actions
```
- ✅ 성공 → Releases → Draft → "Publish release" 클릭
- ❌ 실패 → Actions 로그 확인 후 수정 필요

### 2. 빌드 실패 시 주요 의심 지점
- `npm ci` — package-lock.json 불일치
- Windows 네이티브 바이너리 — `@tauri-apps/cli-win32-x64-msvc` 설치 실패
- Rust 컴파일 오류 — `Cargo.toml` 의존성 문제

---

## 다음 작업 우선순위

### 즉시 (빌드 결과 확인 후)
1. **Releases Draft → Publish** (빌드 성공 시)
2. **download.html 링크 업데이트** — 실제 .exe URL로 교체

### 단기
3. **Google AdSense 계정 신청** (https://adsense.google.com)
4. **Tauri sidecar PyInstaller 번들링** — Python 없어도 실행 가능하게

### 중기
5. **landing/docs/ 내용 보강** — 스크린샷, GIF 추가
6. **v0.2.0 계획** — Mac/Linux, 배치 실행

---

## 중요 값 보관

| 항목 | 값 |
|---|---|
| GitHub 계정 | delion-dev |
| 저장소 | https://github.com/delion-dev/bookengine |
| 랜딩 URL | https://delion-dev.github.io/bookengine/ |
| Trial 라이선스 키 | `BKENG-TRIAL-00000-00000-00000` |
| 라이선스 Secret | `e744fc4d3ad59df9a857691b803cdbba57b1ef63e355c014147ece2feda4ecac` |
| GitHub Secret 이름 | `BOOKENGINE_LICENSE_SECRET` |
