# API-ization Inventory

## 목적

기존 저장소에서 재사용 가능한 로직을 추출하여:

- 전역 API로 고정할 것
- 책별 지역 API로 분리할 것
- Core Engine으로 승격할 후보

를 식별한다.

현재 평가는 `with_the_king`를 기준으로 한 새 집필 플랫폼 관점에서 수행했다.

---

## 분석 원칙

1. 도메인 내용은 지역화한다.
2. 절차와 검증 메커니즘은 전역 API화한다.
3. 상태 전이는 API를 통해서만 허용한다.
4. 스킬의 지시문도 코드와 동일하게 "호출 가능한 계약"으로 본다.

---

## A. 정책/헌법/운영 규칙 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [CLAUDE.md](/d:/solar_book/CLAUDE.md) | 전역 작업 규칙 | 태양광/레거시 구조 혼재 | `engine.constitution.*` | 전역 | 예 |
| [SOP_MASTER.md](/d:/solar_book/SOP_MASTER.md) | 단계별 SOP | `outline.md`, 태양광 스킬 구조에 결합 | `engine.stage.*`, `engine.contract.*` | 전역 | 예 |
| [SYSTEM_DESIGN.md](/d:/solar_book/SYSTEM_DESIGN.md) | MetaGPT형 상위 설계 | 구현과 문서가 불일치 | `engine.registry.*`, `engine.work_order.*` | 전역 | 예 |
| [books/NEW_BOOK_PROTOCOL.md](/d:/solar_book/books/NEW_BOOK_PROTOCOL.md) | 새 책 생성 절차 | 수동 절차 문서 수준 | `engine.bootstrap.*` | 전역 | 예 |

평가:

- 정책 문서는 모두 Core Engine 헌법과 API 스펙으로 재정의해야 한다.
- 책별 스타일은 헌법이 아니라 지역 API로 내려야 한다.

---

## B. 레지스트리/상태/오케스트레이션 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [WORKSPACE_REGISTRY.json](/d:/solar_book/WORKSPACE_REGISTRY.json) | 멀티북 레지스트리 | 레거시 루트와 책별 경로 혼재 | `engine.registry.*` | 전역 | 예 |
| [db/manuscripts_db.json](/d:/solar_book/db/manuscripts_db.json) | solar_pmo 상태 DB | 루트 전용 | `engine.book_state.*` | 지역 | 아니오 |
| `books/{book_id}/db/book_db.json` | 책별 상태 DB | 현재 구조와 일부만 연동 | `engine.book_state.*` | 지역 | 아니오 |
| [db/WORK_ORDER.json](/d:/solar_book/db/WORK_ORDER.json) | 작업 지시서 | 특정 책/챕터 하드코딩 | `engine.work_order.issue/get/ack` | 전역 | 예 |
| [db/PIPELINE_STATUS.md](/d:/solar_book/db/PIPELINE_STATUS.md) | 파이프라인 요약 | 사람이 읽는 레포트 위주 | `engine.pipeline.snapshot/render` | 전역 | 예 |
| [orchestrator SKILL.md](/d:/solar_book/.claude/skills/orchestrator/SKILL.md) | AG-OM 작업 지침 | 전역 설계는 좋지만 파일 경로가 고정 | `engine.work_order.*`, `engine.pipeline.*` | 전역 | 예 |

평가:

- 오케스트레이션은 가장 먼저 API로 고정할 가치가 있다.
- 상태 DB는 책별 지역 API로 통일하고, 전역에서는 책 메타만 봐야 한다.

---

## C. 책 생성/설계/집필 준비 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [architect SKILL.md](/d:/solar_book/.claude/skills/architect/SKILL.md) | BOOK_BLUEPRINT 생성 | 결과는 범용적이나 구현 부재 | `engine.blueprint.generate` | 전역 | 예 |
| [planner SKILL.md](/d:/solar_book/.claude/skills/planner/SKILL.md) | raw guide 생성 | `outline.md`, `db/manuscripts_db.json` 고정 | `engine.stage.plan_raw` | 전역 | 예 |
| [toc-architect SKILL.md](/d:/solar_book/.claude/skills/toc-architect/SKILL.md) | 목차 검증 | 태양광 분량 가정 포함 | `engine.outline.validate` | 전역 | 예 |
| `BOOK_CONFIG.json` 계열 | 책 설정 | 필드가 책마다 다를 수 있음 | `book.profile.*` | 지역 | 아니오 |
| `BOOK_BLUEPRINT.md` 계열 | 책 구조 설계 | 책별 | `book.blueprint.*` | 지역 | 아니오 |
| `STYLE_GUIDE.md` 계열 | 책별 스타일 | 책별 | `book.style.*` | 지역 | 아니오 |
| `QUALITY_CRITERIA.md` 계열 | 책별 품질 기준 | 책별 | `book.quality.*` | 지역 | 아니오 |

