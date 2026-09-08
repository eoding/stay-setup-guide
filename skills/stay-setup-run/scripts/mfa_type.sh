#!/usr/bin/env bash
# 다중 인증 6자리를 크롬의 ERP 인증 화면에 쳐 넣고 [인증] 을 누른다 — **사용자가 직접 실행하는 명령**이다.
#
#   ! bash skills/stay-setup-run/scripts/mfa_type.sh 123456
#   ! bash skills/stay-setup-run/scripts/mfa_type.sh 123456 https://<ERP 주소>/accounts/login/mfa/
#
# Claude Code / Codex 입력창에서 `!` 로 시작하면 세션 셸에서 실행된다 — 에이전트는 이 스크립트를 실행하지도,
# 코드를 대신 넣지도 않는다(SKILL.md "로그인 넘김"). 인증 화면 주소는 둘째 인자 또는 환경변수
# STAY_ERP_MFA_URL 로 준다(저장소에는 주소를 적지 않는다). 리눅스 X11 + xdotool 기준이다.
#
# 하는 일: 보이는 크롬 창을 앞으로 → 주소창에 인증 화면 주소 → 열리면 첫 입력칸(코드칸)으로 Tab → 숫자 → Enter.
# 코드는 30초마다 바뀌므로 인증앱에 보이는 숫자를 바로 넣는다.
set -euo pipefail

code="${1:-}"
url="${2:-${STAY_ERP_MFA_URL:-}}"

if [[ ! "$code" =~ ^[0-9]{6}$ ]]; then
  echo "사용법: mfa_type.sh <6자리 숫자> [인증 화면 주소]" >&2; exit 2
fi
if [[ -z "$url" ]]; then
  echo "인증 화면 주소가 없다 — 둘째 인자로 주거나 STAY_ERP_MFA_URL 을 설정한다" >&2; exit 2
fi
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
echo "인증 화면에 코드를 넣고 [인증] 을 눌렀다 — 호텔 목록이 뜨는지 크롬에서 확인한다"
