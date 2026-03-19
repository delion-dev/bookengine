# Orchestration Specification

## 목적

이 문서는 MetaGPT 기반 통합 오케스트레이션 체계를 정의한다.

초점:

- AG-OM의 동작 방식
- shared memory 운영 방식
- work order와 gate 결과의 흐름
- 병렬 처리와 재작업 규칙

---

## 1. 오케스트레이션 계층

시스템은 4계층으로 동작한다.

### Layer 1. Control Plane

- Core Constitution
- Registry
- Stage Definitions
- Gate Definitions

### Layer 2. Scheduling Plane

- AG-OM
- Work Order Engine
- Priority Queue
- Blocked Queue

### Layer 3. Execution Plane

- AG-IN, AG-AR, AG-RS, AG-00~AG-06, AG-05A, AG-AS
- Stage Runtime API

### Layer 4. Memory Plane

- Global Shared Memory
- Book Shared Memory
- Chapter Shared Memory
- Run Shared Memory

---

## 2. AG-OM 핵심 메커니즘

AG-OM은 다음 순서로 작동한다.

1. Registry에서 책 조회
2. book state snapshot 집계
3. gate 결과와 blocked item 수집
4. 병목 stage 계산
5. work item 우선순위 계산
6. parallel-safe batch 생성
7. WORK_ORDER 발행
8. shared memory 갱신

---

## 3. 우선순위 계산

기본 점수 모델:

```text
priority_score =
  book_priority_weight
  + stage_urgency_weight
  + gate_failure_penalty
  + dependency_unblock_value
  + publication_proximity_weight
```

권장 해석:

- `book_priority_weight`: 현재 책 자체 우선순위
- `stage_urgency_weight`: 뒤 단계가 많이 대기 중이면 가중
- `gate_failure_penalty`: 실패를 오래 끌수록 우선순위 상승
- `dependency_unblock_value`: 막힌 다운스트림이 많으면 우선
- `publication_proximity_weight`: 출판 직전 단계면 가중

---

## 4. Shared Memory 운용

Shared Memory는 세션 간 기억 손실을 막는 공식 저장소다.

### Global Memory

- 엔진 버전
- registry snapshot
- 공통 정책

### Book Memory

- 책 핵심 메시지
- 독자 페르소나
- 파트/챕터 의존 관계
- 주요 미해결 쟁점

### Chapter Memory

- 챕터 요약
- 작성된 핵심 주장
- 출처 요약
- unresolved issue
- visual notes

### Run Memory

- 현재 세션 작업 내용
- 작업 중 발견한 예외
- gate 참고 메모

---

## 5. 이벤트 흐름

```text
stage completed
  -> output registered
  -> gate requested
  -> gate pass/fail stored
  -> state transitioned
  -> shared memory updated
  -> AG-OM reschedules
```

---

## 6. Gate 흐름

### Pass

1. gate result 저장
2. stage status `completed`
3. downstream stage를 `pending`
4. AG-OM이 work queue 갱신

### Fail

1. gate result 저장
2. stage status `gate_failed`
3. `return_to_stage` 기록
4. AG-OM이 재작업 work item 발행

### Blocked

1. blocked reason 저장
2. unblock condition 저장
3. queue에서 제외
4. AG-OM이 대체 작업 배정

---

## 7. 병렬 실행 규칙

허용:

- 다른 챕터, 같은 단계
- 다른 챕터, 다른 단계
- 다른 책, 어떤 단계든

금지:

- 같은 챕터의 stage 연쇄 동시 실행
- 같은 챕터 안에서 subsection node의 live API 병렬 호출
- 같은 shared memory key에 대한 동시 쓰기
- publication과 pre-publication gate 미통과 단계 동시 실행

추가 규칙:

- `S4`, `S5`, `S8A`의 node는 한 챕터 안에서 반드시 순차 실행한다.
- `S6A`는 chapter-level handoff stage이므로 다른 chapter와 병렬 가능하지만, 같은 chapter의 `S7`과 동시 실행하면 안 된다.
- live model 호출은 `VERTEX_REQUEST_MIN_INTERVAL_MS` 간격 정책을 따른다.

---

## 8. 재작업 규칙

재작업은 stage rollback이 아니라 work re-entry다.

즉:

- 원래 stage 결과는 보존
- gate failure 기록도 보존
- 수정 지시를 포함한 새 work item 생성
- 재실행 후 새 artifact version 생성

`with_the_king` 기준으로는 `draft5`를 덮어쓰지 않고 `draft6`를 추가 생성하는 `S8A`가 이 원칙의 대표 사례다.

---

## 9. `with_the_king`에 대한 특수 오케스트레이션

이 책은 시간 민감성이 높은 트렌드형 프로젝트이므로:

- 조사 단계의 freshness score를 항상 계산
- review 단계에서 오래된 citation 자동 재검토
- publication 직전 latest trend refresh를 선택적으로 허용

즉 AG-OM은 일반 책보다 S2/S5를 더 자주 재스케줄링할 수 있다.
