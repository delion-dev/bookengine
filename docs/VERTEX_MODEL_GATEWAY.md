# Vertex Model Gateway

이 문서는 Core Engine의 Google model gateway 규약을 정리한다.

## 1. 원칙

- 에이전트는 Google SDK나 REST를 직접 호출하지 않는다.
- 모든 모델 호출은 `engine.model.*` API를 통해서만 수행한다.
- `.env`는 런타임 설정만 제공하며, stage 로직은 설정 파일을 직접 해석하지 않는다.
- `S4`와 `S5`는 라이브 호출 실패 시 안전한 폴백으로 돌아간다.

## 2. 환경 변수

필수 값은 provider와 인증 모드에 따라 다르다.

- `MODEL_GATEWAY_PROVIDER=vertex_ai` + `api_key` + `express`
  - `VERTEX_AUTH_MODE`
  - `VERTEX_API_KEY`
- `MODEL_GATEWAY_PROVIDER=gemini_api` + `api_key` + `direct`
  - `VERTEX_AUTH_MODE`
  - `GEMINI_API_KEY`
    또는 현재 운영처럼 `VERTEX_API_KEY`를 fallback key로 사용 가능
- `MODEL_GATEWAY_PROVIDER=vertex_ai` + `access_token` + `standard`
  - `VERTEX_AUTH_MODE`
  - `VERTEX_PROJECT_ID`
  - `VERTEX_REGION`
  - `VERTEX_ACCESS_TOKEN`

권장:

- `VERTEX_ENABLE_LIVE_CALLS`
- `VERTEX_MODEL_TEXT`
- `VERTEX_MODEL_STRUCTURED`
- `VERTEX_MODEL_RESEARCH`
- `VERTEX_MODEL_SAFETY`

예시는 [`.env.example`](/d:/solar_book/.env.example)에 있다.

## 3. 엔드포인트 규약

### `vertex_ai` + `api_key`

- 엔진 표준: `express` 엔드포인트
- URL 형식:
  - `https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent?key=...`
- 주의:
  - 이 모드는 express-mode key가 필요하다.
  - `project_id`, `location`은 선택 메타데이터일 뿐 URL 경로에 들어가지 않는다.

### `gemini_api` + `api_key`

- 엔진 표준: `direct` 엔드포인트
- URL 형식:
  - `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- 인증:
  - `x-goog-api-key` 헤더 사용
- 운영 메모:
  - 다른 프로젝트에서 Google AI Studio / Gemini API direct가 정상이고 Vertex express만 `WinError 10013`을 내는 경우, host-specific 보안 정책 우회 수단이 될 수 있다.

### `vertex_ai` + `access_token`

- 엔진 표준: `standard` 엔드포인트
- URL 형식:
  - `https://aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/publishers/google/models/{model}:generateContent`
- 주의:
  - full Vertex REST 경로는 OAuth2 access token 또는 ADC가 필요하다.
  - API key로 이 경로를 호출하면 `401 UNAUTHENTICATED`가 날 수 있다.

## 4. 전역 API 매핑

- `engine.model.route_provider`
  - 모델, 엔드포인트, 인증 모드 결정
- `engine.model.resolve_stage_route`
  - stage/task/section별 전역 모델 라우팅 정책 적용
- `engine.model.generate_text`
  - 일반 텍스트 생성
- `engine.model.generate_structured`
  - JSON 스키마 기반 생성
- `engine.model.grounded_research`
  - Google Search grounding 기반 조사 보강
- `engine.model.safety_check`
  - 안전성 구조화 판정

구현 파일:

- [model_gateway.py](/d:/solar_book/engine_core/model_gateway.py)
- [model_policy.py](/d:/solar_book/engine_core/model_policy.py)
- [llm_client.py](/d:/solar_book/engine_core/llm_client.py)

`llm_client.py`는 `LLMConfig`, `GeminiClient` 형태의 호환 래퍼다.
내부 전송은 `engine.model.*` 게이트웨이를 사용하며, provider 설정에 따라 Vertex REST 또는 Gemini API direct로 라우팅된다.

## 5. Stage 연결

- `S4 / AG-01`
  - raw guide + research questions + policy context를 기반으로 구조화 초고 생성
  - 가능하면 grounded brief를 먼저 만들어 prompt context에 포함
  - 실패 시 템플릿 폴백 사용

- `S5 / AG-02`
  - grounded research로 최신 웹 기반 근거 수집
  - 결과를 `citations.json`, `reference_index.json`, appendix에 반영
  - 실패 시 구조적 citation attach만 수행

## 6. 운영 점검 명령

```powershell
python tools\core_engine_cli.py show-model-config
python tools\core_engine_cli.py diagnose-runtime
python tools\core_engine_cli.py preview-model-request --task-type generate_structured --prompt "테스트"
python tools\core_engine_cli.py diagnose-vertex-auth
```

## 7. 검증 메모

- 2026-03-15 live diagnostic:
  - sandbox 안에서는 `vertex_ai`와 `gemini_api` 모두 `WinError 10013`이 재현됐다.
  - unrestricted 실행에서는 `gemini_api` direct probe가 성공했다.
  - 따라서 현재 우선 운영 방향은 `MODEL_GATEWAY_PROVIDER=gemini_api` 고정 후 stage 검증을 진행하는 것이다.
- 운영 해석:
  - `WinError 10013`은 인증 로직 자체보다 실행 컨텍스트와 host-specific 소켓 차단에 더 가깝다.
  - 따라서 공용 게이트웨이는 provider 교체가 가능해야 하고, 현 시점에서는 Gemini API direct가 실제 우회 경로로 확인됐다.