평가:

- "기획안 + 목차 초안"을 받아 새 책을 세팅하는 단계는 전역 `bootstrap + blueprint` API로 묶어야 한다.
- 스타일/품질/톤은 지역 API로 내려야 한다.

---

## D. 집필/검수/교정 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [writing-master SKILL.md](/d:/solar_book/.claude/skills/writing-master/SKILL.md) | 집필 규칙 | 태양광 독자/구조/목표 분량 고정 | `engine.writer.compose` + local policy | 전역+지역 분리 | 예 |
| [technical-writing SKILL.md](/d:/solar_book/.claude/skills/technical-writing/SKILL.md) | 기술 서술 규칙 | 일부 범용 가능 | `engine.writer.technical_policy` | 전역 | 예 |
| [reviewer SKILL.md](/d:/solar_book/.claude/skills/reviewer/SKILL.md) | 검수/현행화 | 태양광 수치/어조 고정 | `engine.review.run` + local research policy | 전역+지역 분리 | 예 |
| [copy-editor-master SKILL.md](/d:/solar_book/.claude/skills/copy-editor-master/SKILL.md) | 최종 교정/게이트 | 범용성이 높음 | `engine.copyedit.run`, `engine.gate.decide` | 전역 | 예 |
| [beautiful-prose SKILL.md](/d:/solar_book/.claude/skills/beautiful-prose/SKILL.md) | AI 흔적 제거 | 범용 가능 | `engine.style.rewrite` | 전역 | 예 |

평가:

- 집필/검수/교정은 "코어 로직 + 지역 정책"의 전형적인 분리 대상이다.
- 전역 API는 작업 흐름만 담당하고, 지역 API는 책 목소리와 독자를 공급해야 한다.

---

## E. 조사/출처/외부정보 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [web-search SKILL.md](/d:/solar_book/.claude/skills/web-search/SKILL.md) | 최신 정보 검색 | 호출 규칙 중심 | `engine.research.search` | 전역 | 예 |
| [deep-research SKILL.md](/d:/solar_book/.claude/skills/deep-research/SKILL.md) | 심층 조사 | 계획과 실행이 섞임 | `engine.research.plan`, `engine.research.collect` | 전역 | 예 |
| [content-research SKILL.md](/d:/solar_book/.claude/skills/content-research/SKILL.md) | 근거 정리 | 범용 가능 | `engine.research.citations` | 전역 | 예 |
| [knowledge-updater SKILL.md](/d:/solar_book/.claude/skills/knowledge-updater/SKILL.md) | KB 업데이트 | 지역 지식 자산과 결합 | `book.knowledge.update` | 지역 | 아니오 |

평가:

- `with_the_king`는 트렌드/뉴스 의존 책이므로 조사 API를 Core Engine에서 반드시 지원해야 한다.
- 출처 패키지는 아티팩트 계약의 일부가 되어야 한다.

---

## F. 시각화 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [visual-architect SKILL.md](/d:/solar_book/.claude/skills/visual-architect/SKILL.md) | 시각 앵커 설계 | `D:/solar_book/chapters/final` 고정 | `engine.visual.plan` | 전역 | 예 |
| [visual-builder SKILL.md](/d:/solar_book/.claude/skills/visual-builder/SKILL.md) | Mermaid/표 생성 | 파일명 규약 혼재 | `engine.visual.render` | 전역 | 예 |
| [scripts/integrate_visual.py](/d:/solar_book/scripts/integrate_visual.py) | 통합본 생성 | 파일 존재 가정, 파일명 불일치 | `engine.visual.integrate` | 전역 | 예 |
| [scripts/insert_anchors_ch01.py](/d:/solar_book/scripts/insert_anchors_ch01.py) | ch01 전용 앵커 삽입 | 챕터 전용 하드코딩 | 폐기 후 API 통합 | 전역 | 아니오 |

평가:

- 시각 파이프라인은 범용화 가치가 높지만 현재 구현은 레거시 의존이 심하다.
- `draft3 -> draft4` 계약으로 재정의해야 한다.

---

