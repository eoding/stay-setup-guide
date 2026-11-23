"""말끝 조사 — 네 도우미가 같이 쓴다. 담당자에게 읽어 주는 줄은 「이(가)」 · 「(으)로」처럼 둘을 다 적지 않고, 앞 낱말의 끝소리로
하나를 고른다(시운전 10 — 「취소 조건이(가)」 · 「할인 값 14 으로」를 그대로 읽어 주었다).

    josa("취소 조건", "이가")   → "취소 조건이"
    josa("14", "으로")          → "14로"      (사 — 받침 없음)
    josa("16", "으로")          → "16으로"    (육 — 받침 ㄱ)
    josa("350.00 USD", "으로")  → "350.00 USD로"

끝 글자가 한글이면 그 받침으로, 숫자면 그 숫자를 읽는 소리(영 · 일 · 이 · 삼 · 사 · 오 · 육 · 칠 · 팔 · 구 — 10 · 100 같은 끝 0 도
「십 · 백 · 천 · 만」이 모두 받침이 있어 0 과 같다)로, `%` 는 「퍼센트」로, 로마자는 그 글자 이름(엘 · 엠 · 엔 · 알만 받침)으로 고른다.
그 밖의 글자(괄호 · 따옴표 따위)는 건너뛰고 그 앞 글자를 본다. 고를 수 없으면 둘을 다 적는다.
"""

from __future__ import annotations

PAIRS = {"이가": ("이", "가"), "은는": ("은", "는"), "을를": ("을", "를"), "과와": ("과", "와"), "으로": ("으로", "로")}
DIGIT_FINAL = {"0": "ㅇ", "1": "ㄹ", "2": "", "3": "ㅁ", "4": "", "5": "", "6": "ㄱ", "7": "ㄹ", "8": "ㄹ", "9": ""}
LATIN_FINAL = {"l": "ㄹ", "m": "ㅁ", "n": "ㄴ", "r": "ㄹ"}
SKIP = " )]}」』'\"”’."
FINALS = ("", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
          "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ")


def final_sound(word: str) -> str | None:
    """낱말 끝소리의 받침 — 받침이 없으면 빈 글자, 알 수 없으면 None."""
    for char in reversed(word):
        if char in SKIP:
            continue
        if "가" <= char <= "힣":
            return FINALS[(ord(char) - ord("가")) % 28]
        if char in DIGIT_FINAL:
            return DIGIT_FINAL[char]
        if char == "%":
            return ""   # 퍼센트
        if char.isascii() and char.isalpha():
            return LATIN_FINAL.get(char.lower(), "")
        return None
    return None


def josa(word: str, kind: str) -> str:
    """`word` 에 조사를 붙인다 — `kind` 는 이가 · 은는 · 을를 · 과와 · 으로. 「으로」는 받침 ㄹ 뒤에서도 「로」다."""
    with_final, without = PAIRS[kind]
    final = final_sound(word)
    if final is None:
        return f"{word}{with_final}({without})" if kind != "으로" else f"{word}(으)로"
    if kind == "으로":
        return word + ("로" if final in ("", "ㄹ") else "으로")
    return word + (with_final if final else without)
