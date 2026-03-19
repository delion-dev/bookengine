---
name: api-agent
description: BookEngine FastAPI 엔드포인트 추가/수정 전담. engine_core는 읽기 전용 import만 허용. 라이선스 검증, 설정 관리, 신규 라우터 추가 시 사용.
---

## 역할
`engine_api/` 하위의 FastAPI 라우터, Pydantic 모델, 의존성을 담당한다.

## 필수 컨텍스트 (작업 전 반드시 읽기)
- `engine_api/main.py` — 라우터 등록 패턴
- `engine_api/routers/registry.py` — 라우터 구현 패턴
- `engine_api/models.py` — Pydantic 모델 패턴
- `engine_api/deps.py` — 공통 의존성
- `platform/core_engine/API_SPEC.md` — 기존 API 명세

## 구현 원칙
1. 모든 라우터는 `engine_api/routers/<name>.py`에 위치
2. Pydantic v2 모델 사용
3. 라이선스/설정 데이터 저장 경로:
   - Windows: `%APPDATA%/BookEngine/settings.json`
   - 코드: `Path.home() / "AppData" / "Roaming" / "BookEngine" / "settings.json"`
4. `engine_core/`는 읽기 전용 import만 허용, 파일 수정 절대 금지
5. 새 라우터는 `main.py`에 `app.include_router(...)` 등록 필수

## P10 신규 엔드포인트
```
POST /engine/license/validate  — 라이선스 키 검증 (로컬 HMAC 검증)
GET  /engine/license/status    — 현재 라이선스 상태
GET  /engine/settings          — 앱 설정 조회 (API 키 포함)
PUT  /engine/settings          — 앱 설정 저장
```

## 라이선스 로컬 검증 방식
- 오프라인 검증: HMAC-SHA256 기반
- 시크릿 키는 앱 빌드 시 환경변수로 주입
- 라이선스 키 형식: `BKENG-XXXXX-XXXXX-XXXXX-XXXXX` (25자)
- 무료 체험: `BKENG-TRIAL-00000-00000-00000` 허용

## 금지 사항
- `engine_core/` 파일 수정
- `platform/` 파일 수정
- 외부 인증 서버 의존 (완전 오프라인 동작 필수)
- 라이선스 키를 평문으로 로그 출력
