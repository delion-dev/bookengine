# 개발 서버 기동

FastAPI 백엔드 서버를 기동합니다.

```bash
cd d:/solar_book && python tools/core_engine_cli.py run-server
```

포트 충돌 시:
```bash
netstat -ano | findstr ":8000"
taskkill /PID <PID> /F
```
