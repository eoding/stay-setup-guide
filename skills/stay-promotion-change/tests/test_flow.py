"""명령으로 한 바퀴(M1~M6) — 페이지 답은 promotion_scene 의 작은 ERP 가 만든다(진짜 페이지 모듈의 답과 같은 모양, test_golden).

모양 다섯: 연박 두 단 할인율(9002), 상시 정액(9003), 연박 무료 숙박(9004), 전 오퍼 공통 카드의 상시 할인율(9006, 진행기간 제한 켜짐),
단마다 화면 밖 설정(취소 조건)이 붙은 얼리버드(9005). 다섯 모두 읽기 → 바꾸기 → 미리보기 → 적용 직전 다시 읽기 → begin → 저장 →
다시 읽어 견주기 → 되돌리기 → 견주기 → 되돌리기를 되돌리기 → 견주기. 그리고 표식 없는 ERP(읽고 미리보기만), 그 길에서 벗어나는 때.

    python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import promotion_scene as scene

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "promotion_change.py"
CHARGE_SCRIPT = SKILL.parent / "stay-charge-change" / "scripts" / "charge_change.py"

LONG_STAY = {"offer": "601", "promotion": "9002", "tier": "2"}
FLAT = {"offer": "601", "promotion": "9003", "tier": "0"}
FREE = {"offer": "601", "promotion": "9004", "tier": "4"}
EARLY_NRF = {"offer": "601", "promotion": "9005", "tier": "46"}
COMMON = {"offer": "0", "promotion": "9006", "tier": "0"}
GATE = "이 ERP 는 아직 프로모션을 화면으로 저장하면 화면에 안 보이는 설정이 지워질 수 있어, 도우미가 저장하지 않습니다 — ERP 가 고쳐진 뒤에 됩니다"
ORIGIN_UNKNOWN = ("이 프로모션의 편집 창은 ERP 가 할인 단 줄이 어느 저장된 단에서 왔는지 모르는 상태라(앞선 저장이 거절된 뒤 다시 "
                  "그려진 창), 저장하면 화면에 안 보이는 설정이 다른 단에 붙거나 빠질 수 있어 도우미가 저장하지 않습니다 — ERP 에서 그 "
                  "프로모션의 편집 창을 닫았다가 다시 열어 주시면 다시 해 보겠습니다")


class Flow(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.work = Path(self.folder.name) / "작업"
        self.work.mkdir()
        self.env = dict(os.environ, STAY_PRICE_LEDGER_DIR=str(Path(self.folder.name) / "기록"))
        self.erp = scene.Erp()
        self.readings = 0
        self.names = 0

    def tearDown(self):
        self.folder.cleanup()

    def cli(self, *args, script=SCRIPT, code=0):
        """명령 하나 — 장부의 시계는 작은 ERP 의 시계(마지막 답의 끝난 시각)에 서 있다."""
        env = dict(self.env, STAY_PRICE_TEST_NOW=self.erp.clock.isoformat())
        done = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, code, f"{args[0]}: {done.stderr or done.stdout}")
        return json.loads(done.stdout) if code in (0, 1) else json.loads(done.stderr)

    def file(self, name, data) -> Path:
        path = self.work / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def request(self, *tiers, sentence="바꿔줘", **change) -> Path:
        self.names += 1
        return self.file(f"request-{self.names}.json", dict(kind="promotion_change", hotel=scene.HOTEL, tiers=list(tiers),
                                                             sentence=sentence, **change))

    def read(self, **scope) -> Path:
        """읽기 한 번 — read-calls → 프로모션마다 readPromotion 답 → read. 지금 값 파일의 자리를 돌려준다."""
        self.readings += 1
        folder = self.work / f"읽기-{self.readings}"
        folder.mkdir()
        flags = (["--record", scope["record"]] if "record" in scope else ["--all", "--look", self.look()] if scope.get("all")
                 else ["--request", scope["request"]])
        self.cli("read-calls", *flags, "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["promotions"]
        scene.write_answers(folder, "promotion", [self.erp.read_promotion(call) for call in calls])
        self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        return folder / "snapshot.json"

    def look(self) -> Path:
        if not (self.work / "look.json").exists():
            scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
            self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        return self.work / "look.json"

    def listed(self, *flags) -> dict:
        return {entry["id"]: entry for entry in self.cli("list", "--look", self.look(), *flags)["changes"]}

    def preview(self, request, name="plan-1.json", **extra) -> tuple[int, Path, dict]:
        snapshot = self.read(request=request)
        plan = self.work / name
        flags = [item for pair in extra.items() for item in (f"--{pair[0]}", pair[1])]
        short = self.cli("plan", "--snapshot", snapshot, "--request", request, "--record", *flags, "--out", plan)
        return short["change_id"], plan, short

    def apply(self, change, plan, outcome=True) -> list[dict]:
        begun = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        self.assertEqual(begun["status"], "applying", begun)
        results = []
        for call in self.cli("calls", "--change", change)["calls"]:
            answer = self.erp.apply(call["payload"], outcome)
            results.append(self.cli("record-result", "--change", change, "--result",
                                    self.file(f"적용-{change}-{call['no']}.json", answer)))
        return results

    def verified(self, change):
        result = self.cli("verify", "--change", change, "--snapshot", self.read(record=change))
        self.assertEqual((result["same"], result["mismatches"], result["moved"]), (True, [], []), result)

    def roll_back(self, change, name) -> int:
        out = self.work / name
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                            "--sentence", "방금 것 되돌려", "--out", out)
        self.assertEqual((rollback["kept"], rollback["restored"]), (0, rollback["saves"]), rollback)
        back = rollback["change_id"]
        self.assertEqual([item["saved"] for item in self.apply(back, out)], [True] * rollback["saves"])
        self.verified(back)
        return back

    def round_trip(self, request, plan_flags=None):
        """미리보기 → 적용 → 견주기 → 되돌리기 → 견주기 → 되돌리기를 되돌리기 → 견주기. 장부 번호 · 계산 파일 · 저장 요청들을 돌려준다."""
        change, plan, short = self.preview(request, **(plan_flags or {}))
        before = scene.copy.deepcopy(self.erp.data)
        results = self.apply(change, plan)
        self.assertEqual([item["saved"] for item in results], [True] * len(results))
        after = scene.copy.deepcopy(self.erp.data)
        posts = list(self.erp.posts)
        self.verified(change)
        back = self.roll_back(change, f"rollback-{change}.json")
        self.assertEqual(self.erp.data, before, "되돌린 뒤 저장된 값이 처음과 같다(화면 밖 설정 · 저장된 표기까지)")
        again = self.roll_back(back, f"rollback-{back}.json")
        self.assertEqual(self.erp.data, after, "되돌리기를 되돌리면 도우미가 넣었던 값으로 돌아간다")
        lines = self.listed()
        self.assertEqual((lines[again]["status"], lines[change]["status"]), ("applied", "applied"),
                         "되돌리기를 되돌리면 처음 변경이 다시 적용된 것으로 읽힌다")
        self.assertIn(f"되돌렸다가 다시 살림", lines[change]["scope"])
        self.assertIn(f"장부 {back}번 · {again}번", lines[change]["scope"])
        return change, plan, posts, short


def replaced(form, edits):
    """form 에서 짚은 (이름, 몇 번째) 칸만 바꾼 목록 — 저장 요청이 꼭 이것이어야 한다."""
    seen, out = {}, []
    for name, value in form:
        nth = seen.get(name, 0)
        seen[name] = nth + 1
        out.append([name, edits.get((name, nth), value)])
    return out


def form(promotion_id, keeps=True):
    erp = scene.Erp()
    card, promotion = next((c, p) for c, ps in erp.cards() for p in ps if p["id"] == promotion_id)
    return scene.form_of(card, promotion, keeps)


class FiveShapesTest(Flow):
    def test_m1_look_lists_every_promotion_per_card_with_the_common_card_and_presses_nothing_that_saves(self):
        scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
        look = self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        self.assertEqual((look["offers"], look["promotions"]), (3, 6))
        common = next(item for item in look["items"] if item["promotion"] == "9006")
        self.assertEqual((common["offer"], common["offer_name"], common["trigger"], common["benefit"]),
                         ("0", "전 오퍼 공통", "상시 · 조건 없이 항상", ["5%"]))
        early = next(item for item in look["items"] if item["promotion"] == "9005")
        self.assertEqual(early["benefit"][:2], ["체크인 D-N일 전 46 → 15.0%", "체크인 D-N일 전 31 → 10.0%"])
        self.assertEqual(self.erp.posts, [], "읽기는 저장을 누르지 않는다")
        page = self.cli("render", "prices", "--look", self.work / "look.json", "--text")["text"]
        for words in ("전 오퍼 공통", "롱스테이 2박 7% / 3박 10%", "예약일 2026-11-01 ~ 2027-02-28", "배타 그룹 DEMO-ALL"):
            self.assertIn(words, page)

    def test_m1_one_promotion_s_whole_window_shows_every_setting_it_keeps_and_the_off_form_names(self):
        look = self.look()
        folder = self.work / "읽기-설정"
        folder.mkdir()
        self.cli("read-calls", "--promotion", "9005", "--promotion", "9007", "--look", look, "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["promotions"]
        scene.write_answers(folder, "promotion", [self.erp.read_promotion(call) for call in calls])
        self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        text = self.cli("render", "window", "--snapshot", folder / "snapshot.json", "--text")["text"]
        for words in ("체크인 46일 전 단", "취소 조건", "연말 성수기", "디럭스 · 조식 포함", "7일 전까지 무료 취소",
                      "2026-12-20 ~ 2027-01-05", "도우미가 저장할 수 있습니다"):
            self.assertIn(words, text)
        self.assertEqual(self.erp.posts, [])

    def test_a_two_tier_percentage_by_nights_changes_one_tier_and_sends_the_other_as_read(self):
        _change, _plan, posts, short = self.round_trip(self.request(LONG_STAY, value="8", sentence="롱스테이 2박 8% 로"))
        self.assertEqual(posts[0], replaced(form("9002"), {("tiers_value", 0): "8"}))
        self.assertIn("할인이 커져", short["guest"])
        self.assertEqual(self.erp.promotion("9002")["trigger"]["tiers"][1], {"threshold": 3, "pct": "10"})

    def test_an_always_on_flat_discount_changes_by_an_amount_in_the_hotel_currency(self):
        _change, plan, posts, _short = self.round_trip(self.request(FLAT, amount="5", sentence="정액 20달러 할인을 25달러로"))
        self.assertEqual(posts[0], replaced(form("9003"), {("tiers_value", 0): "25"}))
        self.assertEqual(json.loads(plan.read_text(encoding="utf-8"))["plan"]["changes"][0]["after"], "25")

    def test_free_nights_go_from_one_to_two_after_the_red_line_is_chosen(self):
        change, plan, short = self.preview(self.request(FREE, value="2", sentence="연박 무료 1박을 2박으로"))
        self.assertEqual((short["saves"], [line["rule"] for line in short["red"]]), (None, ["OVER_30"]))
        choose = self.file("choose.json", [{"rule": "OVER_30", "choice": "include", "tiers": ["9004 4"], "said": "2박 맞아요"}])
        snapshot = self.work / "읽기-1" / "snapshot.json"
        again = self.cli("plan", "--snapshot", snapshot, "--request", self.work / "request-1.json", "--resolutions", choose,
                         "--record", "--replaces", change, "--out", self.work / "plan-2.json")
        self.assertEqual(again["saves"], 1)
        self.apply(again["change_id"], self.work / "plan-2.json")
        self.assertEqual(self.erp.posts[-1], replaced(form("9004"), {("tiers_value", 0): "2"}))
        self.assertEqual(self.erp.promotion("9004")["trigger"]["tiers"], [{"threshold": 4, "free_nights": 2}])
        self.verified(again["change_id"])

    def test_a_promotion_common_to_all_offers_keeps_its_booking_period_switch_on(self):
        _change, _plan, posts, _short = self.round_trip(self.request(COMMON, value="6", sentence="전 오퍼 공통 할인 6% 로"))
        self.assertEqual(posts[0], replaced(form("9006"), {("tiers_value", 0): "6"}))
        self.assertIn(["promotion_apply_flag", "on"], posts[0], "진행기간 제한은 창이 보인 그대로 켜진 채 간다")
        self.assertIn(["combinability", "on"], posts[0])

    def test_a_tier_carrying_off_form_keys_keeps_them_and_the_preview_says_so(self):
        _change, _plan, posts, short = self.round_trip(self.request(EARLY_NRF, value="16", sentence="얼리버드 46일 16% 로"))
        self.assertEqual(posts[0], replaced(form("9005"), {("tiers_value", 0): "16"}))
        self.assertEqual(short["off"], ["체크인 46일 전 단: 이 단에는 화면에 안 보이는 취소 조건이 붙어 있습니다 — 그대로 둡니다.",
                                        "체크인 31일 전 단: 이 단에는 화면에 안 보이는 취소 조건이 붙어 있습니다 — 그대로 둡니다."])
        tiers = self.erp.promotion("9005")["trigger"]["tiers"]
        self.assertEqual(tiers[1], {"threshold": 31, "pct": "10.0", "cancellation": "CUTOFF_AT_THRESHOLD"}, "건드리지 않은 단은 표기까지 그대로")

    def test_w4_the_tier_sent_as_read_is_counted_and_the_off_settings_read_the_same_after_the_save(self):
        """W4 (시운전 10) — 짚지 않아 그대로 보내는 단을 짧은 답이 센다(`counts.sent`). 저장 뒤 verify 가 견준 것에서 화면 밖 설정이
        그대로라고 말한다(`kept`) — 결과 페이지도. 되돌리기 미리보기에는 「통화 .」가 없고, 되돌리기 결과는 되돌린 할인이라고 한다."""
        change, plan, short = self.preview(self.request(EARLY_NRF, value="16", sentence="얼리버드 46일 16% 로"))
        self.assertEqual((short["counts"]["will_change"], short["counts"]["unchanged"], short["counts"]["sent"]), (1, 0, 1))
        self.assertIn("1 짚지 않아 그대로 보내는 단", self.cli("render", "preview", "--plan", plan, "--text")["text"])
        self.apply(change, plan)
        after = self.read(record=change)
        verified = self.cli("verify", "--change", change, "--snapshot", after)
        kept = ["체크인 46일 전 단: 화면에 안 보이는 취소 조건은 저장 뒤에도 그대로입니다.",
                "체크인 31일 전 단: 화면에 안 보이는 취소 조건은 저장 뒤에도 그대로입니다."]
        self.assertEqual((verified["same"], verified["kept"]), (True, kept))
        result = self.cli("render", "result", "--change", change, "--snapshot", after, "--text")["text"]
        for sentence in kept:
            self.assertIn(sentence, result)
        out = self.work / "rollback-1.json"
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record", "--out", out)
        page = self.cli("render", "rollback", "--plan", out, "--text")["text"]
        self.assertNotIn("통화 .", page)
        self.assertIn("에 ERP 에서 읽은 것입니다.", page)
        self.apply(rollback["change_id"], out)
        undone = self.cli("render", "result", "--change", rollback["change_id"], "--snapshot", self.read(record=rollback["change_id"]),
                          "--text")["text"]
        self.assertIn("되돌린 할인 값은 저장 뒤 새 견적부터 붙습니다", undone)
        self.assertNotIn("새 할인으로 바뀝니다", undone)


class LadderFlowTest(Flow):
    """P4 (리뷰 2 · 파이썬 4) — 2박 7% · 3박 10% 를 둘 다 5% 포인트 올리면(12 · 15) 둘 다 30% 빨간 줄이고 뒤집힘은 없다. 2박은 「이대로
    바꿈」, 3박은 「안 바꿈」을 고르면 2박 12% · 3박 10% 가 되어 3박 손님이 덜 할인받는다 — 다시 계산하면 그것이 2박 단의 새 빨간 줄
    (INVERTS)이고, 저장되면 단마다 값(`ladder`)을 싣는다. 고를 때까지 저장 단계가 없고, 「이대로 바꿈」을 고르면 2박 단만 저장한다."""

    def test_keeping_one_tier_and_including_another_is_asked_again_as_an_inverted_ladder(self):
        request = self.request(LONG_STAY, dict(LONG_STAY, tier="3"), amount="5", sentence="롱스테이 둘 다 5% 포인트 올려")
        change, _plan, short = self.preview(request)
        self.assertEqual([(line["rule"], line["tiers"]) for line in short["red"]], [("OVER_30", 2)])
        snapshot = self.work / "읽기-1" / "snapshot.json"
        said = [{"rule": "OVER_30", "choice": "include", "tiers": ["9002 2"], "said": "2박은 올려"},
                {"rule": "OVER_30", "choice": "keep", "tiers": ["9002 3"], "said": "3박은 그대로 둬"}]
        again = self.cli("plan", "--snapshot", snapshot, "--request", request, "--resolutions", self.file("choices-2.json", said),
                         "--record", "--replaces", change, "--out", self.work / "plan-2.json")
        self.assertEqual((again["saves"], again["counts"]["red"], again["counts"]["INVERTS"]), (None, 1, 1))
        self.assertEqual(again["red"], [{
            "rule": "INVERTS", "label": "기준값이 더 큰 단보다 할인이 커집니다(작으면 작아집니다)", "tiers": 1,
            "choices": {"include": "이대로 바꿈", "keep": "그 단은 안 바꿈"},
            "examples": [{"tier": "9002 2", "name": "데모 오퍼 2027 · 롱스테이 2박 7% / 3박 10% · 2박 이상 단", "moves": "7% → 12%",
                          "ladder": "저장되면 2박 이상 12% · 3박 이상 10%"}]}])
        self.assertEqual([(line["tier"], line["rule"], line["choice"]) for line in again["chosen"]], [("9002 3", "OVER_30", "keep")],
                         "2박의 30% 고름은 뒤집힘을 고른 것이 아니라 남지 않는다")
        text = self.cli("render", "preview", "--plan", self.work / "plan-2.json", "--text")["text"]
        self.assertIn("2박 이상 단 · 할인율(%) | 7% → 12% | 빨간 줄 기준값이 더 큰 단보다 할인이 커집니다(작으면 작아집니다) 저장되면 2박 이상 12% · "
                      "3박 이상 10%", text)
        self.assertIn("먼저 골라 주세요 — 빨간 줄 1단.", text)
        said.append({"rule": "INVERTS", "choice": "include", "tiers": ["9002 2"], "said": "3박이 덜 받아도 2박은 올려"})
        third = self.cli("plan", "--snapshot", snapshot, "--request", request, "--resolutions", self.file("choices-3.json", said),
                         "--record", "--replaces", again["change_id"], "--out", self.work / "plan-3.json")
        self.assertEqual((third["saves"], third["counts"]["will_change"]), (1, 1))
        self.apply(third["change_id"], self.work / "plan-3.json")
        self.assertEqual(self.erp.promotion("9002")["trigger"]["tiers"], [{"threshold": 2, "pct": "12"}, {"threshold": 3, "pct": "10"}])


class GateTest(Flow):
    def test_an_erp_without_the_mark_reads_and_previews_but_never_saves(self):
        self.erp = scene.Erp(keeps=False)
        change, plan, short = self.preview(self.request(EARLY_NRF, value="16", sentence="얼리버드 46일 16% 로"))
        self.assertEqual((short["saves"], short["counts"]["NO_MARK"], short["counts"]["will_change"]), (0, 1, 0))
        self.assertEqual(short["gate"][0]["said"], GATE)
        self.assertEqual(short["blocked"][0]["label"], GATE)
        self.assertEqual(self.listed()[change]["status"], "empty")
        text = self.cli("render", "preview", "--plan", plan, "--text")["text"]
        self.assertIn(GATE, text)
        self.assertIn("저장하지 않습니다", text)
        self.assertFalse(short["scope_card"], "W4 — 저장하지 않는 미리보기에서 저장이 만드는 것을 먼저 말하지 않는다")
        for said in ("저장하면 ERP 가", "저장할 때 ERP 가", "저장은 프로모션마다 한 번"):
            self.assertNotIn(said, text, "W4 — 저장하지 않는 미리보기는 저장이 하는 일을 늘어놓지 않는다")
        refused = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=2)
        self.assertIn("저장할 것이 없는 미리보기", refused["error"])
        self.assertEqual(self.erp.posts, [])

    def test_w4_a_window_whose_row_origin_is_unknown_is_not_saved_and_begin_refuses_it(self):
        """W4 (시운전 13) — 단 줄의 숨은 칸 tiers_origin 이 「?」(ERP 가 그 줄이 어느 저장된 단에서 왔는지 모름 — 숨은 칸 없이 보낸 요청이
        거절된 뒤 다시 그린 창)이면 저장하지 않는다: 미리보기는 계산만 보이고(`gate` 에 그 문장), 적용 직전에 읽은 창이 그러면 begin 이
        아무것도 시작하지 않는다. 문장은 ERP 에서 편집 창을 닫았다가 다시 열라고 한다."""
        self.erp.data["unsure"] = True
        change, plan, short = self.preview(self.request(EARLY_NRF, value="16", sentence="얼리버드 46일 16% 로"))
        self.assertEqual((short["saves"], short["counts"]["ORIGIN_UNKNOWN"], short["counts"]["will_change"]), (0, 1, 0))
        self.assertEqual(short["gate"][0]["said"], ORIGIN_UNKNOWN)
        self.assertFalse(short["scope_card"])
        text = self.cli("render", "preview", "--plan", plan, "--text")["text"]
        self.assertIn(ORIGIN_UNKNOWN, text)
        self.assertIn("저장하지 않습니다", text)
        self.erp.data["unsure"] = False
        change, plan, short = self.preview(self.request(EARLY_NRF, value="16", sentence="얼리버드 46일 16% 로"), "plan-2.json")
        self.assertEqual(short["saves"], 1)
        self.erp.data["unsure"] = True
        refused = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=2)
        self.assertIn(ORIGIN_UNKNOWN, refused["error"])
        self.assertIn("편집 창을 닫았다가 다시 열어", refused["error"])
        self.assertEqual((self.erp.posts, self.listed()[change]["status"]), ([], "previewed"))

    def test_w4_the_plain_view_says_per_promotion_what_hidden_settings_its_tiers_carry_and_whether_this_erp_can_save(self):
        """W4 (시운전 13) — 「지금 프로모션 보여줘」만으로 프로모션마다 한 줄: 화면 밖 설정이 붙은 단, 이 ERP 에 표식이 있는지(도우미가 거기서
        저장할 수 있는지). 목록의 프로모션을 모두 읽어(read-calls --all) prices 페이지에 단다."""
        snapshot = self.read(all=True)
        calls = json.loads((snapshot.parent / "calls.json").read_text(encoding="utf-8"))["promotions"]
        self.assertEqual(len(calls), json.loads(self.look().read_text(encoding="utf-8"))["promotions"].__len__(), "목록의 프로모션 전부")
        text = self.cli("render", "prices", "--look", self.look(), "--snapshot", snapshot, "--text")["text"]
        self.assertIn("화면 밖 설정: 체크인 46일 전 단에 취소 조건 · 체크인 31일 전 단에 취소 조건 · 표식 있음 — 도우미가 저장할 수 있습니다"
                      "(그 설정은 그대로 둡니다)", text)
        self.assertIn("화면 밖 설정: 없음 · 표식 있음 — 도우미가 저장할 수 있습니다", text)
        self.assertIn("편집 창을 열어 읽고 닫았습니다", text)
        self.assertNotIn("화면 밖 설정", self.cli("render", "prices", "--look", self.look(), "--text")["text"],
                         "읽지 않고 그리면 그 줄이 없다")
        self.erp.data["keeps"] = False
        bare = self.cli("render", "prices", "--look", self.look(), "--snapshot", self.read(all=True), "--text")["text"]
        self.assertIn("화면 밖 설정: 이 ERP 는 보여 주지 않습니다 · 표식 없음 — 이 ERP 에서는 도우미가 저장하지 않습니다", bare)
        self.assertNotIn("화면 밖 설정: 없음", bare, "표식 없는 ERP 에서는 설정이 없다고 하지 않는다(보이지 않을 뿐)")
        self.erp.data.update(keeps=True, unsure=True)
        unsure = self.cli("render", "prices", "--look", self.look(), "--snapshot", self.read(all=True), "--text")["text"]
        self.assertIn("창을 닫았다가 다시 열어야 도우미가 저장합니다", unsure)
        window = self.cli("render", "window", "--snapshot", self.read(all=True), "--text")["text"]
        self.assertIn(ORIGIN_UNKNOWN, window, "설정 전부 페이지도 그 창에서는 저장하지 않는다고 한다")

    def test_a_mark_that_disappears_before_applying_stops_the_start(self):
        change, plan, short = self.preview(self.request(LONG_STAY, value="8"))
        self.assertEqual(short["saves"], 1)
        self.erp.data["keeps"] = False
        refused = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=2)
        self.assertIn(GATE, refused["error"])
        self.assertEqual((self.erp.posts, self.listed()[change]["status"]), ([], "previewed"))

    def test_the_small_erp_refuses_a_save_on_a_window_without_the_mark_like_the_page(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        self.erp.data["keeps"] = False
        call, = self.cli("calls", "--change", change)["calls"]
        answer = self.erp.apply(call["payload"])
        self.assertEqual((answer["saved"], answer["pressed"]), (False, False))
        result = self.cli("record-result", "--change", change, "--result", self.file("refused.json", answer))
        self.assertEqual((result["saved"], result["status"]), (False, "stopped"))
        self.assertEqual(self.erp.posts, [])

    def test_a_rollback_on_an_erp_that_lost_the_mark_makes_no_save(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        self.erp.data["keeps"] = False
        refused = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                           "--out", self.work / "rollback-x.json", code=2)
        self.assertIn(GATE, refused["error"])


class AwayFromThePathTest(Flow):
    def test_the_window_shows_a_different_tier_value_than_the_reading_and_nothing_is_saved(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.erp.promotion("9002")["trigger"]["tiers"][1]["pct"] = "11"
        begun = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        self.assertEqual((begun["same"], begun["status"]), (False, "previewed"))
        self.assertEqual(begun["differences"][0]["key"], {"promotion": "9002", "tier": "3"})
        self.assertEqual(self.erp.posts, [])

    def test_a_setting_the_helper_does_not_touch_also_stops_the_start(self):
        change, plan, _short = self.preview(self.request(COMMON, value="6"))
        self.erp.promotion("9006")["apply_flag"] = False
        begun = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        self.assertFalse(begun["same"])
        self.assertEqual(self.erp.posts, [])

    def test_an_off_form_mark_that_changed_since_the_preview_stops_the_start(self):
        change, plan, _short = self.preview(self.request(EARLY_NRF, value="16"))
        del self.erp.promotion("9005")["trigger"]["tiers"][1]["cancellation"]
        begun = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        self.assertFalse(begun["same"])
        self.assertEqual(self.erp.posts, [])

    def test_the_small_erp_refuses_a_payload_whose_form_differs_even_if_the_ledger_let_it_through(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        self.erp.promotion("9002")["code"] = "LS"
        call, = self.cli("calls", "--change", change)["calls"]
        self.assertEqual(self.erp.apply(call["payload"])["pressed"], False)
        self.assertEqual(self.erp.posts, [])

    def test_a_save_that_changed_another_tier_is_caught_by_the_check_after_applying(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        self.erp.promotion("9002")["trigger"]["tiers"][1]["pct"] = "9"
        result = self.cli("verify", "--change", change, "--snapshot", self.read(record=change), code=1)
        self.assertEqual(result["moved"][0]["what"], "할인 값 10 → 9")

    def test_an_off_form_name_lost_in_the_save_is_caught_by_the_check_after_applying(self):
        change, plan, _short = self.preview(self.request(EARLY_NRF, value="16"))
        self.apply(change, plan)
        del self.erp.promotion("9005")["trigger"]["tiers"][0]["cancellation"]
        result = self.cli("verify", "--change", change, "--snapshot", self.read(record=change), code=1)
        self.assertEqual([item["what"] for item in result["moved"]], ["기준값 46 단의 화면에 없는 설정 'cancellation' → '없음'"])

    def test_a_tier_changed_since_is_kept_with_the_three_values_and_the_cause(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        self.erp.promotion("9002")["trigger"]["tiers"][0]["pct"] = "9"
        out = self.work / "rollback-1.json"
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record", "--out", out)
        self.assertEqual((rollback["restored"], rollback["kept"], rollback["saves"]), (0, 1, 0))
        self.assertTrue(rollback["kept_why"][0]["outside"])
        text = self.cli("render", "rollback", "--plan", out, "--text")["text"]
        self.assertIn("도우미 밖에서 바뀜", text)
        self.assertIn("되돌려도 바뀌지 않습니다", text)

    def test_a_threshold_someone_changed_makes_the_tier_gone_and_the_rollback_keeps_it(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        self.erp.promotion("9002")["trigger"]["tiers"][0]["threshold"] = 5
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                            "--out", self.work / "rollback-1.json")
        self.assertEqual((rollback["restored"], rollback["kept"]), (0, 1))

    def test_a_failed_save_stops_and_check_lets_it_continue_after_a_fresh_reading(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        result, = self.apply(change, plan, outcome=False)
        self.assertEqual((result["saved"], result["status"]), (False, "stopped"))
        refused = self.cli("calls", "--change", change, code=2)
        self.assertIn("멈춰 있습니다", refused["error"])
        report = self.cli("check", "--change", change, "--snapshot", self.read(record=change))
        self.assertTrue(report["can_continue"], report)
        call, = self.cli("calls", "--change", change)["calls"]
        answer = self.erp.apply(call["payload"])
        self.assertEqual(self.cli("record-result", "--change", change, "--result", self.file("again.json", answer))["status"], "applied")

    def test_a_saved_step_is_never_handed_out_again(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        self.assertEqual(self.cli("calls", "--change", change)["calls"], [])
        self.assertEqual(len(self.erp.posts), 1)

    def test_a_change_idle_for_fifteen_minutes_is_stopped_and_needs_a_fresh_check(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        self.erp.clock += scene.timedelta(minutes=16)
        refused = self.cli("calls", "--change", change, code=2)
        self.assertIn("멈춰 있습니다", refused["error"])
        self.assertTrue(self.cli("check", "--change", change, "--snapshot", self.read(record=change))["can_continue"])

    def test_a_name_that_states_the_old_rate_is_pointed_out(self):
        _change, _plan, short = self.preview(self.request(LONG_STAY, value="8"))
        self.assertEqual(short["names"], ["프로모션 「데모 오퍼 2027 · 롱스테이 2박 7% / 3박 10%」의 이름에 바꾸기 전 값(7%)이 그대로 적혀 "
                                          "있습니다 — 도우미는 이름을 바꾸지 않으니 ERP 에서 사람이 고쳐 주세요."])

    def test_a_plan_with_nothing_to_save_says_so(self):
        change, plan, short = self.preview(self.request(LONG_STAY, value="7"))
        self.assertEqual(short["saves"], 0)
        self.assertEqual(self.listed()[change]["status"], "empty")
        self.assertIn("저장할 것이 없습니다", self.cli("render", "preview", "--plan", plan, "--text")["text"])

    def test_list_names_the_kind_in_plain_words_and_another_helper_lists_the_same_line(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        mine = self.listed()[change]
        self.assertEqual(mine["helper"], "프로모션 할인 도우미")
        self.assertTrue(mine["scope"].startswith("프로모션 1개 (데모 오퍼 2027 · 롱스테이 2박 7% / 3박 10%) · 할인 값 8로"), mine["scope"])
        theirs = self.cli("list", "--look", self.look(), script=CHARGE_SCRIPT)["changes"]
        self.assertEqual(next(entry for entry in theirs if entry["id"] == change)["line"], mine["line"])
        refused = self.cli("read-calls", "--record", change, script=CHARGE_SCRIPT, code=2)
        self.assertIn("프로모션 할인 도우미의 기록입니다", refused["error"])

    def test_the_result_page_says_what_was_saved_and_how_to_undo(self):
        change, plan, _short = self.preview(self.request(LONG_STAY, value="8"))
        self.apply(change, plan)
        text = self.cli("render", "result", "--change", change, "--snapshot", self.read(record=change), "--text")["text"]
        self.assertIn("새 견적부터", text)
        self.assertIn(f"{change}번 되돌려", text)


if __name__ == "__main__":
    unittest.main()
