# 다중 인증 6자리를 크롬의 ERP 인증 화면에 쳐 넣고 [인증] 을 누른다 — **사용자가 직접 실행하는 명령**이다(윈도우 판).
#
#   ! powershell -ExecutionPolicy Bypass -File skills\stay-setup-run\scripts\mfa_type.ps1 123456
#   ! powershell -ExecutionPolicy Bypass -File skills\stay-setup-run\scripts\mfa_type.ps1 123456 https://<ERP 주소>/accounts/login/mfa/
#
# Claude Code / Codex 입력창에서 `!` 로 시작하면 세션 셸에서 실행된다 — 에이전트는 이 스크립트를 실행하지도,
# 코드를 대신 넣지도 않는다(SKILL.md "로그인 넘김"). 인증 화면 주소는 둘째 인자 또는 환경변수
# STAY_ERP_MFA_URL 로 준다(저장소에는 주소를 적지 않는다).
#
# 실행 정책: 서명 없는 스크립트는 기본 정책에서 막히므로 위처럼 `-ExecutionPolicy Bypass -File` 을 붙여 부른다
# (정책 자체를 바꾸지 않는다). 리눅스·맥은 같은 규약의 mfa_type.sh 를 쓴다.
#
# 하는 일: 크롬으로 인증 주소를 열고 3초 기다린 뒤 크롬 창을 앞으로 → 첫 입력칸(코드칸)으로 Tab → 숫자 → Enter.
# 코드는 30초마다 바뀌므로 인증앱에 보이는 숫자를 바로 넣는다.

param(
  [string]$Code,
  [string]$Url
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($Url)) { $Url = $env:STAY_ERP_MFA_URL }

if ($Code -notmatch '^[0-9]{6}$') {
  Write-Error "사용법: mfa_type.ps1 <6자리 숫자> [인증 화면 주소]"
  exit 2
}
if ([string]::IsNullOrWhiteSpace($Url)) {
  Write-Error "인증 화면 주소가 없다 — 둘째 인자로 주거나 STAY_ERP_MFA_URL 을 설정한다"
  exit 2
}

try {
  Start-Process chrome $Url
} catch {
  Write-Error "크롬을 열지 못했다 — Chrome 이 설치돼 있고 chrome 이 PATH 에 있는지 확인한다 ($($_.Exception.Message))"
  exit 3
}

Start-Sleep -Seconds 3

$shell = New-Object -ComObject WScript.Shell

$activated = $false
foreach ($p in Get-Process | Where-Object { $_.MainWindowTitle -like '*Chrome*' }) {
  if ($shell.AppActivate($p.Id)) { $activated = $true; break }
}
if (-not $activated) { $activated = $shell.AppActivate('Chrome') }
if (-not $activated) {
  Write-Error "크롬 창을 앞으로 올리지 못했다 — 크롬 창이 최소화돼 있지 않은지, 다른 창이 전체화면을 잡고 있지 않은지 확인한다"
  exit 4
}

Start-Sleep -Milliseconds 500
$shell.SendKeys('{TAB}')      # 인증 화면의 첫 입력칸이 코드칸이다
Start-Sleep -Milliseconds 200
$shell.SendKeys($Code)
Start-Sleep -Milliseconds 200
$shell.SendKeys('{ENTER}')

Write-Output "인증 화면에 코드를 넣고 [인증] 을 눌렀다 — 호텔 목록이 뜨는지 크롬에서 확인한다"
