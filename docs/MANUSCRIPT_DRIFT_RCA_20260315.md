# Manuscript Drift RCA

Date: 2026-03-15
Scope: `with_the_king` stage drift and anchor render mismatch

## Symptoms

- `draft4~draft6` 일부 챕터가 독자용 본문보다 편집 메모처럼 보인다.
- `draft2` 이후 본문에 `Review Layer`, `Citation Attachments`, `Visual Planning Status` 같은 운영 메타가 섞인다.
- Mermaid 계열 앵커가 최종 HTML/PDF에서 실제 시각물 대신 문법 코드로 노출된다.

## Root Cause

1. `S4 / AG-01` fallback 본문이 독자용 산문이 아니라 에디토리얼 지시문에 가깝다.
   - 위치: [writer.py](/d:/solar_book/engine_core/writer.py)
   - 흔적: `장의 출발점은`, `이 장의 맥락은`, `현재 초고는`, `이후 AG-02 리뷰 단계`, `마지막 단락은`

2. `S5 / AG-02`가 review 메타를 sidecar가 아니라 `draft2` 본문 끝에 직접 붙였다.
   - 위치: [reviewer.py](/d:/solar_book/engine_core/reviewer.py)
   - 영향: `Review Layer`, `Grounded Findings`, `Grounded Sources`, `Review Resolution`이 본문 오염원으로 전파됨

3. `S6 / AG-03`와 `S8 / AG-05`는 내부 섹션을 일부만 제거했다.
   - 위치: [visual_planner.py](/d:/solar_book/engine_core/visual_planner.py), [copyeditor.py](/d:/solar_book/engine_core/copyeditor.py)
   - 영향: 메타 헤딩은 일부 지워도 본문 안 메타 문장은 그대로 통과

4. `S7 / AG-04`는 시각화를 “출판용 렌더”가 아니라 “구조 치환”으로만 구현했다.
   - 위치: [visual_renderer.py](/d:/solar_book/engine_core/visual_renderer.py)
   - 영향: Mermaid는 code fence, callout은 markdown admonition, table은 markdown table로 남음

5. `S7` gate는 한동안 `Visual Integration Summary` 같은 내부 요약을 사실상 요구했다.
   - 위치: [gates.py](/d:/solar_book/engine_core/gates.py)
   - 영향: 독자용 draft와 운영 summary가 분리되지 않음

## Implemented Fixes

- 공통 본문 정제기 추가
  - [manuscript_integrity.py](/d:/solar_book/engine_core/manuscript_integrity.py)
- `S5 draft2`를 review sidecar와 분리
  - [reviewer.py](/d:/solar_book/engine_core/reviewer.py)
- `S6`, `S8`, `S9`에 공통 정제기 적용
  - [visual_planner.py](/d:/solar_book/engine_core/visual_planner.py)
  - [copyeditor.py](/d:/solar_book/engine_core/copyeditor.py)
  - [publication.py](/d:/solar_book/engine_core/publication.py)
- `S4` fallback 문장을 독자용 기본 산문으로 교체
  - [writer.py](/d:/solar_book/engine_core/writer.py)
- `S7`의 내부 요약 섹션 강제 제거
  - [visual_renderer.py](/d:/solar_book/engine_core/visual_renderer.py)
  - [gates.py](/d:/solar_book/engine_core/gates.py)
- copyedit/gate에서 본문 메타 마커를 새로 감지
  - `장의 출발점은`, `현재 초고는`, `AG-02 리뷰 단계` 등

## Remaining Work

1. 기존 오염 챕터는 코드 수정만으로 자동 복구되지 않는다.
   - 현재 산출물은 이미 잘못된 본문을 포함하고 있으므로, 영향을 받은 챕터는 다시 stage를 태워야 한다.

2. 재생성 우선순위
   - `S4` fallback 오염 챕터: `ch04~outro`
   - 이후 `S5 -> S6 -> S7 -> S8 -> S8A -> S9`

3. Mermaid/anchor 출판 렌더는 별도 구현이 남아 있다.
   - 현행 `S7`은 markdown 구조 치환까지만 수행
   - 최종 해결은 `S7` 또는 `S9`에서 SVG/HTML 컴포넌트 선렌더를 추가해야 함
