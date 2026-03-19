# BookEngine Design System — MASTER

> Source of Truth. 모든 페이지는 이 파일을 기반으로 구현한다.
> 페이지별 오버라이드: `design-system/pages/<page>.md`

---

## 제품 정보
- **제품명**: BookEngine
- **유형**: AI 도서 자동 집필 플랫폼 (Productivity / Developer Tool)
- **플랫폼**: 로컬 설치형 Tauri 데스크톱 앱 (Windows)
- **언어**: 한국어 UI
- **스택**: Next.js 16 + Tailwind CSS + shadcn/ui + Tauri 2.x

---

## 스타일 시스템

### 기본 스타일
- **Primary**: Modern Dark + Glassmorphism
- **테마**: Dark Mode 전용 (OLED 최적화)
- **분위기**: 전문적, 차분, 고급스러운 생산성 도구

### 색상 팔레트 (CSS Variables)
```css
:root {
  /* Background Layers */
  --bg-deep:     #020203;
  --bg-base:     #050506;
  --bg-elevated: #0a0a0c;
  --bg-card:     #0E1223;
  --bg-muted:    #1A1E2F;

  /* Surface (Glassmorphism) */
  --surface:           rgba(255, 255, 255, 0.05);
  --surface-hover:     rgba(255, 255, 255, 0.08);
  --surface-active:    rgba(255, 255, 255, 0.12);
  --border:            rgba(255, 255, 255, 0.08);
  --border-subtle:     rgba(255, 255, 255, 0.05);

  /* Text */
  --foreground:        #EDEDEF;
  --foreground-muted:  #8A8F98;
  --foreground-subtle: #4B5563;

  /* Accent (Blue — Primary Action) */
  --accent:            #5E6AD2;
  --accent-hover:      #7C85E0;
  --accent-glow:       rgba(94, 106, 210, 0.25);

  /* Status Colors */
  --success:     #22C55E;
  --warning:     #F97316;
  --danger:      #EF4444;
  --info:        #3B82F6;

  /* Stage 상태 색상 */
  --stage-pass:    #22C55E;
  --stage-fail:    #EF4444;
  --stage-pending: #F97316;
  --stage-running: #3B82F6;
  --stage-skip:    #4B5563;

  /* Radius */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  /* Blur */
  --blur-sm:  blur(8px);
  --blur-md:  blur(16px);
  --blur-lg:  blur(24px);

  /* Easing */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in:  cubic-bezier(0.7, 0, 0.84, 0);

  /* Z-index */
  --z-base:    0;
  --z-card:    10;
  --z-overlay: 40;
  --z-modal:   100;
  --z-toast:   1000;
}
```

---

## 타이포그래피

### 폰트
- **Heading**: Plus Jakarta Sans (600–700)
- **Body**: Plus Jakarta Sans (400–500)
- **Mono**: JetBrains Mono (코드, ID, 해시값)

### 스케일
| 역할 | 크기 | Weight | Line-height |
|------|------|--------|-------------|
| Display | 32px | 700 | 1.2 |
| H1 | 24px | 700 | 1.3 |
| H2 | 20px | 600 | 1.35 |
| H3 | 16px | 600 | 1.4 |
| Body | 14px | 400 | 1.6 |
| Small | 12px | 400 | 1.5 |
| Mono | 13px | 400 | 1.5 |

---

## 컴포넌트 패턴

### Glassmorphism Card
```css
background: rgba(255, 255, 255, 0.05);
backdrop-filter: blur(16px);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: var(--radius-lg);
```

### Primary Button
```css
background: var(--accent);
color: #fff;
border-radius: var(--radius-md);
padding: 10px 20px;
transition: all 150ms var(--ease-out);
/* hover */ background: var(--accent-hover);
/* glow  */ box-shadow: 0 0 20px var(--accent-glow);
```

