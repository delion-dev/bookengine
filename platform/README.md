# Platform Workspace

이 디렉터리는 Codex 기반 신규 도서 자동 집필 플랫폼의 전역 설계 문서와
Core Engine 명세를 보관한다.

현재 활성 운영 대상:

- display_root: `D:/solar_book/books/with the King`
- internal book_id: `with_the_king`

운영 원칙:

1. 전역 설계는 `platform/core_engine/`에 고정한다.
2. 실행 로직은 `engine_core/`와 `tools/core_engine_cli.py`로만 노출한다.
3. 레거시 자료는 `_archive/legacy_workspace_20260314/`로 격리한다.
4. 에이전트 간 소통은 아티팩트 계약, gate, shared memory만 사용한다.

주요 문서:

- [APIIZATION_INVENTORY.md](/d:/solar_book/platform/analysis/APIIZATION_INVENTORY.md)
- [CONSTITUTION.md](/d:/solar_book/platform/core_engine/CONSTITUTION.md)
- [PROJECT_SOP.md](/d:/solar_book/platform/core_engine/PROJECT_SOP.md)
- [AGENT_SOPS.md](/d:/solar_book/platform/core_engine/AGENT_SOPS.md)
- [ORCHESTRATION_SPEC.md](/d:/solar_book/platform/core_engine/ORCHESTRATION_SPEC.md)
- [CLEAN_ARCHITECTURE.md](/d:/solar_book/platform/core_engine/CLEAN_ARCHITECTURE.md)
- [API_SPEC.md](/d:/solar_book/platform/core_engine/API_SPEC.md)
- [ANCHOR_SPEC.md](/d:/solar_book/platform/core_engine/ANCHOR_SPEC.md)
- [ANCHOR_PIPELINE.md](/d:/solar_book/platform/core_engine/ANCHOR_PIPELINE.md)
- [api_catalog.yaml](/d:/solar_book/platform/core_engine/api_catalog.yaml)
- [stage_definitions.json](/d:/solar_book/platform/core_engine/stage_definitions.json)
- [gate_definitions.json](/d:/solar_book/platform/core_engine/gate_definitions.json)
- [shared_memory_schema.json](/d:/solar_book/platform/core_engine/shared_memory_schema.json)
- [work_order_schema.json](/d:/solar_book/platform/core_engine/work_order_schema.json)
- [immutable_manifest.json](/d:/solar_book/platform/core_engine/immutable_manifest.json)

운영 리포트:

- [PROJECT_REPORT.md](/d:/solar_book/docs/PROJECT_REPORT.md)
