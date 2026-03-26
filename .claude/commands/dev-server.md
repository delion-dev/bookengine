# 개발 서버 기동

## FastAPI 서버 (터미널 1)

```bash
cd /d/solar_book && python tools/core_engine_cli.py run-server
```

## Tauri 개발 앱 (터미널 2)

```bash
cd /d/solar_book/frontend && npm run tauri dev
```

## 서버 상태 확인

```bash
curl -s http://localhost:8000/engine/status | python -m json.tool
```

## 포트 8000 충돌 해결 (PowerShell)

```powershell
netstat -ano | findstr ":8000"
taskkill /PID <PID> /F
```

## 포트 8000 충돌 해결 (Git Bash)

```bash
# PID 확인
cmd.exe /c "netstat -ano | findstr :8000"
# 프로세스 종료
cmd.exe /c "taskkill /PID <PID> /F"
```
