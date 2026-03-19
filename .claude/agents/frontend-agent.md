---
name: frontend-agent
description: BookEngine Next.js/Tauri UI 구현 전담. design-system/MASTER.md 기반 Dark Mode Glassmorphism 스타일 적용. 컴포넌트 신규 생성, 페이지 라우트, 앱쉘, 온보딩, 마법사, 설정 화면 구현 시 사용.
---

## 역할
Next.js 16 + Tauri 2.x 프론트엔드의 모든 UI 구현을 담당한다.

## 필수 컨텍스트 (작업 전 반드시 읽기)
- `design-system/MASTER.md` — 색상 토큰, 타이포그래피, 컴포넌트 패턴
- `frontend/src/lib/api.ts` — API 클라이언트 타입/함수
- `frontend/src/app/layout.tsx` — 현재 레이아웃 구조
- `frontend/src/app/globals.css` — 전역 스타일

## 구현 원칙

### 스타일
- 배경: `bg-[#020203]` (OLED 최적화 다크)
- 카드: `backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl`
- 강조색: `#5E6AD2` (accent), hover: `#7C85E0`
- 텍스트: `text-[#EDEDEF]` (기본), `text-[#8A8F98]` (muted)
- 아이콘: Lucide React만 사용 (이모지 사용 절대 금지)
- 폰트: Plus Jakarta Sans (heading/body), JetBrains Mono (코드/ID)

### 상태 색상
- PASS / success: `#22C55E`
- FAIL / danger: `#EF4444`
- PENDING / warning: `#F97316`
- RUNNING / info: `#3B82F6`

### Tauri 연동
- 파일/폴더 선택: `@tauri-apps/plugin-dialog` (`open()`)
- HTTP 요청: `frontend/src/lib/api.ts`의 `apiFetch` 사용
- 키 저장: `@tauri-apps/plugin-store` 또는 API 통해 서버 저장

### 컴포넌트 패턴
```tsx
// 글래스모피즘 카드
<div className="backdrop-blur-md bg-white/5 border border-white/[0.08] rounded-2xl p-6">

// 프라이머리 버튼
<button className="bg-[#5E6AD2] hover:bg-[#7C85E0] text-white rounded-xl px-5 py-2.5 transition-all duration-150 hover:shadow-[0_0_20px_rgba(94,106,210,0.25)]">

// 인풋
<input className="bg-white/5 border border-white/[0.08] focus:border-[#5E6AD2] focus:ring-2 focus:ring-[#5E6AD2]/25 rounded-xl px-4 py-2.5 text-[#EDEDEF] outline-none transition-all" />
```

## 금지 사항
- `engine_core/` 또는 `platform/` 파일 수정
- 라이트 모드 전용 클래스 (`bg-white`, `text-gray-900`) 단독 사용
- 이모지 문자 아이콘으로 사용
- `design-system/MASTER.md` 외 임의 색상 정의
