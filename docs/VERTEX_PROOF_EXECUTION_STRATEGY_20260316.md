# Vertex Proof Execution Strategy (2026-03-16)

## 1. 현재 실측 상태

- 설정 잠금 결과:
  - `MODEL_GATEWAY_PROVIDER=vertex_ai`
  - `VERTEX_AUTH_MODE=api_key`
  - `VERTEX_ENDPOINT_MODE=express`
  - `VERTEX_MODEL_TEXT=gemini-2.5-pro`
  - `VERTEX_MODEL_RESEARCH=gemini-2.5-pro`
  - `VERTEX_MODEL_FAST=gemini-2.5-flash`
- `show-model-config` 기준 런타임은 현재 `vertex_ai / express / api_key / gemini-2.5-pro`로 해석된다.
- `diagnose-vertex-auth` 기준 실제 live probe는 다음 오류로 중단된다.
  - `Vertex generateContent network error: [WinError 10013] 액세스 권한에 의해 숨겨진 소켓에 액세스를 시도했습니다`

즉, 현재 상태는 더 이상 `gemini_api` direct 오배치가 아니라, `Vertex express`는 맞게 잡혔지만 로컬 실행 환경이 `aiplatform.googleapis.com` outbound 소켓을 차단하는 상태다.

---

## 2. 왜 이전 방식이 비효율적이었는가

이전 경로의 낭비 포인트는 두 가지였다.

1. 실제 런타임이 `vertex_ai`가 아니라 `gemini_api` direct였다.
   - `gemini-3.1-pro-preview` direct 경로에서 `429 quota exceeded`가 누적됐다.
   - 사용자는 Vertex 유료 구독을 의도했지만, 실실행은 다른 quota 체계를 탔다.

2. stage가 provider proof 없이 다수 노드 호출로 바로 들어갔다.
   - `S4`는 segment/node 단위로 여러 번 호출한다.
   - `S5`도 grounded review를 section/node 단위로 여러 번 호출한다.
   - provider가 막히거나 quota가 다 떨어진 상태에서 이런 구조는 토큰과 시간만 낭비한다.

---

## 3. 즉시 반영한 조치

### 3.1 Provider lock

`.env`를 `vertex_ai + express + api_key`로 잠가 Vertex 의도와 실제 실행 경로를 일치시켰다.

### 3.2 모델 경로 정리

preview 모델 `gemini-3.1-pro-preview` 대신 현재 운영 기본값을 아래로 맞췄다.

- text: `gemini-2.5-pro`
- structured: `gemini-2.5-pro`
- research: `gemini-2.5-pro`
- fast/safety: `gemini-2.5-flash`

### 3.3 장기 quota retry 차단

`engine_core/model_gateway.py`는 이제 `429` 응답 본문에 긴 retry window 또는 quota exhaustion 신호가 보이면 즉시 hard-stop한다.

- 더 이상 `2~3회` 의미 없는 재시도를 하지 않는다.
- hint에 `switch provider/model or wait`를 남긴다.

---

## 4. 현재 남은 실제 blocker

현재 blocker는 인증 로직이 아니라 로컬 네트워크/보안 계층이다.

- 상태: `WinError 10013`
- 의미: Windows/보안 제품/방화벽/샌드박스가 소켓 접근을 차단
- 영향: `Vertex express` live proof가 실패하므로 `S4 -> S4A -> S5` 일괄 live 재실행을 시작하면 안 된다.

따라서 지금은 "모델 라우팅 오설계"보다 "endpoint security unblock"이 먼저다.

---

## 5. 앞으로의 효율적 실행 정책

### Rule 1. Provider proof first

대량 stage 실행 전에 아래 1회만 수행한다.

- `python tools/core_engine_cli.py diagnose-vertex-auth`

통과 전에는 `S4/S5/S8A` live batch를 시작하지 않는다.

### Rule 2. Hard stop on provider-block / long quota

아래 두 경우에는 즉시 중단한다.

- `WinError 10013`
- `429 quota exhausted` with long retry window

이 경우 재시도 루프를 돌리지 않는다.

### Rule 3. One pilot chapter before batch

live proof가 통과하면 순서는 다음과 같다.

1. `S4 ch01` 1회
2. 결과 품질/게이트 확인
3. `S4A ch01`
4. `S5 ch01`
5. 이 3단계가 clean일 때만 전 장 batch

### Rule 4. Batch order

검증이 끝나면 전 장 일괄 순서는 다음과 같다.

1. all chapters `S4`
2. all chapters `S4A`
3. all chapters `S5`

중간에 provider block이 감지되면 즉시 중단하고 다음 chapter로 넘어가지 않는다.

---

## 6. 다음 리팩터링 권고

provider unblock 이후에도 호출 수를 줄이기 위한 구조 개선이 필요하다.

### S4 권고

현재:

- grounded brief 1회
- segment/node generate 여러 회
- 필요 시 recovery pass

권고:

- chapter-level research brief 1회
- section bundle 또는 chapter bundle generate 1회
- 부족 시 repair pass 1회

즉, `many-node generation`에서 `few-call proof-oriented generation`으로 바꾼다.

### S5 권고

현재:

- section/node grounded review 다중 호출

권고:

- chapter-level grounded review 1회
- citation attach / rights review / freshness summary는 deterministic postprocess로 분리

---

## 7. 운영 판단

지금 시점의 올바른 판단은 다음과 같다.

- `Vertex` 라우팅 자체는 바로잡혔다.
- preview direct quota 낭비 루프는 차단 방향으로 수정됐다.
- 그러나 live execution은 아직 `WinError 10013` 때문에 blocked다.
- 따라서 당장 필요한 것은 stage batch 실행이 아니라 outbound unblock이다.

provider unblock이 확인되면 그 다음부터는 `diagnose-vertex-auth 1회 -> ch01 pilot -> full batch` 순서로만 진행한다.
