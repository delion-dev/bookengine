# AG-01 Enhancement Spec

## Goal

`AG-01`은 더 이상 4개 섹션을 느슨하게 채우는 초고 골격 생성기가 아니다.
강화된 `AG-01`의 목표는 다음 두 가지다.

1. `S3` raw guide를 실제 집필 계약으로 소비한다.
2. `draft1 >= target_words * 0.90`에 가까운 실질 초고를 세그먼트 단위로 만든다.

## Core Design

`AG-01`은 아래 5단계 내부 함수로 동작한다.

1. `plan_segments`
   - 장을 `8~16개` 세그먼트로 분해한다.
   - 각 세그먼트는 `claim_intent`, `evidence_slot`, `reader_payoff`, `anchor_obligation_ids`를 가진다.

2. `design_narrative`
   - 세그먼트별 `opening_tactic`, `continuity_bridge`, `tone_guardrail`, `forbidden_drift_topics`를 설계한다.

3. `implement_segments`
   - 세그먼트 단위로 live 호출한다.
   - 실패하면 출판 가능한 한국어 fallback prose로 대체한다.

4. `verify_density`
   - `draft_coverage_ratio`, `live_node_success_ratio`, `fallback_only_completion`을 점검한다.

5. `report_session`
   - `completed`, `completed_with_alert`, `gate_failed` 중 하나의 운영 판정을 남긴다.

## Context Strategy

효율적인 컨텍스트 관리를 위해 세그먼트 호출에는 아래만 넣는다.

- section / segment brief
- reader payoff
- evidence slot
- local note
- continuity bridge
- 최근 2개 세그먼트의 짧은 발췌
- grounded source signals 상위 3개
- rights guardrails 상위 4개

넣지 않는 것:

- raw guide 전체 본문 반복
- blueprint 원문 전체
- style guide 전체
- 이미 완성된 장 전체 본문

즉 `정적 정책은 context pack`, `동적 집필 정보는 segment prompt`로 분리한다.

## Runtime Semantics

- 기본 실행 모드: `ag01_segment_pipeline`
- 네트워크성 전량 fallback일 때만 `1회 recovery pass`
- `S4` 내부 expansion loop는 1차 구현에서는 `0회`, cap만 기록
- fallback만으로 draft를 만들더라도 `session_report`에 `completed_with_alert`를 남긴다.

## Artifacts

`S4`는 이제 아래 5개 산출물을 남긴다.

- `{chapter_id}_draft1.md`
- `{chapter_id}_segment_plan.json`
- `{chapter_id}_narrative_design.json`
- `{chapter_id}_density_audit.json`
- `{chapter_id}_session_report.json`

`draft1.md`는 사람이 읽는 초고 뷰만 담당한다.
집필 계약, segment metadata, density 진단, runtime 판정은 JSON 산출물에 남기고 본문에는 직접 노출하지 않는다.

이 구조 덕분에 사용자는 `무엇을 쓰려 했는가 -> 어떻게 쓰려 했는가 -> 실제로 얼마나 나왔는가`를 단계별로 육안 검수할 수 있다.
