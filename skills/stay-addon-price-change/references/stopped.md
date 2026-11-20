# 중간에 멈춘 변경

적용하다 저장이 실패했을 때(`saved: false`), 저장됐는지 모를 때(`saved: "unknown"`), 15분 동안 아무 일이 없었을 때(세션이 끊김), 담당자가 "N번 이어서"라고 할 때, 「준비」 4 에서 알린 멈춘 변경을 보자고 할 때 이대로 한다. 다시 읽어 `check` 가 이어서 해도 된다고 하기 전에는 이어서 하지 않는다. 같은 저장을 두 번 누르지 않는다.

1. `read-calls --record N` 으로 읽기(SKILL.md 「읽기」) → S.
2. `python3 scripts/addon_change.py check --change N --snapshot "<S>"`.
   - `cause` 는 멈춘 까닭 — `failed` 저장이 실패함 · `unknown` 저장 단추는 눌렸고 저장됐는지 모름(읽은 값으로 가려 장부에 적는다) · `cut_off` 실패 없이 끊김(15분 동안 아무 일이 없었다).
   - `last_saved` · `next` 는 마지막으로 저장된 단계와 다음 단계, `why` 는 이어서 할 수 없는 까닭(줄마다).
3. `python3 scripts/addon_change.py render result --change N` → `page` 를 열고 고를 것을 한 번만 묻는다.
   - `can_continue: true` 면 "이어서 · 된 것까지 되돌리기 · 이대로 두기". **이어서** 는 15분 안에 `calls --change N` 부터 SKILL.md 「적용하기」 2 를 한다(그보다 늦으면 1 부터 다시).
   - `can_continue: false` 면 `why` 를 말하고 "된 것까지 되돌리기 · 이대로 두기" 가운데 고르게 한다. 남은 줄은 새 미리보기로 다시 바꾼다.
   - **된 것까지 되돌리기** 는 SKILL.md 「3. 되돌리기」의 1 부터(번호 N).
   - **이대로 두기** 는 아무것도 하지 않는다. 장부에 멈춘 채로 남아 다음에 이어서 볼 수 있다.
