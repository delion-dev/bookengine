# WinError 10013 ALYac / Firewall Checklist

이 문서는 Vertex live call 중 발생하는 `WinError 10013`를
`ALYac`, `Windows Defender Firewall`, 실행 컨텍스트 관점에서 점검하기 위한 운영 체크리스트다.

## 현재 관찰된 사실

1. `engine.runtime.diagnose` 기준 `express + api_key` 모델 게이트웨이 설정은 유효하다.
2. `aiplatform.googleapis.com` DNS 해석은 정상이다.
3. `WinHTTP` 프록시는 `Direct access` 상태다.
4. 사용자 `WinINet` 프록시는 비활성 상태다.
5. 동일 머신에서 동일 엔드포인트가 어떤 시점에는 성공하고 어떤 시점에는 `WinError 10013`으로 실패한다.
6. 활성 보안 제품으로 `알약(ALYac)`과 `Windows Defender`가 등록되어 있다.

## 이번 점검에 쓰는 경로

1. Python: `C:\Users\Daddy\AppData\Local\Programs\Python\Python314\python.exe`
2. PowerShell 7: `C:\Program Files\PowerShell\7\pwsh.exe`
3. 보안 제품: `C:\Program Files\ESTsoft\ALYac\AYRunSC.exe`
4. 대상 호스트: `aiplatform.googleapis.com`
5. 대상 포트: `443`

## 표준 재현 명령

```powershell
python tools\core_engine_cli.py diagnose-runtime --with-live-probes --with-grounded-probe
```

판정 기준:

1. `plain_text_probe`와 `grounded_research_probe`가 모두 `ok=true`이면 현재 실행 컨텍스트는 통신 가능 상태다.
2. 둘 다 `WinError 10013`이면 로컬 소켓/보안 정책 문제 가능성이 높다.
3. `plain_text_probe`만 성공하고 `grounded_research_probe`만 실패하면 timeout, quota, 검색 도구 경로를 추가 점검한다.

## ALYac 점검 순서

1. 알약을 관리자 권한으로 연다.
2. 최근 차단 기록, 네트워크 차단 기록, 방화벽 기록, 행위 차단 기록 중 하나라도 보이는 메뉴를 먼저 연다.
3. 시간 범위를 `WinError 10013` 발생 시각 전후 5분으로 맞춘다.
4. `python.exe`, `pwsh.exe`, `aiplatform.googleapis.com`, `443`, `ESTsoft`, `PowerShell`, `Python` 키워드로 검색한다.
5. `차단`, `격리`, `행위 차단`, `네트워크 보호`, `의심 연결 차단` 류 이벤트가 있으면 세부 이유를 기록한다.
6. `python.exe`가 차단되어 있으면 신뢰 프로그램 또는 예외 목록에 추가한다.
7. `pwsh.exe`가 차단되어 있으면 신뢰 프로그램 또는 예외 목록에 추가한다.
8. 도메인/FQDN 허용이 가능하면 `aiplatform.googleapis.com`을 허용 목록에 추가한다.
9. 포트 단위 정책이 있으면 `443` outbound를 허용한다.
10. 적용 후 알약 보호 엔진을 재시작하거나 PC를 재부팅한다.

알약 UI 명칭은 버전에 따라 다를 수 있다. 보통 `예외`, `허용 목록`, `신뢰`, `방화벽`, `네트워크 보호`, `행위 차단` 계열 메뉴를 찾으면 된다.

## Windows Defender Firewall 점검 순서

1. 관리자 권한으로 `wf.msc`를 연다.
2. `Outbound Rules`에서 `python.exe` 또는 `pwsh.exe`에 대한 명시적 `Block` 규칙이 있는지 먼저 찾는다.
3. 있으면 규칙 이름, 방향, 프로필, 프로그램 경로를 기록한다.
4. 조직 정책 때문에 삭제가 어렵다면 동일 프로그램 경로에 대해 더 구체적인 `Allow` 규칙을 추가한다.
5. `Outbound Rules`에 아래 두 규칙을 만든다.
6. 규칙 1: Program = `C:\Users\Daddy\AppData\Local\Programs\Python\Python314\python.exe`, Action = `Allow`, Direction = `Outbound`, Protocol = `TCP`, Remote Port = `443`
7. 규칙 2: Program = `C:\Program Files\PowerShell\7\pwsh.exe`, Action = `Allow`, Direction = `Outbound`, Protocol = `TCP`, Remote Port = `443`
8. 프로필은 우선 현재 사용 중인 프로필만 체크하고, 모르면 `Domain`, `Private`, `Public` 모두 임시 허용 후 재검증한다.
9. 필요하면 원격 주소를 `aiplatform.googleapis.com` 해석 IP 대역으로 더 좁힌다.
10. 설정 후 동일 진단 명령을 다시 실행한다.

## 관리자 PowerShell로 만드는 예시 규칙

```powershell
New-NetFirewallRule -DisplayName "Allow Python314 Vertex Outbound" `
  -Direction Outbound `
  -Action Allow `
  -Program "C:\Users\Daddy\AppData\Local\Programs\Python\Python314\python.exe" `
  -Protocol TCP `
  -RemotePort 443

New-NetFirewallRule -DisplayName "Allow Pwsh7 Vertex Outbound" `
  -Direction Outbound `
  -Action Allow `
  -Program "C:\Program Files\PowerShell\7\pwsh.exe" `
  -Protocol TCP `
  -RemotePort 443
```

## 재검증 순서

1. `python tools\core_engine_cli.py diagnose-runtime --with-live-probes --with-grounded-probe` 실행
2. `vertex_auth_probe.ok == true` 확인
3. `plain_text_probe.ok == true` 확인
4. `grounded_research_probe.ok == true` 확인
5. `assessment_notes`에 현재 실행 컨텍스트 성공 메시지가 들어갔는지 확인

## 실패 시 다음 분기

1. ALYac 차단 로그가 있으면 ALYac 정책이 1순위 원인이다.
2. ALYac 로그가 없고 Firewall 규칙 변경 후에도 동일하면 Windows 보안 정책 또는 기업용 보안 제품 추가 개입을 의심한다.
3. `10013`은 사라졌지만 `timeout`만 남으면 소켓 권한 문제는 해소된 것이고, 이후에는 모델 timeout / pacing / retry 정책을 조정한다.
4. unrestricted 실행만 성공하고 일반 실행만 실패하면 실행 컨텍스트 차이, 보안 제품의 프로세스 신뢰도, 또는 샌드박스 정책 차이를 우선 본다.

## 롤백

1. 임시로 만든 Firewall Allow 규칙은 이름 기준으로 삭제한다.
2. ALYac에 추가한 예외는 테스트 종료 후 유지 여부를 보안 정책에 맞게 결정한다.

## 참고 링크

1. Microsoft Windows Firewall Rules: https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules
2. Microsoft Configure Firewall Rules: https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/configure
3. Microsoft netsh advfirewall: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/netsh-advfirewall
