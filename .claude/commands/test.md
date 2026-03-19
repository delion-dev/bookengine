# 전체 테스트 실행

## API 단위 테스트
```bash
cd /d/solar_book && python -m pytest engine_api/tests/ -v --tb=short
```

## TypeScript + Lint
```bash
cd /d/solar_book/frontend && npx tsc --noEmit && npm run lint
```

## 전체 (순서대로)
```bash
cd /d/solar_book
python -m pytest engine_api/tests/ -v --tb=short
cd frontend
npx tsc --noEmit
npm run lint
```
