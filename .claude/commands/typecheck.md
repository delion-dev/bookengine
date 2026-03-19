# TypeScript 타입 검사

프론트엔드 전체 타입 에러를 확인합니다.

```bash
cd /d/solar_book/frontend && npx tsc --noEmit
```

에러만 필터링:
```bash
cd /d/solar_book/frontend && npx tsc --noEmit 2>&1 | grep "error TS"
```