## G. 출판/배포 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [tools/epub_builder_mcp.py](/d:/solar_book/tools/epub_builder_mcp.py) | MCP 기반 EPUB 생성/상태 확인 | 루트 경로, 8개 챕터, 태양광 제목 고정 | `engine.publish.*` | 전역 | 예 |
| [scripts/build_epub.sh](/d:/solar_book/scripts/build_epub.sh) | EPUB 빌드 | 절대경로, cover 파일 가정, 챕터 고정 | `engine.publish.build_epub` | 전역 | 예 |
| [scripts/build_pdf.sh](/d:/solar_book/scripts/build_pdf.sh) | PDF 빌드 | 절대경로/태양광 제목 고정 | `engine.publish.build_pdf` | 전역 | 예 |
| [scripts/build_book.sh](/d:/solar_book/scripts/build_book.sh) | DOCX 합본 | 레거시 | `engine.publish.build_docx` | 전역 | 조건부 |
| [scripts/epub_metadata_check.py](/d:/solar_book/scripts/epub_metadata_check.py) | 메타데이터 검증 | 범용 가능 | `engine.publish.validate_metadata` | 전역 | 예 |
| [scripts/epub_google_play_check.py](/d:/solar_book/scripts/epub_google_play_check.py) | Google Play 호환성 | 범용 가능 | `engine.publish.validate_google_play` | 전역 | 예 |
| [epub-builder SKILL.md](/d:/solar_book/.claude/skills/epub-builder/SKILL.md) | 출판 규칙 | 태양광 메타데이터 예시 고정 | `engine.publish.policy` + local metadata | 전역+지역 분리 | 예 |

평가:

- 출판은 가장 명확한 Core Engine 후보다.
- Google Books/Google Play 검증은 전역 API여야 한다.

---

## H. 세션/도구/운영 계층

| 기존 소스 | 현재 역할 | 문제 | API화 대상 | 범위 | Core 승격 |
|---|---|---|---|---|---|
| [session-manager SKILL.md](/d:/solar_book/.claude/skills/session-manager/SKILL.md) | 세션 시작/종료 | 루트 기준 | `engine.session.open/close` | 전역 | 예 |
| [scripts/session_open.py](/d:/solar_book/scripts/session_open.py) | 세션 시작 리포트 | Unicode/누락파일/레거시 경로 | `engine.session.open` | 전역 | 예 |
| [scripts/session_close.py](/d:/solar_book/scripts/session_close.py) | 세션 종료/로그 | Unicode/레거시 경로 | `engine.session.close` | 전역 | 예 |
| [tools/setup_epub_mcp.py](/d:/solar_book/tools/setup_epub_mcp.py) | 도구 설치 | 보조 도구 | `engine.runtime.setup` | 전역 | 조건부 |
| [tools/test_imports.py](/d:/solar_book/tools/test_imports.py) | 환경 진단 | Unicode 출력 의존 | `engine.runtime.diagnose` | 전역 | 조건부 |

평가:

- 세션과 진단 도구는 운영 API로 흡수해야 한다.
- 콘솔 출력이 아니라 구조화된 JSON 응답을 표준으로 바꿔야 한다.

---

## I. 모델/검색/외부 연동 계층

현재 저장소에는 Google AI 모델 연동이 구현돼 있지 않다.
하지만 사용자 요구상 다음 전역 API가 반드시 필요하다.

| 신규 API 후보 | 역할 | 범위 | Core 승격 |
|---|---|---|---|
| `engine.model.generate_text` | 텍스트 생성 | 전역 | 예 |
| `engine.model.generate_structured` | JSON 스키마 기반 생성 | 전역 | 예 |
| `engine.model.grounded_research` | 웹/뉴스/SNS 조사 보강 | 전역 | 예 |
| `engine.model.summarize_sources` | 출처 요약 | 전역 | 예 |
| `engine.model.safety_check` | 민감도/정책 점검 | 전역 | 예 |
| `engine.model.route_provider` | Google AI 포함 공급자 선택 | 전역 | 예 |

Google AI 연동 방향:

- 직접 호출 금지
- 반드시 `engine.model.*` 게이트웨이 경유
- 책별 프롬프트 차이는 지역 API에서 주입

---

## 최종 API화 우선순위

1. `engine.constitution`, `engine.contract`, `engine.stage`
2. `engine.registry`, `engine.book_state`, `engine.work_order`
3. `engine.bootstrap`, `engine.blueprint`
4. `engine.research`, `engine.model`
5. `engine.writer`, `engine.review`, `engine.copyedit`
6. `engine.visual`
7. `engine.publish`
8. `engine.session`, `engine.runtime`

---

## 이번 단계 결론

기존 저장소에서 재사용 가능한 것은 "도메인 내용"이 아니라 다음 네 가지다.

1. MetaGPT형 역할 분리
2. 아티팩트 계약 기반 소통
3. 단계 상태와 게이트 모델
4. 출판 검증 파이프라인

따라서 새 시스템은 기존 로직을 파일 단위로 재사용하는 것이 아니라,
위 네 가지를 API로 추출하여 Core Engine으로 재구성하는 방식으로 진행해야 한다.
