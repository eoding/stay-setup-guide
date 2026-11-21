"""명령으로 한 바퀴(C1~C6) — 페이지 답은 charge_scene 의 작은 ERP 가 만든다(진짜 페이지 모듈의 답과 같은 모양, test_golden).

모양 넷: 시간대 요율 둘인 정률 부과금(701), 날짜 하나에 붙는 인당 정액 의무 부과금(703), 현장 결제 부과금(704), 연령별 단가가 있는
부과금(705). 넷 모두 읽기 → 바꾸기 → 미리보기 → 적용 직전 다시 읽기 → begin → 저장 → 다시 읽어 견주기 → 되돌리기 → 견주기.
그리고 그 길에서 벗어나는 때: 적용 직전에 창의 값이 달라짐(아무것도 저장 안 함), 저장이 다른 칸을 바꿈(견주기가 짚음), 그 사이
바뀐 칸은 되돌리지 않고 세 값과 까닭을 댐, 멈춘 변경, 같은 장부의 다른 도우미가 이 변경을 같은 줄로 읽어 주기만 하고 만지지 않음.

    python3 -m unittest discover -s tests
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import charge_scene as scene

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "charge_change.py"
ADDON_SCRIPT = SKILL.parent / "stay-addon-price-change" / "scripts" / "addon_change.py"
PRICE_SCRIPT = SKILL.parent / "stay-price-change" / "scripts" / "price_change.py"

LATE_BAND = {"offer": "601", "charge": "701", "time": "14:01-18:00", "field": "pct"}
GALA = {"offer": "601", "charge": "703", "field": "amount"}
RESORT = {"offer": "601", "charge": "704", "field": "onsite"}
CHILD = {"offer": "602", "charge": "705", "age": "CHD", "field": "amount"}


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
        """명령 하나 — 장부의 시계는 작은 ERP 의 시계(마지막 답의 끝난 시각)에 서 있다. 이 컴퓨터의 시계에 기대지 않는다."""
        env = dict(self.env, STAY_PRICE_TEST_NOW=self.erp.clock.isoformat())
        done = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, code, f"{args[0]}: {done.stderr or done.stdout}")
        return json.loads(done.stdout) if code in (0, 1) else json.loads(done.stderr)

    def file(self, name, data) -> Path:
        path = self.work / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def request(self, *amounts, sentence="바꿔줘", **change) -> Path:
        self.names += 1
        return self.file(f"request-{self.names}.json", dict(kind="charge_change", hotel=scene.HOTEL, amounts=list(amounts),
                                                             sentence=sentence, **change))

    def read(self, **scope) -> Path:
        """읽기 한 번 — read-calls → 부과금마다 readCharge 답 → read. 지금 값 파일의 자리를 돌려준다."""
        self.readings += 1
        folder = self.work / f"읽기-{self.readings}"
        folder.mkdir()
        flags = ["--record", scope["record"]] if "record" in scope else ["--request", scope["request"]]
        self.cli("read-calls", *flags, "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["charges"]
        scene.write_answers(folder, "charge", [self.erp.read_charge(call) for call in calls])
        self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        return folder / "snapshot.json"

    def look(self) -> Path:
        """look 한 번 — 이 작업 폴더의 look/ 에 답을 두고 look 명령으로 묶는다. look.json 의 자리를 돌려준다."""
        if not (self.work / "look.json").exists():
            scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
            self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        return self.work / "look.json"

    def listed(self, *flags) -> dict:
        """탭의 호텔(look)로 좁힌 장부 목록 — 번호 → 줄."""
        return {entry["id"]: entry for entry in self.cli("list", "--look", self.look(), *flags)["changes"]}

    def preview(self, request, name="plan-1.json", **extra) -> tuple[int, Path]:
        snapshot = self.read(request=request)
        plan = self.work / name
        flags = [item for pair in extra.items() for item in (f"--{pair[0]}", pair[1])]
        short = self.cli("plan", "--snapshot", snapshot, "--request", request, "--record", *flags, "--out", plan)
        return short["change_id"], plan

    def apply(self, change, plan, outcome=True) -> list[dict]:
        begun = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        self.assertEqual(begun["status"], "applying", begun)
        results = []
        for call in self.cli("calls", "--change", change)["calls"]:
            answer = self.erp.apply(call["payload"], outcome)
            results.append(self.cli("record-result", "--change", change, "--result",
                                    self.file(f"적용-{change}-{call['no']}.json", answer)))
        return results

    def round_trip(self, request, plan_flags=None):
        """미리보기 → 적용 → 견주기 → 되돌리기 → 견주기. 장부 번호 · 계산 파일 · 저장 요청들을 돌려준다."""
        change, plan = self.preview(request, **(plan_flags or {}))
        before = scene.copy.deepcopy(self.erp.data)
        results = self.apply(change, plan)
        self.assertEqual([item["saved"] for item in results], [True] * len(results))
        posts = list(self.erp.posts)
        verified = self.cli("verify", "--change", change, "--snapshot", self.read(record=change))
        self.assertEqual((verified["same"], verified["mismatches"], verified["moved"]), (True, [], []), verified)
        out = self.work / f"rollback-{change}.json"
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                            "--sentence", "방금 것 되돌려", "--out", out)
        self.assertEqual(rollback["kept"], 0)
        back = rollback["change_id"]
        self.assertEqual([item["saved"] for item in self.apply(back, out)], [True] * rollback["saves"])
        self.assertTrue(self.cli("verify", "--change", back, "--snapshot", self.read(record=back))["same"])
        self.assertEqual(self.erp.data, before, "되돌린 뒤 저장된 값이 처음과 같다")
        return change, plan, posts


def replaced(form, edits):
    """form 에서 짚은 (이름, 몇 번째) 칸만 바꾼 목록 — 저장 요청이 꼭 이것이어야 한다."""
    seen, out = {}, []
    for name, value in form:
        nth = seen.get(name, 0)
        seen[name] = nth + 1
        out.append([name, edits.get((name, nth), value)])
    return out


class FourShapesTest(Flow):
    def test_c1_look_lists_every_charge_per_offer_as_the_list_shows_it_and_presses_nothing_that_saves(self):
        scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
        look = self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        self.assertEqual((look["offers"], look["charges"]), (2, 6))
        listing = json.loads((self.work / "look.json").read_text(encoding="utf-8"))
        late = next(item for item in listing["charges"] if item["id"] == "701")
        self.assertEqual((late["offer"], late["offer_name"], late["kind"], late["amount"][:2]),
                         ("601", "데모 오퍼 2027", "레이트 체크아웃",
                          ["12:01 ~ 14:00 · 정액: 0.00 USD", "14:01 ~ 18:00 · 1박 요금의 %: 50.00%"]))
        page = self.cli("render", "prices", "--look", self.work / "look.json", "--text")
        self.assertEqual(set(page), {"text"}, "--text 만이면 파일을 만들지 않는다")
        for said in ("현장 결제: 15.00 USD", "소아: 50.00 USD", "의무 지정 1일 2026-12-24", "미정"):
            self.assertIn(said, page["text"])
        lines = page["text"].splitlines()
        self.assertEqual(lines.count(lines[0]), 1, "K4 — --text 는 제목을 한 번만 낸다")
        self.assertIn('10% 올려줘" 처럼 말씀해 주세요', page["text"], "K5 — 부과금마다 통화가 달라 말 보기는 퍼센트로")
        first = listing["charges"][0]
        self.assertIn(f'"{first["offer_name"]} · {first["name"]} 10% 올려줘"', page["text"], "T9 — 말 보기도 목록의 줄처럼 오퍼부터 댄다")
        self.assertEqual(self.erp.posts, [])

    def test_a_percentage_charge_with_two_time_bands_changes_one_band_and_sends_the_other_band_as_read(self):
        request = self.request(LATE_BAND, value="60", sentence="레이트 체크아웃 50% 를 60% 로")
        change, plan, posts = self.round_trip(request)
        data = json.loads(plan.read_text(encoding="utf-8"))
        self.assertEqual([(c["before"], c["after"], c["verdict"]) for c in data["plan"]["changes"]], [("50.00", "60.00", None)])
        form = scene.form_of(*self.offer_charge("701"))
        self.assertEqual(posts[0], replaced(form, {("tiers_pct", 1): "60.00"}))
        self.assertEqual(dict(posts[0])["pct_mode"], "set", "금액의 뜻(지정)은 창이 보인 그대로 간다")
        self.assertEqual([v for k, v in posts[0] if k == "tiers_amount"], ["0.00", ""], "건드리지 않은 시간대 줄은 그대로 간다")

    def test_a_flat_per_person_mandatory_charge_on_one_date_keeps_its_date_room_and_mandatory_mark(self):
        request = self.request(GALA, value="100", sentence="크리스마스 갈라 디너 성인 요금 100 으로")
        _change, plan, posts = self.round_trip(request)
        sent = dict(posts[0])
        self.assertEqual((sent["amount"], sent["amount_mode"], sent["date_mode"], sent["date_scope"], sent["room_scope"]),
                         ("100.00", "set", "mandatory", "2026-12-24", "51"))
        page = self.cli("render", "preview", "--plan", plan, "--text")["text"]
        self.assertIn("90.00 USD → 100.00 USD", page)
        self.assertIn("저장 한 번. 맞으면 \"적용\"이라고 해 주세요.", page, "F10 — 저장이 하나면 「1번(부과금마다 한 번)」이 아니다")

    def test_a_pay_at_property_charge_changes_only_its_on_site_amount_after_the_red_line_is_chosen(self):
        request = self.request(RESORT, value="20", sentence="리조트피 현장 결제 20달러로")
        change, plan = self.preview(request)
        short = json.loads(plan.read_text(encoding="utf-8"))
        self.assertIsNone(short["steps"], "30% 넘게 바뀌면 고르기 전에는 저장 단계가 없다")
        self.assertEqual([item["rule"] for item in short["red"]], ["OVER_30"])
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=2)
        choose = self.file("고름.json", [{"rule": "OVER_30", "choice": "include", "amounts": ["704 onsite"],
                                         "said": "현장 결제는 20달러 맞아요, 그대로 바꿔 주세요"}])
        _change, _plan, posts = self.round_trip(request, dict(resolutions=choose, replaces=change, name="plan-2.json"))
        sent = dict(posts[0])
        self.assertEqual((sent["onsite_amount"], sent["amount"], sent["onsite_currency"]), ("20.00", "0.00", "2"))
        self.assertIn("“현장 결제는 20달러 맞아요, 그대로 바꿔 주세요”",
                      self.cli("render", "result", "--change", _change, "--text")["text"], "고르며 한 말이 결과에 보인다")
        listed = self.listed()
        self.assertEqual(listed[change]["status"], "replaced")

    def test_an_age_rate_changes_by_its_band_code_and_the_other_band_and_adult_price_stay(self):
        request = self.request(CHILD, percent="10", sentence="갈라 디너 아동 요금 10% 올려줘")
        change, _plan, posts = self.round_trip(request)
        sent = dict(posts[0])
        self.assertEqual((sent["age_rate_82"], sent["age_rate_81"], sent["amount"]), ("55.00", "0.00", "100.00"))
        listed = self.listed()
        self.assertEqual(listed[change]["status"], "rolled_back")
        self.assertIn("1인 단가 +10%", listed[change]["scope"])

    def test_the_words_said_with_a_red_line_choice_are_required_kept_in_the_ledger_and_shown(self):
        said = "갈라 디너는 무료로 하기로 했어요"
        request = self.request(GALA, value="0", sentence="갈라 디너 무료로")
        first, _plan = self.preview(request)
        snapshot = self.read(request=request)
        refused = self.cli("plan", "--snapshot", snapshot, "--request", request, "--record", "--replaces", first, "--resolutions",
                           self.file("bare.json", [{"rule": "OVER_30", "choice": "include"}]), "--out", self.work / "plan-2.json", code=2)
        self.assertIn("(said)", refused["error"], "담당자의 말이 없는 고름은 받지 않는다")
        short = self.cli("plan", "--snapshot", snapshot, "--request", request, "--record", "--replaces", first, "--resolutions",
                         self.file("choices.json", [{"rule": "OVER_30", "choice": "include", "said": said}]),
                         "--out", self.work / "plan-2.json")
        self.assertEqual([(item["label"], item["said"]) for item in short["chosen"]], [("이대로 바꿈", said)])
        db = sqlite3.connect(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3")
        kept = set(db.execute("SELECT DISTINCT choice, said FROM item_values WHERE change_id = ? AND choice IS NOT NULL",
                              (short["change_id"],)))
        db.close()
        self.assertEqual(kept, {("include", said)})
        self.apply(short["change_id"], self.work / "plan-2.json")
        page = self.cli("render", "result", "--change", short["change_id"], "--text")["text"]
        self.assertIn("고르신 빨간 줄", page)
        self.assertIn(f"“{said}”", page)

    def test_zero_is_allowed_and_said_out_loud(self):
        change, plan = self.preview(self.request(GALA, value="0", sentence="갈라 디너 무료로"),
                                    resolutions=self.file("고름-0.json", [{"rule": "OVER_30", "choice": "include", "said": "네 그대로요"}]))
        data = json.loads(plan.read_text(encoding="utf-8"))
        self.assertEqual((data["counts"]["free"], len(data["steps"])), (1, 1))
        self.assertIn("무료가 됩니다", self.cli("render", "preview", "--plan", plan, "--text")["text"])
        self.apply(change, plan)
        self.assertEqual(self.erp.charge("703")["amount"], "0.00")

    def offer_charge(self, charge_id):
        return next((o, c) for o in self.erp.data["offers"] for c in o["charges"] if c["id"] == charge_id)


class FreshReadingTest(Flow):
    def test_the_window_shows_a_different_amount_than_the_reading_and_nothing_is_saved(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.erp.charge("701")["tiers"][1]["pct"] = "55.00"          # 미리보기 뒤 누가 ERP 에서 고침
        answer = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        self.assertEqual((answer["same"], answer["status"]), (False, "previewed"))
        self.assertEqual([item["key"] for item in answer["differences"]],
                         [{"charge": "701", "time": "14:01-18:00"}, {"charge": "701"}], "그 줄과, 그 줄을 보이는 목록 글자")
        self.assertEqual(self.erp.posts, [], "아무것도 저장하지 않았다")
        self.cli("calls", "--change", change, code=2)

    def test_a_changed_field_the_helper_does_not_touch_also_stops_the_start(self):
        change, plan = self.preview(self.request(GALA, value="95"))
        self.erp.charge("703")["dates"] = ["2026-12-25"]
        answer = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        moved, = answer["differences"]
        self.assertEqual((moved["then"]["others"]["form.date_scope"], moved["now"]["others"]["form.date_scope"]),
                         ("2026-12-24", "2026-12-25"))

    def test_the_same_window_refuses_a_save_whose_form_differs_even_when_the_ledger_let_it_through(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        call, = self.cli("calls", "--change", change)["calls"]
        self.erp.charge("701")["tiers"][0]["amount"] = "5.00"       # begin 과 저장 사이에 바뀜 — 페이지가 막는다
        refused = self.cli("record-result", "--change", change, "--result", self.file("1.json", self.erp.apply(call["payload"])))
        self.assertEqual((refused["saved"], refused["status"]), (False, "stopped"))
        self.assertEqual(self.erp.posts, [])

    def test_a_save_that_changed_an_amount_it_was_not_asked_to_is_caught_by_the_check_after_applying(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.apply(change, plan)
        self.erp.charge("701")["tiers"][0]["amount"] = "10.00"      # ERP 가 저장하며 다른 줄을 바꿨다고 치자
        verified = self.cli("verify", "--change", change, "--snapshot", self.read(record=change), code=1)
        self.assertEqual(verified["mismatches"], [], "넣은 값은 맞다")
        self.assertEqual([item["what"] for item in verified["moved"]], ["정액 금액 0.00 → 10.00"])

    def test_a_time_band_the_save_added_is_caught_too(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.apply(change, plan)
        self.erp.charge("701")["tiers"].append({"from": "18:01", "to": "20:00", "basis": 1, "amount": None, "pct": "100.00"})
        verified = self.cli("verify", "--change", change, "--snapshot", self.read(record=change), code=1)
        self.assertIn("미리보기 때 없던 것이 생겼습니다", [item["what"] for item in verified["moved"]])


class RollbackKeepsTest(Flow):
    def test_amounts_changed_since_are_kept_with_the_three_values_and_the_cause(self):
        change, plan = self.preview(self.request(LATE_BAND, GALA, value="60", sentence="둘 다 60"),
                                    resolutions=self.file("고름.json", [{"rule": "OVER_30", "choice": "include", "said": "네 그대로요"}]))
        self.apply(change, plan)
        self.erp.charge("703")["amount"] = "70.00"                  # 도우미 밖에서 고침
        out = self.work / "rollback-1.json"
        short = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--out", out)
        self.assertEqual((short["restored"], short["kept"]), (1, 1))
        self.assertEqual(short["kept_why"], [{"change_id": None, "at": None, "sentence": None, "outside": True, "items": 1}])
        kept, = json.loads(out.read_text(encoding="utf-8"))["rollback"]["kept"]
        self.assertEqual((kept["recorded"], kept["written"], kept["now"]["fields"]["amount"]),
                         ({"amount": "90.00"}, {"amount": "60.00"}, "70.00"))
        page = self.cli("render", "rollback", "--plan", out, "--text")["text"]
        self.assertIn("도우미 밖에서 바뀜", page)
        self.assertIn("ERP 번호", page, "되돌릴 수 없는 것(줄 번호 · 적용 범위 기록)을 적용 전에 말한다")

    def test_a_later_change_by_the_helper_is_named_as_the_cause(self):
        first, plan = self.preview(self.request(CHILD, value="52"))
        self.apply(first, plan)
        second, plan2 = self.preview(self.request(CHILD, value="54"), "plan-2.json")
        self.apply(second, plan2)
        short = self.cli("rollback", "--change", first, "--snapshot", self.read(record=first), "--out", self.work / "rollback-1.json")
        self.assertEqual([(item["change_id"], item["outside"]) for item in short["kept_why"]], [(second, False)])

    def test_a_rollback_of_one_charge_leaves_the_other_charge_of_the_same_change(self):
        change, plan = self.preview(self.request(LATE_BAND, CHILD, value="55", sentence="둘 다 55"))
        self.apply(change, plan)
        out = self.work / "rollback-1.json"
        short = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--charge", "705", "--record",
                         "--out", out)
        self.assertEqual((short["scope"], short["saves"]), ("부과금 705번", 1))
        self.apply(short["change_id"], out)
        self.assertEqual((self.erp.charge("705")["ages"]["82"], self.erp.charge("701")["tiers"][1]["pct"]), ("50.00", "55.00"))


class StoppedTest(Flow):
    def test_a_failed_save_stops_and_check_lets_the_rest_continue_after_a_fresh_reading(self):
        change, plan = self.preview(self.request(GALA, CHILD, value="95", sentence="둘 다 95"),
                                    resolutions=self.file("고름.json", [{"rule": "OVER_30", "choice": "include", "said": "네 그대로요"}]))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        first, second = self.cli("calls", "--change", change)["calls"]
        done = self.cli("record-result", "--change", change, "--result", self.file("1.json", self.erp.apply(first["payload"])))
        self.assertEqual(done["status"], "applying")
        refused = self.cli("record-result", "--change", change, "--result",
                           self.file("2.json", self.erp.apply(second["payload"], outcome=False)))
        self.assertEqual((refused["saved"], refused["status"]), (False, "stopped"))
        self.cli("calls", "--change", change, code=2)
        report = self.cli("check", "--change", change, "--snapshot", self.read(record=change))
        self.assertEqual((report["can_continue"], report["remaining"], report["cause"]), (True, [2], "failed"))
        call, = self.cli("calls", "--change", change)["calls"]
        self.assertEqual(self.cli("record-result", "--change", change, "--result",
                                  self.file("2b.json", self.erp.apply(call["payload"])))["status"], "applied")

    def test_a_change_idle_for_fifteen_minutes_is_stopped_and_needs_a_fresh_check(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        db = sqlite3.connect(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3")
        with db:
            db.execute("UPDATE changes SET active_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (change,))
        db.close()
        self.assertIn("멈춰 있습니다", self.cli("calls", "--change", change, code=2)["error"])
        report = self.cli("check", "--change", change, "--snapshot", self.read(record=change))
        self.assertEqual((report["cause"], report["can_continue"]), ("cut_off", True))
        self.assertEqual(len(self.cli("calls", "--change", change)["calls"]), 1)

    def test_check_will_not_continue_when_another_amount_of_the_same_charge_moved(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        call, = self.cli("calls", "--change", change)["calls"]
        self.cli("record-result", "--change", change, "--result",
                 self.file("1.json", dict(self.erp.apply(call["payload"], outcome=False))))
        self.erp.charge("701")["tiers"][0]["amount"] = "3.00"        # 같은 부과금의 다른 줄이 그 사이 바뀜
        report = self.cli("check", "--change", change, "--snapshot", self.read(record=change))
        self.assertFalse(report["can_continue"])
        self.assertTrue(any("미리보기 때 읽은 값과 다릅니다" in why for why in report["why"]), report["why"])

    def test_a_save_refused_because_someone_changed_the_charge_shows_what_the_check_read_and_no_continue(self):
        """T1 — 첫 저장 뒤 다른 사람이 둘째 부과금의 금액을 바꿔 둘째 저장이 누르기 전에 거절됐다. 다시 읽어 check 가 이어서 할 수
        없다고 한 뒤의 결과 페이지는 이어서를 빼고, 그 칸을 check 가 읽은 값(그 시각과 함께 — 지금 값이라고 하지 않는다, 시운전 8
        F1)과 그 사이 바뀌었다는 문장으로 보인다."""
        change, plan = self.preview(self.request(GALA, CHILD, value="95", sentence="둘 다 95"),
                                    resolutions=self.file("고름.json", [{"rule": "OVER_30", "choice": "include", "said": "네 그대로요"}]))
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        first, second = self.cli("calls", "--change", change)["calls"]
        self.cli("record-result", "--change", change, "--result", self.file("1.json", self.erp.apply(first["payload"])))
        self.erp.charge("705")["ages"]["82"] = "41.00"        # 다른 사람이 ERP 에서 고침
        refused = self.cli("record-result", "--change", change, "--result", self.file("2.json", self.erp.apply(second["payload"])))
        self.assertEqual((refused["saved"], refused["status"]), (False, "stopped"))
        report = self.cli("check", "--change", change, "--snapshot", self.read(record=change))
        self.assertFalse(report["can_continue"])
        text = self.cli("render", "result", "--change", change, "--text")["text"]
        self.assertNotIn("이어서 —", text)
        self.assertIn("ERP 를 다시 읽어 보니 이어서 할 수 없습니다.", text)
        self.assertIn("「그 사이 ERP 에서 바뀜」 1칸은 미리보기 뒤에 ERP 에서 값이 바뀐 칸입니다", text)
        self.assertRegex(text, r"미리보기 때 \S+ USD · \d+시 \d+분에 다시 읽으니 41\.00 USD 그 사이 ERP 에서 바뀜 · 넣지 않음")
        self.assertIn("다시 읽은 값은 그때 ERP 에 있던 값이고, 그 뒤에 또 바뀌었을 수 있습니다.", text)
        self.assertNotRegex(text, r"지금 [\d,.]+")
        self.assertNotIn("로그인", text)

    def test_a_saved_step_is_never_handed_out_again(self):
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.apply(change, plan)
        self.assertEqual(self.cli("calls", "--change", change)["calls"], [], "저장된 단계는 다시 내지 않는다")
        self.assertEqual(len(self.erp.posts), 1)


class AnswersTest(Flow):
    def test_a_missing_piece_is_asked_for_by_this_helpers_take(self):
        request = self.request(LATE_BAND, value="60")
        folder = self.work / "읽기-x"
        folder.mkdir()
        self.cli("read-calls", "--request", request, "--out", folder / "calls.json")
        call, = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["charges"]
        answer, *pieces = self.erp.read_charge(call)
        scene.write_answers(folder, "charge", [[answer, *pieces[1:]]])
        refused = self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json", code=2)
        self.assertIn("stayCharge.take(", refused["error"])
        self.assertNotIn("stayPrice.take(", refused["error"])
        self.assertEqual(refused["refetch"][0]["at"], 0)

    def test_render_text_only_reads_the_page_and_refuses_an_out_file(self):
        _change, plan = self.preview(self.request(GALA, value="95"))
        self.assertIn("text", self.cli("render", "preview", "--plan", plan, "--text"))
        self.cli("render", "preview", "--plan", plan, "--text", "--out", self.work / "x.html", code=2)
        self.assertFalse((self.work / "x.html").exists())

    def test_the_scope_line_counts_the_charges_a_change_writes(self):
        change, _plan = self.preview(self.request(GALA, {"offer": "602", "charge": "706", "field": "amount"}, value="95",
                                                  sentence="갈라 디너 95"))
        entry = self.listed()[change]
        self.assertTrue(entry["scope"].startswith("부과금 1개 (데모 오퍼 2027 · 크리스마스 갈라 디너"), entry["scope"])


class NameNoteTest(Flow):
    """H1 — 시운전에서 레이트 체크아웃을 50% 에서 60% 로 바꾸는 동안 이름 · 설명은 「… 1박 요금의 50%」 그대로였고 아무도 말하지
    않았다. 바꾸는 값이 이름 · 설명에 적혀 있으면 미리보기와 결과가 한 문장으로 알린다. 우연히 같은 숫자는 알리지 않는다."""

    def test_a_name_and_a_description_that_state_the_old_rate_are_pointed_out_in_the_preview_and_the_result(self):
        self.erp.charge("701")["description"] = "14:01 부터 18:00 까지 1박 요금의 50% 를 받습니다"
        change, plan = self.preview(self.request(LATE_BAND, value="60", sentence="레이트 체크아웃 50% 를 60% 로"))
        names = json.loads(plan.read_text(encoding="utf-8"))["names"]
        self.assertEqual(names, [
            "부과금 「데모 오퍼 2027 · 레이트 체크아웃 (14시 이후 · 1박 요금의 50%)」의 이름에 바꾸기 전 값(50%)이 그대로 적혀 "
            "있습니다 — 도우미는 이름을 바꾸지 않으니 ERP 에서 사람이 고쳐 주세요.",
            "부과금 「데모 오퍼 2027 · 레이트 체크아웃 (14시 이후 · 1박 요금의 50%)」의 설명 “14:01 부터 18:00 까지 1박 요금의 50% 를 "
            "받습니다”에 바꾸기 전 값(50%)이 그대로 적혀 있습니다 — 도우미는 설명을 바꾸지 않으니 ERP 에서 사람이 고쳐 주세요."])
        self.assertIn(names[0], self.cli("render", "preview", "--plan", plan, "--text")["text"])
        self.apply(change, plan)
        self.assertEqual(self.erp.charge("701")["name"], "레이트 체크아웃 (14시 이후 · 1박 요금의 50%)", "이름은 바꾸지 않는다")
        verified = self.cli("verify", "--change", change, "--snapshot", self.read(record=change))
        self.assertEqual(verified["names"], names, "적용 뒤에도 말한다")
        self.assertIn(names[1], self.cli("render", "result", "--change", change, "--text")["text"])

    def test_an_on_site_amount_in_the_description_is_pointed_out_too(self):
        self.erp.charge("704")["description"] = "체크인 때 15달러를 호텔에 직접 냅니다"
        _change, plan = self.preview(self.request(RESORT, value="17", sentence="리조트피 현장 결제 17달러로"))
        name, = json.loads(plan.read_text(encoding="utf-8"))["names"]
        self.assertIn("설명 “체크인 때 15달러를 호텔에 직접 냅니다”에 바꾸기 전 값(15)", name)

    def test_a_number_that_only_happens_to_match_the_old_amount_is_not_pointed_out(self):
        self.erp.charge("703")["amount"] = "24.00"                        # 이름의 「12/24」 는 날짜다
        self.erp.charge("701")["tiers"][0]["amount"] = "14.00"            # 이름의 「14시 이후」 는 시각이다
        self.erp.charge("701")["description"] = "만 14세 이상은 14:00 까지 무료입니다"
        _change, plan = self.preview(self.request(GALA, {"offer": "601", "charge": "701", "time": "12:01-14:00", "field": "amount"},
                                                  percent="5", sentence="갈라 디너와 레이트 체크아웃 앞 시간대 5% 올려줘"))
        data = json.loads(plan.read_text(encoding="utf-8"))
        self.assertEqual((data["counts"]["will_change"], data["names"]), (2, []))
        self.assertNotIn("바꾸기 전 값", self.cli("render", "preview", "--plan", plan, "--text")["text"])


class SmallFindingsTest(Flow):
    """H4 — 시운전의 작은 것들: 다음 작업의 look 은 앞 작업이 받은 쪽을 빌리고, 미리보기의 수와 표가 맞으며(계산에 쓰이지 않는 값은
    그렇게 적는다), 바꾸지 않고 부과금 하나의 설정을 다 볼 수 있다."""

    def test_a_later_look_of_the_same_screen_borrows_the_pieces_an_earlier_look_folder_took(self):
        work = Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "작업"
        first, second = work / "2026-11-21 100000" / "look", work / "2026-11-21 103000" / "look"
        scene.write_answers(first, "look", [scene.look_answer(self.erp)])
        self.cli("look", "--answers", first, "--out", first.parent / "look.json")
        scene.write_answers(second, "look", [scene.look_answer(self.erp, body_id="blook2")[:1]])
        short = self.cli("look", "--answers", second, "--out", second.parent / "look.json")
        self.assertEqual((short["offers"], short["charges"]), (2, 6), "같은 화면이면 쪽을 다시 받지 않는다")
        self.erp.charge("703")["amount"] = "91.00"            # 화면이 바뀌면 빌릴 것이 없어 받으라고 한다
        third = work / "2026-11-21 110000" / "look"
        scene.write_answers(third, "look", [scene.look_answer(self.erp, body_id="blook3")[:1]])
        error = self.cli("look", "--answers", third, "--out", third.parent / "look.json", code=2)
        self.assertEqual([item["id"] for item in error["refetch"]], ["blook3"])

    def test_the_preview_counts_what_its_table_shows_and_names_a_value_the_erp_does_not_use(self):
        _change, plan = self.preview(self.request(LATE_BAND, value="60"))
        counts = json.loads(plan.read_text(encoding="utf-8"))["counts"]
        self.assertEqual((counts["will_change"], counts["unchanged"]), (1, 0))
        text = self.cli("render", "preview", "--plan", plan, "--text")["text"]
        self.assertIn("0 그대로인 칸", text)
        rows = [line for line in text.splitlines() if line.count("|") == 2 and "금액 칸" not in line]
        self.assertFalse([line for line in rows if line.split("|")[1].strip().endswith("그대로")],
                         "「그대로인 칸」 0 이면 표의 전 → 후 칸에도 「그대로」가 없다")
        sent = [line for line in rows if line.endswith("그대로 보냄")]
        self.assertIn(f"{len(sent)} 짚지 않아 그대로 보내는 금액 칸", text, "수와 표가 맞는다")
        top = next(line for line in rows if line.startswith("부과금 · 정률(%)"))
        self.assertIn("쓰이지 않는 값", top, "시간대 줄이 있는 부과금의 맨 위 정률은 「그대로」가 아니라 쓰이지 않는 값이다")

    def test_one_charge_s_whole_edit_window_can_be_shown_without_a_change_request(self):
        self.erp.charge("701")["description"] = "늦은 체크아웃은 프런트에 미리 말해 주세요"
        folder = self.work / "읽기-설정"
        folder.mkdir()
        self.assertIn("--look", self.cli("read-calls", "--charge", "701", "--out", folder / "calls.json", code=2)["error"])
        self.assertIn("999", self.cli("read-calls", "--charge", "999", "--look", self.look(), "--out", folder / "x.json", code=2)["error"])
        short = self.cli("read-calls", "--charge", "701", "--look", self.look(), "--out", folder / "calls.json")
        self.assertEqual(short["charges"], [{"hotel": scene.HOTEL, "offer": "601", "charge": "701"}], "오퍼는 목록에서 찾는다")
        scene.write_answers(folder, "charge", [self.erp.read_charge(call) for call in short["charges"]])
        self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        text = self.cli("render", "window", "--snapshot", folder / "snapshot.json", "--text")["text"]
        for said in ("아무것도 바꾸지 않았습니다", "종류 | 레이트 체크아웃", "이름 | 레이트 체크아웃 (14시 이후 · 1박 요금의 50%)",
                     "부과 방식 | 1박 요금의 %", "의무 · 선택 | 선택", "적용 룸 · 적용 범위 | 이 오퍼의 모든 객실 · 객실: 기존 범위 그대로",
                     "설명 | 늦은 체크아웃은 프런트에 미리 말해 주세요", "12:01~14:00 시간대 · 정액 금액 | 0.00 USD | 쓰임",
                     "14:01~18:00 시간대 · 정률(%) | 50.00% | 쓰임", "부과금 · 정률(%) | 50.00% | 시간대별 요율이 있어"):
            self.assertIn(said, text)
        self.assertEqual(self.erp.posts, [], "읽기만 한다")
        db = Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3"
        self.assertFalse(db.exists() and self.cli("list", "--all")["changes"], "장부에 적지 않는다")


class AdultWordTest(Flow):
    def test_an_adult_age_band_is_refused_with_the_rule_that_the_charge_s_own_amount_is_the_adult_one(self):
        """H2 — 연령별 단가가 있는 부과금에서 「성인」은 연령 구간이 아니다. 그렇게 적은 요청은 짐작해 고치지 않고 규칙을 말하며 거절한다."""
        request = self.request({"offer": "602", "charge": "705", "age": "성인", "field": "amount"}, value="110",
                               sentence="갈라 디너 성인 요금 110 으로")
        snapshot = self.read(request=request)
        refused = self.cli("plan", "--snapshot", snapshot, "--request", request, "--out", self.work / "plan-1.json", code=2)
        self.assertIn("연령별 단가가 아니라 부과금 자체의 금액입니다", refused["error"])
        right = self.request({"offer": "602", "charge": "705", "field": "amount"}, value="110", sentence="갈라 디너 성인 요금 110 으로")
        _change, plan = self.preview(right, name="plan-2.json")
        change, = json.loads(plan.read_text(encoding="utf-8"))["plan"]["changes"]
        self.assertEqual((change["before"], change["after"]), ("100.00", "110.00"), "성인 금액은 부과금 자체의 금액이다")


class LedgerListTest(Flow):
    """H3 — 저장할 것이 없는 미리보기는 그렇게 적히고 그렇게 보이며, 목록은 탭의 호텔 것을 먼저, 다른 호텔 것은 청할 때만 싣는다."""

    def test_a_preview_whose_red_lines_are_all_declined_is_recorded_and_listed_as_nothing_to_save(self):
        request = self.request(GALA, value="130", sentence="갈라 디너 130달러로")
        first, _plan = self.preview(request)
        keep = self.file("안바꿈.json", [{"rule": "OVER_30", "choice": "keep", "said": "그럼 안 바꿀게요"}])
        declined, plan = self.preview(request, name="plan-2.json", resolutions=keep, replaces=first)
        self.assertEqual(json.loads(plan.read_text(encoding="utf-8"))["steps"], [])
        entry = self.listed()[declined]
        self.assertEqual(entry["status"], "empty", "적용을 기다리는 미리보기(previewed)로 읽히지 않는다")
        self.assertTrue(entry["scope"].endswith("· 저장할 것 없음"), entry["scope"])
        self.assertEqual(self.listed()[first]["status"], "replaced")
        self.assertIn("저장할 것이 없는 미리보기였습니다", self.cli("render", "result", "--change", declined, "--text")["text"])
        db = sqlite3.connect(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3")
        self.assertEqual(db.execute("SELECT status FROM changes WHERE id = ?", (declined,)).fetchone()[0], "empty",
                         "장부 자체에 그렇게 적힌다")
        db.close()
        include = self.file("바꿈.json", [{"rule": "OVER_30", "choice": "include", "said": "아니 그냥 130으로 해 주세요"}])
        again, _plan = self.preview(request, name="plan-3.json", resolutions=include, replaces=declined)
        self.assertEqual((self.listed()[declined]["status"], self.listed()[again]["status"]), ("replaced", "previewed"),
                         "마음을 바꾸면 다시 계산한 미리보기가 그 번호를 바꾼다")

    def test_begin_refuses_a_preview_with_nothing_to_save_even_without_the_plan_file_check(self):
        sys.path.insert(0, str(SKILL.parent / "stay-price-change" / "scripts"))
        from change_core.ledger import Ledger, LedgerError
        change, _plan = self.preview(self.request(GALA, value="90.00", sentence="갈라 디너 그대로"))
        self.assertEqual(self.listed()[change]["status"], "empty", "바뀌는 칸이 없는 미리보기도 저장할 것이 없다")
        ledger = Ledger(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3", kind="charge")
        with self.assertRaisesRegex(LedgerError, "저장할 것이 없는 미리보기"):
            ledger.begin(change, [], read_at=self.erp.clock.isoformat())

    def test_the_list_shows_the_tab_hotel_and_other_hotels_only_when_asked(self):
        sys.path.insert(0, str(SKILL.parent / "stay-price-change" / "scripts"))
        from decimal import Decimal
        from change_core.ledger import Ledger, ValueRow
        mine, _plan = self.preview(self.request(GALA, value="95"))
        other = Ledger(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3", kind="charge").record_preview(
            hotel="다른 데모 호텔", hotel_id="2", offer="", currency="USD", sentence="다른 호텔 부과금", read_at=self.erp.clock.isoformat(),
            rows=[ValueRow("charge", '{"charge":"901"}', "다른 오퍼 · 다른 부과금", "amount", "present", Decimal("10.00"))])
        tab = self.cli("list", "--look", self.look())
        self.assertEqual(([entry["id"] for entry in tab["changes"]], tab["others"], tab["hotel"]),
                         ([mine], 1, {"id": "1", "name": "데모 호텔"}))
        self.assertRegex(tab["changes"][0]["line"], rf"^장부 {mine}번 · \d+/\d+ \d\d:\d\d 미리보기 · 부과금 1개 ",
                         "K5 — 확인받는 한 줄은 세 도우미가 같은 코드로 만든다")
        every = self.cli("list", "--look", self.look(), "--all")
        self.assertEqual(([entry["id"] for entry in every["changes"]], every["others"]), ([mine, other], 0),
                         "다른 호텔의 번호는 청할 때만, 탭의 호텔 것 뒤에")
        self.assertIn("--look", self.cli("list", code=2)["error"])


class RolledBackLineTest(Flow):
    """N2 — 되돌린 변경은 목록의 줄(범위 `scope`, 그래서 확인받을 때 읽어 주는 `line` 도)이 되돌렸다고 말한다. 시운전에서는 되돌린 변경의
    줄이 「장부 1번 · … 적용 · … · 정률(%) 60 으로」로 끝나 그 60% 가 살아 있는 것처럼 읽혔다. 세 도우미가 같은 말이다
    (files.record_progress)."""

    def test_a_partly_then_fully_rolled_back_change_says_so_with_the_records_that_did_it(self):
        change, plan = self.preview(self.request(LATE_BAND, GALA, percent="10", sentence="레이트 체크아웃이랑 갈라 디너 10% 올려줘"))
        self.apply(change, plan)
        part = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--charge", "703", "--record",
                        "--sentence", "갈라 디너만 되돌려", "--out", self.work / "rollback-1.json")
        self.apply(part["change_id"], self.work / "rollback-1.json")
        entry = self.listed()[change]
        self.assertEqual(entry["status"], "partly_rolled_back")
        self.assertTrue(entry["line"].endswith(f" · 일부 되돌림 1/2칸 (장부 {part['change_id']}번) · 나머지 1칸은 넣은 값 그대로"),
                        entry["line"])
        rest = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--charge", "701", "--record",
                        "--sentence", "나머지도 되돌려", "--out", self.work / "rollback-2.json")
        self.apply(rest["change_id"], self.work / "rollback-2.json")
        entry = self.listed()[change]
        self.assertEqual(entry["status"], "rolled_back")
        self.assertTrue(entry["line"].endswith(f" · 모두 되돌림 2/2칸 (장부 {part['change_id']}번, {rest['change_id']}번)"),
                        entry["line"])
        self.assertEqual(entry["line"], f"장부 {change}번 · {entry['line'].split(' · ')[1]} · {entry['scope']}")


class LookItemsTest(Flow):
    """N4 — 고를 부과금의 번호와 이름은 `look` 명령의 짧은 답(`items`)에 있다: 오퍼 번호와 이름 · 부과금 번호와 이름 · 종류 · 금액 줄
    (시간대 줄의 시각 · 연령별 단가 이름). 목록이 길면 `--find` 로 담당자의 낱말이 든 것만 받는다(파일은 그대로 전부)."""

    def test_the_short_answer_lists_the_charges_with_numbers_and_a_word_narrows_it(self):
        scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
        short = self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        listing = json.loads((self.work / "look.json").read_text(encoding="utf-8"))
        self.assertEqual(len(short["items"]), len(listing["charges"]))
        self.assertNotIn("more", short)
        late = next(item for item in short["items"] if item["charge"] == "701")
        self.assertEqual((late["offer"], late["offer_name"], late["kind"], late["amount"][1]),
                         ("601", "데모 오퍼 2027", "레이트 체크아웃", "14:01 ~ 18:00 · 1박 요금의 %: 50.00%"),
                         "요청 파일에 옮길 번호와 시간대 줄의 시각이 짧은 답에 있다")
        found = self.cli("look", "--answers", self.work / "look", "--find", "레이트", "--out", self.work / "look-2.json")
        self.assertEqual((found["found"], [item["charge"] for item in found["items"]]),
                         (sum("레이트" in " ".join((c["name"], c["kind"])) for c in listing["charges"]),
                          [c["id"] for c in listing["charges"] if "레이트" in " ".join((c["name"], c["kind"]))]))
        self.assertIn("701", [item["charge"] for item in found["items"]])
        self.assertEqual(json.loads((self.work / "look-2.json").read_text(encoding="utf-8")), listing, "파일은 좁히지 않는다")


class OneLedgerTest(Flow):
    def test_the_other_helpers_list_a_charge_change_with_the_same_line_and_do_not_touch_it(self):
        """P1 — 장부는 하나다. 다른 두 도우미의 목록에도 이 변경이 같은 줄로 나오고, 그 번호로 무엇을 하려 하면 부과금 도우미의
        기록이라며 거절한다."""
        change, plan = self.preview(self.request(LATE_BAND, value="60"))
        self.apply(change, plan)
        mine, = self.cli("list", "--all")["changes"]
        self.assertEqual((mine["item_kind"], mine["helper"]), ("charge", "부과금 도우미"))
        for script in (PRICE_SCRIPT, ADDON_SCRIPT):
            self.assertEqual(self.cli("list", "--all", script=script)["changes"], [mine])
            self.assertIn("부과금 도우미의 기록", self.cli("calls", "--change", change, script=script, code=2)["error"])
        db = sqlite3.connect(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3")
        kinds = {row[0] for row in db.execute("SELECT DISTINCT item_kind FROM item_values")}
        keys = {row[0] for row in db.execute("SELECT DISTINCT item_key FROM item_values")}
        db.close()
        self.assertEqual(kinds, {"charge"})
        self.assertEqual(keys, {'{"charge":"701"}', '{"charge":"701","time":"12:01-14:00"}', '{"charge":"701","time":"14:01-18:00"}'})


class ReadAgainTest(Flow):
    """검토 1 — begin 은 그 번호를 계산한 뒤에 읽은 값만, check 는 장부가 그 번호에 마지막으로 적은 것 뒤에 읽은 값만 받는다
    (change_core.ledger). 미리보기의 읽은 값 그대로, 그 읽기 폴더의 앞선 답을 다시 묶은 읽기, 저장 결과보다 앞선 적용 직전의 읽은 값은
    거절하고 아무것도 시작하거나 가리지 않는다. 새로 읽으면 된다."""

    def test_begin_and_check_take_only_a_reading_made_after_what_the_ledger_last_wrote(self):
        change, plan = self.preview(self.request(GALA, value="100"))
        own = self.work / "읽기-1" / "snapshot.json"
        bound_again = own.parent / "snapshot-again.json"
        self.cli("read", "--calls", own.parent / "calls.json", "--answers", own.parent, "--out", bound_again)
        for reading in (own, bound_again):
            refused = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", reading, code=2)["error"]
            self.assertIn(f"{change}번을 계산한 때", refused, reading.name)
            self.assertIn("뒤에 읽은 것이 아닙니다", refused, reading.name)
        self.assertIn("begin", self.cli("calls", "--change", change, code=2)["error"], "아무것도 시작하지 않았다")

        before = self.read(record=change)
        self.assertEqual(self.cli("begin", "--change", change, "--plan", plan, "--snapshot", before)["status"], "applying")
        call = self.cli("calls", "--change", change)["calls"][0]
        self.cli("record-result", "--change", change, "--result", self.file("refused.json", self.erp.apply(call["payload"], False)))
        refused = self.cli("check", "--change", change, "--snapshot", before, code=2)["error"]
        self.assertIn("마지막으로 적은 저장 결과", refused, "적용 직전의 읽은 값은 그 뒤의 저장을 모른다")
        self.assertEqual(self.cli("check", "--change", change, "--snapshot", self.read(record=change))["cause"], "failed")


class UndoOnceTest(Flow):
    """검토 3 — 되돌리기는 다시 되돌리지 않는다(change_core.ledger 의 _undoable). 거절하고 아무것도 적지 않으며, 목록의 「모두 되돌림」과
    「되돌릴 것이 없습니다」는 ERP 에 살아 있는 값(바꾸기 전 값)과 같다."""

    def test_a_rollback_is_not_rolled_back_again_and_the_list_stays_true(self):
        change, plan = self.preview(self.request(GALA, value="100"))
        self.apply(change, plan)
        back = self.work / "rollback-1.json"
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record", "--out", back)["change_id"]
        self.apply(rollback, back)
        again = self.work / "rollback-2.json"
        refused = self.cli("rollback", "--change", rollback, "--snapshot", self.read(record=rollback), "--record", "--out", again,
                           code=2)["error"]
        self.assertIn(f"{rollback}번은 {change}번 되돌리기입니다 — 되돌리기는 다시 되돌리지 않습니다", refused)
        self.assertFalse(again.exists())
        rows = {entry["id"]: entry for entry in self.cli("list", "--all")["changes"]}
        self.assertEqual((sorted(rows), rows[change]["status"], rows[change]["undone_by"]), ([change, rollback], "rolled_back", [rollback]))
        self.assertIn("아직 되돌리지 않은 것이 없습니다",
                      self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), code=2)["error"])


if __name__ == "__main__":
    unittest.main()
