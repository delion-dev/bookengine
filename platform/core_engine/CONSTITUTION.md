# Core Engine Constitution

## 목적

이 문서는 새 책 집필 플랫폼의 Core Engine 헌법이다.
헌법에 포함된 원칙과 Core 파일은 임의 수정 대상이 아니다.
변경은 오직 버전 상승과 호환성 검증을 동반한 공식 마이그레이션으로만 허용한다.

---

## 제1조. Core Engine 우선

모든 에이전트는 직접 파일을 편집하기 전에 Core Engine API를 우선 호출해야 한다.

금지:

- 임의 경로 계산
- 직접 상태 전이 기록
- 임의 형식의 입출력 파일 생성

허용:

- 지역 아티팩트 작성
- 지역 스킬 호출
- Core Engine이 승인한 출력 저장

---

## 제2조. 산출물 계약 우선

에이전트 간 소통은 오직 아티팩트 계약으로만 수행한다.

허용되는 소통 형식:

- `artifact_ref`
- `stage_manifest`
- `review_report`
- `gate_decision`
- `publication_manifest`

금지:

- "앞 단계가 이런 의도였을 것이다" 같은 추정 기반 전달
- 계약에 없는 임의 텍스트 파일을 다음 단계 입력으로 사용하는 행위

---

## 제3조. 단일 책임 에이전트

각 에이전트는 정확히 한 단계 책임만 가진다.

- AG-AR: 구조 설계
- AG-OM: 오케스트레이션
- AG-00: 집필 가이드
- AG-01: 초고
- AG-02: 검수/현행화
- AG-03: 시각 설계
- AG-04: 시각 구현
- AG-05: 교정/게이트
- AG-06: 출판

한 세션에서 다중 역할 겸임은 원칙적으로 금지한다.

---

## 제4조. 전역 API와 지역 API 분리

전역 API는 절차와 메커니즘을 제공한다.
지역 API는 특정 책의 설정과 지식만 제공한다.

전역 API의 예:

- `engine.stage.run`
- `engine.contract.validate`
- `engine.publish.build_epub`

지역 API의 예:

- `book.style.get`
- `book.domain_knowledge.resolve`
- `book.metadata.get`

전역 API가 책 내용을 직접 품어서는 안 된다.

---

## 제5조. 모델 접근 게이트웨이

Google AI 모델을 포함한 모든 생성형 모델 접근은 반드시 Model Gateway API를 통해야 한다.

직접 금지:

- 임의 SDK 직접 호출
- 에이전트별 개별 프롬프트 하드코딩
- 공급자별 응답 포맷을 그대로 노출

허용:

- `engine.model.generate_text`
- `engine.model.generate_structured`
- `engine.model.grounded_research`

---

## 제6조. 상태 전이 보호

상태 변경은 Core Engine의 상태 API만 수행할 수 있다.

상태는 다음과 같이 제한한다.

- `not_started`
- `pending`
- `in_progress`
- `completed`
- `gate_failed`
- `blocked`

에이전트가 직접 `book_db.json`을 수정하는 구조는 최종적으로 제거한다.

---

## 제7조. Gate 우선 진행

모든 단계는 Gate 판정 후에만 다음 단계로 넘어간다.

Gate 판정 권한:

- 구조/품질 Gate: AG-05 + `engine.gate.decide`
- 출판 Gate: AG-06 + `engine.publish.validate_*`

불합격 산출물은 반드시 반환 대상과 수정 지시를 포함해야 한다.

---

## 제8조. Core Engine 불변 파일

다음 파일은 Core Engine 불변 파일이다.

- [CONSTITUTION.md](/d:/solar_book/platform/core_engine/CONSTITUTION.md)
- [API_SPEC.md](/d:/solar_book/platform/core_engine/API_SPEC.md)
- [api_catalog.yaml](/d:/solar_book/platform/core_engine/api_catalog.yaml)
- [stage_definitions.json](/d:/solar_book/platform/core_engine/stage_definitions.json)
- [immutable_manifest.json](/d:/solar_book/platform/core_engine/immutable_manifest.json)

향후 코드 구현 시 다음 경로도 불변 코어 대상이다.

- `platform/core_engine/runtime/`
- `platform/core_engine/contracts/`
- `platform/core_engine/gateway/`

---

## 제9조. 사용자 입력의 정식 경로

새 책 시스템의 공식 입력은 다음 두 축이다.

1. `proposal.md`
2. `toc_seed.md`

필요 시 선택 입력:

- `author_note.md`
- `market_positioning.md`
- `reference_sources/`

기획안과 목차가 들어오면 Core Engine은 책 뼈대를 생성할 수 있어야 한다.

---

## 제10조. 검증 대상

현재 Core Engine 검증 대상은 다음 하나다.

- display root: `D:/solar_book/books/with the King`
- internal id: `with_the_king`

이 검증이 통과하기 전에는 다른 책 폴더를 기준 모델로 삼지 않는다.
