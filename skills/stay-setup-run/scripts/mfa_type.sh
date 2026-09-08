#!/usr/bin/env bash
# 다중 인증 6자리를 크롬의 ERP 인증 화면에 쳐 넣고 [인증] 을 누른다 — **사용자가 직접 실행하는 명령**이다.
#
#   ! bash skills/stay-setup-run/scripts/mfa_type.sh 123456
#   ! bash skills/stay-setup-run/scripts/mfa_type.sh 123456 https://<다른 ERP 주소>/accounts/login/mfa/
#
# Claude Code / Codex 입력창에서 `!` 로 시작하면 세션 셸에서 실행된다 — 에이전트는 이 스크립트를 실행하지도,
# 코드를 대신 넣지도 않는다(SKILL.md "로그인 넘김"). 인증 화면 주소는 둘째 인자 또는 환경변수
# STAY_ERP_MFA_URL 로 준다. 둘 다 없으면 운영 ERP(https://basecamp.team/accounts/login/mfa/)다.
#
# 이 파일은 리눅스(X11 + xdotool)와 맥(osascript)을 함께 다룬다 — `uname` 이 Darwin 이면 맥 경로로 간다.
# 윈도우는 같은 규약의 PowerShell 판이 옆에 있다:
#   ! powershell -ExecutionPolicy Bypass -File skills\stay-setup-run\scripts\mfa_type.ps1 123456 <주소>
#
# 하는 일: 보이는 크롬 창을 앞으로 → 주소창(맥은 앞 창의 탭)에 인증 화면 주소 → 열리면 첫 입력칸(코드칸)으로
# Tab → 숫자 → Enter. 코드는 30초마다 바뀌므로 인증앱에 보이는 숫자를 바로 넣는다.
set -euo pipefail

code="${1:-}"
url="${2:-${STAY_ERP_MFA_URL:-https://basecamp.team/accounts/login/mfa/}}"

if [[ ! "$code" =~ ^[0-9]{6}$ ]]; then
  echo "사용법: mfa_type.sh <6자리 숫자> [인증 화면 주소]" >&2; exit 2
fi
if [[ -z "$url" ]]; then
  echo "인증 화면 주소가 없다 — 둘째 인자로 주거나 STAY_ERP_MFA_URL 을 설정한다" >&2; exit 2
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  # ── 맥: osascript 로 크롬을 앞으로 올리고 앞 창의 탭을 인증 주소로 바꾼 뒤 키를 보낸다 ──────────
  if ! command -v osascript >/dev/null; then
    echo "osascript 가 없다 — 맥 기본 도구이니 맥이 아니면 리눅스/윈도우 판을 쓴다" >&2; exit 3
  fi
  if ! osascript <<OSA
tell application "Google Chrome"
  activate
  if (count of windows) is 0 then
    make new window
  end if
  set URL of active tab of front window to "$url"
end tell
delay 3
tell application "System Events"
  tell process "Google Chrome"
    keystroke tab          -- 인증 화면의 첫 입력칸이 코드칸이다
    keystroke "$code"
    keystroke return
  end tell
end tell
OSA
  then
    echo "osascript 가 실패했다 — 첫 실행이면 권한이 없어서다." >&2
    echo "  시스템 환경설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에서 이 명령을 실행한 터미널" >&2
    echo "  (터미널.app / iTerm / Claude Code 를 띄운 앱)을 켜 준 뒤 다시 실행한다." >&2
    echo "  같은 창의 '자동화' 항목에서 Google Chrome·시스템 이벤트 제어도 허용해야 한다." >&2
    exit 3
  fi
else
  # ── 리눅스: X11 + xdotool ────────────────────────────────────────────────────────────────
  if ! command -v xdotool >/dev/null; then
    echo "xdotool 이 없다 (sudo pacman -S xdotool / sudo apt install xdotool). Wayland 이면 X11 세션에서 실행한다" >&2; exit 3
  fi

  win="$(xdotool search --onlyvisible --class chrom | head -1 || true)"
  if [[ -z "$win" ]]; then echo "보이는 크롬 창이 없다 — 크롬을 먼저 연다" >&2; exit 4; fi

  xdotool windowactivate --sync "$win"
  sleep 0.3
  xdotool key --clearmodifiers ctrl+l
  sleep 0.2
  xdotool type --delay 20 "$url"
  xdotool key Return
  sleep 3
  xdotool key Tab            # 인증 화면의 첫 입력칸이 코드칸이다
  xdotool type --delay 40 "$code"
  xdotool key Return
fi

echo "인증 화면에 코드를 넣고 [인증] 을 눌렀다 — 호텔 목록이 뜨는지 크롬에서 확인한다"
