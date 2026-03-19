# Clean Architecture

## Goal

이 플랫폼은 stage별 에이전트가 파일을 직접 조작하는 것이 아니라, 안정된 API를 호출해 작업하도록 설계한다.

핵심 문장:

- 에이전트는 `engine.stage.run` 또는 하위 `engine.*` API만 호출한다.
- stage별 비즈니스 로직은 use case 모듈에 둔다.
- gate, contract, state transition은 도메인 규칙으로 고정한다.
- 책별 데이터는 로컬 아티팩트로 분리한다.

## Layers

### 1. Interface Adapters

- [core_engine_cli.py](/d:/solar_book/tools/core_engine_cli.py)
- [stage_api.py](/d:/solar_book/engine_core/stage_api.py)

역할:

- 사용자/에이전트 요청을 API 호출로 변환
- `stage_id`, `chapter_id`, `book_root`를 표준 입력으로 정리
- `engine.stage.run` 호출마다 `engine.session.open/close`와 declared output registration을 공통 래핑

### 2. Application / Use Cases

- [architecture.py](/d:/solar_book/engine_core/architecture.py)
- [orchestration.py](/d:/solar_book/engine_core/orchestration.py)
- [research.py](/d:/solar_book/engine_core/research.py)
- [planner.py](/d:/solar_book/engine_core/planner.py)
- [writer.py](/d:/solar_book/engine_core/writer.py)
- [asset_collection.py](/d:/solar_book/engine_core/asset_collection.py)
- [reviewer.py](/d:/solar_book/engine_core/reviewer.py)
- [visual_planner.py](/d:/solar_book/engine_core/visual_planner.py)

역할:

- stage별 핵심 과업 실행
- 입력 계약 검증
- 산출물 생성
- gate 호출
- 상태 전이와 work order 반영

### 3. Domain Services

- [targets.py](/d:/solar_book/engine_core/targets.py)
- [anchors.py](/d:/solar_book/engine_core/anchors.py)
- [references.py](/d:/solar_book/engine_core/references.py)
- [contracts.py](/d:/solar_book/engine_core/contracts.py)
- [gates.py](/d:/solar_book/engine_core/gates.py)
- [stage.py](/d:/solar_book/engine_core/stage.py)
- [work_order.py](/d:/solar_book/engine_core/work_order.py)

역할:

- 분량 계획
- 앵커 계획/주입
- 레퍼런스 인덱스
- 계약 해석
- gate 판단
- 상태 규칙
- 오케스트레이션 큐 계산

### 4. Infrastructure

- [common.py](/d:/solar_book/engine_core/common.py)
- [book_state.py](/d:/solar_book/engine_core/book_state.py)
- [memory.py](/d:/solar_book/engine_core/memory.py)
- [registry.py](/d:/solar_book/engine_core/registry.py)
- [session.py](/d:/solar_book/engine_core/session.py)

역할:

- 파일 I/O
- registry 저장
- shared memory 저장
- 세션 로그 저장

## Stage Mapping

| Stage | Agent | Public API | Use Case |
| --- | --- | --- | --- |
| `S0` | `AG-AR` | `engine.stage.run(S0)` | `architecture.py` |
| `S1` | `AG-OM` | `engine.stage.run(S1)` | `orchestration.py` |
| `S2` | `AG-RS` | `engine.stage.run(S2)` | `research.py` |
| `S3` | `AG-00` | `engine.stage.run(S3)` | `planner.py` |
| `S4` | `AG-01` | `engine.stage.run(S4)` | `writer.py` |
| `S4A` | `AG-01B` | `engine.stage.run(S4A)` | `anchor_injector.py` |
| `S5` | `AG-02` | `engine.stage.run(S5)` | `reviewer.py` |
| `S6` | `AG-03` | `engine.stage.run(S6)` | `visual_planner.py` |
| `S6A` | `AG-AS` | `engine.stage.run(S6A)` | `asset_collection.py` |
| `S7` | `AG-04` | `engine.stage.run(S7)` | `visual_renderer.py` |
| `S8` | `AG-05` | `engine.stage.run(S8)` | `copyeditor.py` |
| `S8A` | `AG-05A` | `engine.stage.run(S8A)` | `amplifier.py` |
| `S9` | `AG-06` | `engine.stage.run(S9)` | `publication.py` |

## Current Rule

- CLI는 직접 `architecture.py` 같은 모듈을 몰라도 된다.
- 표준 진입점은 `run-stage`와 `engine.stage.run`이다.
- stage별 세부 규칙 변경은 use case 내부가 아니라 core spec과 domain service부터 갱신해야 한다.
