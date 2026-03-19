# Meta Block Specification

## Purpose

이 문서는 reader-facing prose와 운영 메타를 분리하기 위한 표준 `META_START ... META_END` 문법을 정의한다.

핵심 원칙:

- meta block은 anchor가 아니다.
- meta block은 시각화 계약이 아니라 운영/검토/인수인계 계약이다.
- meta block은 후속 stage에서 제거 가능해야 한다.
- 출판 단계까지 남아 있으면 실패다.

## Canonical Grammar

```md
<!-- META_START id="META_CH05_S4_001" kind="editorial_intent" stage="S4" owner="AG-01" action="remove_before_visual_plan" -->
- target payoff: 기록과 해석의 경계를 독자에게 선명하게 보여 줄 것
- reviewer hint: primary history source 우선
<!-- META_END id="META_CH05_S4_001" -->
```

필수 속성:

- `id`: 전역적으로 유일한 meta block identifier
- `kind`: 메타 블록 종류
- `stage`: 생성 stage
- `owner`: 생성 agent
- `action`: 제거/보존 정책

권장 `kind`:

- `editorial_intent`
- `review_handoff`
- `visual_hint`
- `rights_hint`
- `repair_note`

권장 `action`:

- `remove_before_visual_plan`
- `remove_before_visual_render`
- `remove_before_publication`

## Difference From Anchor Block

anchor block:

- 독자용 원고 안의 시각화 작업 범위
- 후속 stage가 `ANCHOR_SLOT`을 실제 산출물로 치환

meta block:

- 운영상 참고 정보
- 후속 stage가 제거 또는 sidecar 분리
- 독자용 본문으로 남지 않음

즉 anchor는 render target이고, meta block은 process note다.

## Lifecycle Rule

1. stage가 꼭 필요할 때만 meta block을 삽입한다.
2. 가능한 경우 sidecar artifact를 우선 사용한다.
3. `S6` 이후 reader-facing draft에는 meta block 잔존이 없어야 한다.
4. `S9` HTML/EPUB/PDF에는 meta block이 절대 남아 있으면 안 된다.

## Engine Rule

- parser: `engine_core/meta_blocks.py`
- reader cleanup: `engine_core/manuscript_integrity.py`
- gate detection: `engine_core/gates.py`
- publication fail-safe: `engine_core/publication.py`
