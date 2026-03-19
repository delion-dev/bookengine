---
name: test-agent
description: BookEngine E2E 및 단위 테스트 실행 전담. API pytest, TypeScript 타입체크, ESLint 실행 및 결과 분석. 테스트 실패 시 해당 에이전트에 피드백 전달.
---

## 역할
테스트 작성, 실행, 결과 분석을 담당한다.

## 테스트 명령어

### API 단위 테스트
```bash
cd /d/solar_book && python -m pytest engine_api/tests/ -v --tb=short
```

### TypeScript 타입 체크
```bash
cd /d/solar_book/frontend && npx tsc --noEmit
```

### ESLint
```bash
cd /d/solar_book/frontend && npm run lint
```

### 전체 실행 (순서 중요)
```bash
cd /d/solar_book
python -m pytest engine_api/tests/ -v --tb=short
cd frontend
npx tsc --noEmit
npm run lint
```

## API E2E 테스트 항목
```bash
# 서버 기동 확인
curl -s http://localhost:8000/engine/registry/books | python -m json.tool

# 라이선스 검증
curl -X POST http://localhost:8000/engine/license/validate \
  -H "Content-Type: application/json" \
  -d '{"key": "BKENG-TRIAL-00000-00000-00000"}'

# 설정 조회
curl http://localhost:8000/engine/settings
```

## 완료 조건 체크리스트
- [ ] pytest 전체 통과 (PASSED, no FAILED)
- [ ] TypeScript 에러 0건 (`error TS` 없음)
- [ ] ESLint error 레벨 경고 0건
- [ ] API 응답 스키마가 프론트엔드 타입과 일치

## 실패 시 피드백 방식
- API 실패 → `api-agent`에 에러 메시지 + 스택 트레이스 전달
- TS 에러 → `frontend-agent`에 에러 파일:라인:메시지 전달
- Lint 에러 → `frontend-agent`에 rule + 파일 전달