### Input Field
```css
background: rgba(255, 255, 255, 0.05);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: var(--radius-md);
color: var(--foreground);
/* focus */ border-color: var(--accent);
           box-shadow: 0 0 0 3px var(--accent-glow);
```

---

## 레이아웃

### 앱 쉘 구조
```
┌─────────────────────────────────┐
│  Sidebar (240px)  │  Main Area  │
│  ─────────────   │  ───────── │
│  Logo             │  Header     │
│  Nav Items        │  Content    │
│  ─────────────   │             │
│  AdSense (하단)   │  AdSense    │
└─────────────────────────────────┘
```

### 사이드바 네비게이션
```
BookEngine [로고]
──────────────────
📚 내 책 목록
+ 새 책 등록
──────────────────
[선택된 책]
  📊 대시보드
  ⚡ 파이프라인
  🔍 QA 리포트
  📋 Work Order
──────────────────
⚙️  설정
──────────────────
[광고 영역 160×600]
```

### 반응형 브레이크포인트
| 이름 | 범위 | 레이아웃 |
|------|------|---------|
| desktop | ≥1280px | Sidebar + Content |
| laptop | 1024–1279px | Sidebar(접힘) + Content |

---

## 화면별 설계

### 1. 온보딩 / 라이선스 키 인증
- 전체 화면 배경 (glassmorphism 중앙 카드)
- BookEngine 로고 + 설명
- 라이선스 키 입력 폼
- "무료 체험 시작" CTA

### 2. 책 목록 대시보드
- 카드 그리드 (책별)
- 각 카드: 제목, 챕터 수, 진행률 바, 마지막 세션
- "+ 새 책 등록" 버튼 (상단 우측)
- AdSense 배너 (우측 사이드 또는 하단)

### 3. 새 책 등록 마법사 (3단계)
- Step 1: 책 기본 정보 (제목, book_id)
- Step 2: 폴더 선택 + 기획안 파일 선택 (Tauri 파일 다이얼로그)
- Step 3: AI API 키 입력 (Gemini / OpenAI)
- 진행 표시바 + 각 단계별 유효성 검사

### 4. 스테이지 파이프라인
- 챕터 × 스테이지 매트릭스 그리드
- 셀 색상: PASS(녹) / FAIL(적) / PENDING(주황) / RUNNING(파랑)
- 셀 클릭 → 상세 슬라이드 패널
- 스테이지 실행 / 중지 / 재시도 버튼

### 5. QA 리포트
- 체크 항목 테이블 (PASS/FAIL 배지)
- 재실행 버튼
- 실패 항목 상세 펼침

### 6. Work Order
- 작업 목록 테이블
- 상태 필터 탭

### 7. 설정
- AI API 키 관리 (Gemini, OpenAI)
- 라이선스 정보
- 앱 버전

---

## 광고 (Google AdSense)

### 배치 원칙
- 콘텐츠 방해 최소화
- 사이드바 하단: 160×600 (스카이스크레이퍼)
- 콘텐츠 하단: 728×90 (리더보드) — 페이지 스크롤 끝
- 글래스모피즘 컨테이너로 자연스럽게 통합

---

## 애니메이션

| 종류 | Duration | Easing |
|------|----------|--------|
| 마이크로 인터랙션 | 150ms | ease-out |
| 패널 슬라이드 | 250ms | cubic-bezier(0.16,1,0.3,1) |
| 모달 등장 | 200ms | ease-out |
| 페이지 전환 | 300ms | ease-in-out |

---

## 아이콘
- **라이브러리**: Lucide React
- **크기**: 16px (소), 20px (기본), 24px (대)
- **이모지 사용 금지**

---

## 접근성 체크리스트
- [ ] 텍스트 대비 4.5:1 이상
- [ ] 포커스 링 visible (2px accent color)
- [ ] 키보드 탭 순서 논리적
- [ ] aria-label 모든 아이콘 버튼에 적용
- [ ] 에러 메시지 필드 근처 표시
- [ ] 로딩 상태 150ms 후 표시
