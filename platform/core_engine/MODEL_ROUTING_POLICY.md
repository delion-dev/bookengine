# Model Routing Policy

## 목적

이 문서는 stage/task/section별 모델 선택 정책을 전역 Core Engine 규약으로 정의한다.

원칙:

- 에이전트는 모델 이름을 직접 하드코딩하지 않는다.
- stage는 `engine.model.route_provider`가 아니라 `engine.model_policy.resolve_stage_route`를 통해 진입한다.
- 책별 규칙은 지역 컨텍스트에 담기고, 모델 선택 규칙은 전역 정책으로 유지한다.

---

## 1. 전역 특성

- 모델 선택 규칙은 모든 책에 공통이다.
- `S4`, `S5`, `S8A`처럼 비용과 품질 trade-off가 큰 stage에만 우선 적용한다.
- `high_quality / balanced / fast` 3등급 profile을 사용한다.

---

## 2. 지역 특성

- chapter part
- section key
- node 목적

이 정보는 route resolver의 입력으로 들어가지만, 정책 파일을 직접 수정하지 않고 override 테이블로만 해석된다.

예:

- `S4 insight`: 더 높은 품질 profile
- `S8A hook`: balanced profile
- `S5 grounded_research`: high_quality profile

---

## 3. 구현

- 정책 정의: [model_routing_policy.json](/d:/solar_book/platform/core_engine/model_routing_policy.json)
- 해석기: [model_policy.py](/d:/solar_book/engine_core/model_policy.py)
- 게이트웨이: [model_gateway.py](/d:/solar_book/engine_core/model_gateway.py)

---

## 4. 운영 규칙

- 실제 모델 이름은 `.env`의 `VERTEX_MODEL_*`를 읽는다.
- 정책은 model profile을 결정하고, 게이트웨이는 해당 profile에 맞는 model override를 적용한다.
- `fast` profile은 가능한 경우 `VERTEX_MODEL_FAST`를 사용한다.
- `high_quality` profile은 task 기본 모델을 유지한다.
