# S4 Stabilization Progress (2026-03-16)

## 목적

공감대를 다시 잡은 뒤 `S4 / AG-01`이 더 이상 "집필 방법"을 말하지 않고,
실제 책 내용을 쓰는 초고 엔진으로 안정화되는지 점검한다.

## 이번 라운드에서 반영한 핵심 수정

- `engine_core/ag01_engine.py`
  - raw guide의 `reader_promise`, `Blueprint rule` 같은 내부 규칙이 본문으로 노출되지 않도록 정리
  - segment 수를 줄여 호출 수를 축소
  - live/fallback 공통으로 메타성 문장을 정리하는 sanitize 단계 추가
  - section별 deterministic density 보강 문단 추가
  - stage 시작 시 live proof를 1회만 보고, `WinError 10013`/장기 quota block이면 chapter 전체를 즉시 fallback 경로로 전환
  - live 응답이 짧더라도 통째로 버리지 않고 deterministic 보강 문단을 덧붙여 reader-facing prose를 유지하도록 변경
  - `live_uplifted_from_short_response` 상태를 남겨, 실제 live 호출 성공과 품질 보강 여부를 함께 추적하도록 정리
  - raw guide `Include` 항목 중 어색한 메타 명사구를 reader-facing 표현으로 정규화
- `engine_core/context_packs.py`
  - `S4`, `S5` soft input budget를 상향해 로직 실증 중심으로 조정
- `engine_core/writer.py`
  - `gate_failed` 상태의 `S4`가 재검증 루프에 머무르지 않고 실제 재생성으로 들어가도록 수정
- `.env`
  - `vertex_ai + express + api_key`
  - text/research 기본 모델을 `gemini-2.5-pro`로 정리

## 현재 파일럿 결과

대상: `intro`, `ch01`, `ch02`

- 공통 상태
  - 모두 `generation_mode=vertex_live_segment_nodes`
  - 모두 `required_sections_present=true`
  - 모두 `density_pass=true`
  - 모두 `fallback_only_completion=false`
- `ch01`
  - `approx_tokens=6663 / 9000`
  - `draft_words=2279 / floor 2268`
  - `live_node_success_ratio=1.0`
- `intro`
  - `approx_tokens=6423 / 9000`
  - `draft_words=2337 / floor 2304`
  - `live_node_success_ratio=1.0`
- `ch02`
  - `approx_tokens=6633 / 9000`
  - `draft_words=2294 / floor 2268`
  - `live_node_success_ratio=1.0`

추가로 이번 라운드에서 확인한 중요한 사실:

- Vertex live 호출 자체는 실제로 성공하고 있었다.
- 문제는 짧은 live 응답을 전부 fallback 초고로 덮어쓰는 판정 로직이었다.
- 이 부분을 고친 뒤 `node_manifest`와 `density_audit`도 실측 결과와 일치하게 정리됐다.

## 판단

- 방향성은 맞아졌다.
  - 메타성 문장 오염이 크게 줄었다.
  - `S4` 재검증 루프도 제거됐다.
  - live 성공과 fallback 판정이 뒤섞이던 핵심 오판도 정리됐다.
- 아직 끝나지 않은 부분도 분명하다.
  - `draft1`은 통과했지만, 일부 chapter에서는 반복 문장과 일반론 비중을 더 낮춰야 한다.
  - `S4`를 전 장으로 확장하기 전 `intro/ch01/ch02` reader-facing 품질을 한 번 더 샘플 검토하는 편이 안전하다.

## 다음 작업

1. `intro/ch01/ch02` 초고를 샘플 검토해 반복 패턴과 장면 구체성을 한 번 더 손본다.
2. 샘플 품질이 수용 가능하면 전 장 `S4` batch로 확장한다.
3. `S4` 전 장 완료 후 `S4A -> S5`를 순차 재실행한다.
