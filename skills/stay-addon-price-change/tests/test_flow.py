"""명령으로 한 바퀴(X1~X6) — 페이지 답은 addon_scene 의 작은 ERP 가 만든다(진짜 페이지 모듈의 답과 같은 모양, test_golden).

읽기 → 두 줄 10% → 미리보기 → 적용 직전 다시 읽기 → begin → 저장 → 다시 읽어 견주기 → 되돌리기 → 견주기. 그리고 그 길에서
벗어나는 때: 적용 직전에 편집 창의 값이 달라짐(아무것도 저장 안 함), 저장이 공급 원가를 지움(견주기가 짚음), 그 사이 바뀐 줄은
되돌리지 않고 세 값과 까닭을 댐, 멈춘 변경, 같은 장부의 가격 캘린더 도우미가 이 변경을 보지도 만지지도 않음.

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

import addon_scene as scene

SKILL = Path(__file__).resolve().parent.parent
SCRIPT = SKILL / "scripts" / "addon_change.py"
PRICE_SCRIPT = SKILL.parent / "stay-price-change" / "scripts" / "price_change.py"
BOTH = [{"addon": "201", "line": "301"}, {"addon": "203", "line": "304"}]


class Flow(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.work = Path(self.folder.name) / "작업"
        self.work.mkdir()
        self.env = dict(os.environ, STAY_PRICE_LEDGER_DIR=str(Path(self.folder.name) / "기록"))
        self.erp = scene.Erp()
        self.readings = 0

    def tearDown(self):
        self.folder.cleanup()

    def cli(self, *args, script=SCRIPT, code=0):
        done = subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, f"{args[0]}: {done.stderr or done.stdout}")
        return json.loads(done.stdout) if code in (0, 1) else json.loads(done.stderr)

    def file(self, name, data) -> Path:
        path = self.work / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def request(self, name="request.json", lines=BOTH, **change):
        change = change or {"percent": "10"}
        return self.file(name, dict(kind="addon_change", hotel=scene.HOTEL, lines=lines, field=change.pop("field", "sell"),
                                    sentence="조식 · 엑스트라베드 10% 올려줘", **change))

    def read(self, **scope) -> Path:
        """읽기 한 번 — read-calls → 줄마다 readLine 답 → read. 지금 값 파일의 자리를 돌려준다."""
        self.readings += 1
        folder = self.work / f"읽기-{self.readings}"
        folder.mkdir()
        flags = ["--record", scope["record"]] if "record" in scope else ["--request", scope["request"]]
        self.cli("read-calls", *flags, "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["lines"]
        scene.write_answers(folder, "line", [self.erp.read_line(call) for call in calls])
        self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        return folder / "snapshot.json"

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
            results.append(self.cli("record-result", "--change", change, "--result", self.file(f"적용-{change}-{call['no']}.json", answer)))
        return results


class EndToEndTest(Flow):
    def test_read_change_two_lines_preview_begin_save_verify_rollback_verify(self):
        # X1 — 호텔의 부가옵션과 줄 전부(누르는 것은 탭뿐 — 페이지 시험이 본다)
        scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
        look = self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        self.assertEqual((look["addons"], look["lines"], look["currency"]), (3, 4, "USD"))

        # X2 — 두 줄 판매가 10%, 셈은 명령이 한다
        change, plan = self.preview(self.request())
        data = json.loads(plan.read_text(encoding="utf-8"))
        self.assertEqual((data["counts"]["will_change"], data["counts"]["red"], data["counts"]["blocked"]), (2, 0, 0))
        moves = {item["line"]["listed"]["line"]: (item["after"]["sell"], item["after"]["supply"]) for item in data["plan"]["changes"]}
        self.assertEqual(moves, {"301": ("22.00", "15.00"), "304": ("33.00", "25.00")})
        page = self.cli("render", "preview", "--plan", plan, "--text", "--out", self.work / "미리보기.html")
        self.assertIn("20.00 → 22.00", page["text"])
        self.assertIn("15.00 그대로", page["text"], "바뀌지 않는 공급 원가는 그대로라고 보인다")
        self.assertIn("ERP 손입력", page["text"], "되돌릴 수 없는 출처 표시를 적용 전에 말한다")

        # X3 — 적용: 저장은 줄마다 한 번, 바꾸지 않는 칸은 창이 보인 그대로(공급 원가 포함)
        results = self.apply(change, plan)
        self.assertEqual([(item["saved"], item["status"]) for item in results], [(True, "applying"), (True, "applied")])
        self.assertEqual([dict(post)["price"] for post in self.erp.posts], ["22.00", "33.00"])
        self.assertEqual([dict(post)["net_amount"] for post in self.erp.posts], ["15.00", "25.00"], "공급 원가를 비워 보내지 않았다")
        self.assertEqual([dict(post)["season"] for post in self.erp.posts], ["41", ""], "다른 칸은 읽은 그대로")

        # X4 — 다시 읽어 견주기, 결과 페이지
        after = self.read(record=change)
        verified = self.cli("verify", "--change", change, "--snapshot", after)
        self.assertEqual((verified["same"], verified["mismatches"], verified["moved"]), (True, [], []))
        result = self.cli("render", "result", "--change", change, "--snapshot", after, "--text", "--out", self.work / "결과.html")
        self.assertIn("적용했고, 다시 읽어 확인했습니다", result["text"])

        # 되돌리기 → 견주기
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                            "--sentence", "방금 것 되돌려", "--out", self.work / "rollback-1.json")
        self.assertEqual((rollback["restored"], rollback["kept"], rollback["saves"]), (2, 0, 2))
        back = rollback["change_id"]
        self.assertEqual([item["saved"] for item in self.apply(back, self.work / "rollback-1.json")], [True, True])
        self.assertEqual(self.cli("verify", "--change", back, "--snapshot", self.read(record=back))["same"], True)
        self.assertEqual({key: (item["sell"], item["supply"]) for key, item in self.erp.lines.items() if key in ("301", "304")},
                         {"301": ("20.00", "15.00"), "304": ("30.00", "25.00")})
        listed = {entry["id"]: entry for entry in self.cli("list")["changes"]}
        self.assertEqual((listed[change]["status"], listed[back]["status"]), ("rolled_back", "applied"))
        self.assertIn("판매가 +10%", listed[change]["scope"])


class FreshReadingTest(Flow):
    def test_a_window_showing_another_sell_price_than_the_reading_saves_nothing_and_asks_for_a_new_preview(self):
        change, plan = self.preview(self.request())
        self.erp.lines["301"]["sell"] = "21.00"            # 미리보기 뒤 누가 ERP 에서 고침
        answer = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        self.assertEqual((answer["same"], answer["status"]), (False, "previewed"))
        self.assertEqual([item["key"]["line"] for item in answer["differences"]], ["301"])
        self.assertEqual(self.erp.posts, [], "아무것도 저장하지 않았다")
        self.cli("calls", "--change", change, code=2)

    def test_a_changed_field_the_helper_does_not_touch_also_stops_the_start(self):
        change, plan = self.preview(self.request())
        self.erp.lines["304"]["description"] = "1박 기준"
        answer = self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change), code=1)
        moved, = answer["differences"]
        self.assertEqual((moved["then"]["others"]["form.description"], moved["now"]["others"]["form.description"]), ("", "1박 기준"))

    def test_a_save_that_cleared_the_supply_cost_is_caught_by_the_check_after_applying(self):
        change, plan = self.preview(self.request(lines=BOTH[:1]))
        self.apply(change, plan)
        self.erp.lines["301"]["supply"] = ""             # ERP 가 저장하며 원가를 지웠다고 치자
        verified = self.cli("verify", "--change", change, "--snapshot", self.read(record=change), code=1)
        self.assertEqual(verified["mismatches"], [], "넣은 판매가는 맞다")
        self.assertEqual([item["what"] for item in verified["moved"]], ["공급 원가 15.00 → 없음"])


class RollbackKeepsTest(Flow):
    def test_lines_changed_since_are_kept_with_the_three_values_and_the_cause(self):
        change, plan = self.preview(self.request())
        self.apply(change, plan)
        self.erp.lines["304"]["sell"] = "40.00"           # 도우미 밖에서 고침
        out = self.work / "rollback-1.json"
        short = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--out", out)
        self.assertEqual((short["restored"], short["kept"]), (1, 1))
        self.assertEqual(short["kept_why"], [{"change_id": None, "at": None, "sentence": None, "outside": True, "lines": 1}])
        kept, = json.loads(out.read_text(encoding="utf-8"))["rollback"]["kept"]
        self.assertEqual((kept["recorded"], kept["written"], kept["now"]["fields"]["sell"]),
                         ({"sell": "30.00"}, {"sell": "33.00"}, "40.00"))
        page = self.cli("render", "rollback", "--plan", out, "--text", "--out", self.work / "되돌리기.html")["text"]
        self.assertIn("도우미 밖에서 바뀜", page)
        self.assertIn("ERP 손입력", page, "되돌려도 출처 표시는 돌아오지 않는다고 말한다")

    def test_the_rollback_answer_carries_the_scope_line_that_list_shows_and_the_confirmation_reads(self):
        change, plan = self.preview(self.request())
        self.apply(change, plan)
        snapshot = self.read(record=change)
        loose = self.cli("rollback", "--change", change, "--snapshot", snapshot, "--line", "304", "--out", self.work / "rollback-0.json")
        short = self.cli("rollback", "--change", change, "--snapshot", snapshot, "--line", "304", "--record",
                         "--out", self.work / "rollback-1.json")
        entry, = [item for item in self.cli("list")["changes"] if item["id"] == short["change_id"]]
        self.assertEqual(short["scope"], entry["scope"])
        self.assertEqual(loose["scope"], entry["scope"], "장부에 적지 않아도 같은 줄이다")
        self.assertEqual(short["scope"], f"부가옵션 가격 줄 1개 (데모 오퍼 2027 · 엑스트라베드 · 엑스트라베드 1개 · 전체) · "
                                         f"{change}번 되돌리기 (가격 줄 304번만)")
        page = self.cli("render", "rollback", "--plan", self.work / "rollback-1.json", "--text", "--out", self.work / "되돌리기.html")
        self.assertIn(f"되돌리는 범위: {short['scope']}", page["text"])

    def test_a_later_change_by_the_helper_is_named_as_the_cause(self):
        first, plan = self.preview(self.request())
        self.apply(first, plan)
        second, plan2 = self.preview(self.request("request-2.json", lines=BOTH[1:], value="45.00"), "plan-2.json",
                                     resolutions=self.file("고름.json", [{"rule": "OVER_30", "choice": "include"}]))
        self.apply(second, plan2)
        short = self.cli("rollback", "--change", first, "--snapshot", self.read(record=first), "--out", self.work / "rollback-1.json")
        self.assertEqual([(item["change_id"], item["outside"]) for item in short["kept_why"]], [(second, False)])

    def test_a_supply_cost_the_helper_put_on_a_line_that_had_none_is_cleared_again_on_rollback(self):
        self.erp = scene.Erp(scene.demo_lines() + [scene.line("205", "늦은 체크아웃", "306", "18시까지", "50.00", "")])
        line = [{"addon": "205", "line": "306"}]
        change, plan = self.preview(self.request(lines=line, field="supply", value="12.00"))
        self.apply(change, plan)
        self.assertEqual(self.erp.lines["306"]["supply"], "12.00")
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                            "--out", self.work / "rollback-1.json")
        step, = json.loads((self.work / "rollback-1.json").read_text(encoding="utf-8"))["steps"]
        self.assertEqual(step["set"], {"net_amount": ""}, "적어 둔 원가가 없던 줄은 원가를 비워 되돌린다")
        self.apply(rollback["change_id"], self.work / "rollback-1.json")
        self.assertEqual(self.erp.lines["306"]["supply"], "")

    def test_the_cost_is_cleared_only_when_asked_and_rollback_puts_it_back(self):
        line = [{"addon": "201", "line": "302"}]
        change, plan = self.preview(self.request(lines=line, field="supply", clear=True))
        self.apply(change, plan)
        self.assertEqual(self.erp.lines["302"]["supply"], "", "담당자가 비우라고 했을 때만 비운다")
        rollback = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record",
                            "--out", self.work / "rollback-1.json")
        self.apply(rollback["change_id"], self.work / "rollback-1.json")
        self.assertEqual(self.erp.lines["302"]["supply"], "28.00")


class StoppedTest(Flow):
    def test_a_failed_save_stops_and_check_lets_the_rest_continue_after_a_fresh_reading(self):
        change, plan = self.preview(self.request())
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
        change, plan = self.preview(self.request())
        self.cli("begin", "--change", change, "--plan", plan, "--snapshot", self.read(record=change))
        db = sqlite3.connect(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3")
        with db:
            db.execute("UPDATE changes SET active_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (change,))
        db.close()
        self.assertIn("멈춰 있습니다", self.cli("calls", "--change", change, code=2)["error"])
        report = self.cli("check", "--change", change, "--snapshot", self.read(record=change))
        self.assertEqual((report["cause"], report["can_continue"]), ("cut_off", True))
        self.assertEqual(len(self.cli("calls", "--change", change)["calls"]), 2)


class OneLedgerTest(Flow):
    def test_the_price_calendar_helper_neither_lists_nor_touches_an_add_on_change_in_the_same_ledger(self):
        change, plan = self.preview(self.request())
        self.apply(change, plan)
        self.assertEqual(self.cli("list", script=PRICE_SCRIPT)["changes"], [])
        refused = self.cli("calls", "--change", change, script=PRICE_SCRIPT, code=2)
        self.assertIn("부가옵션 가격 도우미의 기록", refused["error"])
        db = sqlite3.connect(Path(self.env["STAY_PRICE_LEDGER_DIR"]) / "가격장부.sqlite3")
        kinds = {row[0] for row in db.execute("SELECT DISTINCT item_kind FROM item_values")}
        fields = {row[0] for row in db.execute("SELECT DISTINCT field FROM item_values")}
        db.close()
        self.assertEqual((kinds, fields), ({"addon_price"}, {"sell", "supply"}))


class NothingToSaveTest(Flow):
    """F7 — 빨간 줄을 모두 「그 줄은 안 바꿈」으로 골라 바꿀 줄이 없는 미리보기(`saves` 0)는 어디서나 그렇게 말한다: 짧은 답, 페이지,
    안내문. "적용"을 청하지 않고, begin 이 받지 않는다(첫 실호텔 시험의 모양 — 공급 원가 아래의 새 값 → 안 바꿈)."""

    def test_keeping_every_red_line_saves_nothing_asks_for_nothing_and_begin_refuses_the_record(self):
        request = self.request(lines=BOTH[:1], value="14.00")
        first, _plan = self.preview(request)
        snapshot = self.read(request=request)
        plan = self.work / "plan-2.json"
        short = self.cli("plan", "--snapshot", snapshot, "--request", request, "--record", "--replaces", first,
                         "--resolutions", self.file("고름.json", [{"rule": "BELOW_COST", "choice": "keep"}]), "--out", plan)
        self.assertEqual((short["saves"], short["counts"]["will_change"], short["counts"]["red"], short["counts"]["unchanged"]),
                         (0, 0, 0, 1))

        text = self.cli("render", "preview", "--plan", plan, "--text", "--out", self.work / "미리보기.html")["text"]
        self.assertIn("바꿀 줄이 없어 적용할 것이 없습니다", text)
        self.assertIn("고르신 대로 그대로 둡니다(저장하지 않습니다)", text, "줄에서도 저장하지 않는다고 말한다")
        for said in ("저장 0번", '"적용"이라고 해 주세요', "저장은 줄마다 한 번"):
            self.assertNotIn(said, text, "저장할 것이 없는 미리보기는 저장한다고도, 적용하라고도 말하지 않는다")

        refused = self.cli("begin", "--change", short["change_id"], "--plan", plan, "--snapshot",
                           self.read(record=short["change_id"]), code=2)
        self.assertIn("바꿀 줄이 없어 적용할 것이 없습니다", refused["error"], "빨간 줄을 고르라는 말이 아니다")
        entry, = [item for item in self.cli("list")["changes"] if item["id"] == short["change_id"]]
        self.assertEqual((entry["status"], entry["steps"]), ("previewed", 0), "begin 이 받지 않아 아무것도 시작하지 않았다")
        self.assertEqual(self.erp.posts, [])

        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        step = skill[skill.index("**읽고 미리보기.**"):skill.index("## 3. 되돌리기")]
        self.assertIn("`saves` 가 0 이면 저장할 것이 없다", step)
        self.assertIn('"적용"을 청하지 않는다', step)


class ScopeCardTest(Flow):
    """F8 — 짧은 답이 편집 창에 적용 범위 카드가 있는지 말하고(`scope_card` — 도우미가 적용 범위 기록 한 문장을 말할 때), 미리보기의
    「그대로 다시 보내는 칸」은 적용 범위를 그 값으로 보인다."""

    def plan(self, lines, k):
        change, plan = self.preview(self.request(f"request-{k}.json", lines=lines), f"plan-{k}.json")
        return json.loads(plan.read_text(encoding="utf-8")), self.cli("render", "preview", "--plan", plan, "--text",
                                                                      "--out", self.work / f"미리보기-{k}.html")["text"]

    def test_the_short_answer_says_whether_a_saved_line_has_a_scope_card_and_the_page_shows_its_values(self):
        self.erp = scene.Erp(scene.demo_lines() + [scene.line("205", "늦은 체크아웃", "306", "18시까지", "50.00", "40.00", scope=False)])
        data, text = self.plan(BOTH[:1], 1)
        self.assertIs(data["scope_card"], True)
        self.assertIn("설명 비어 있음 · 적용 범위 요금제 기존 범위 그대로 · 객실 기존 범위 그대로", text)
        self.assertIn("적용 범위 기록이 없으면 하나 만듭니다", text)
        request = self.work / "request-1.json"
        short = self.cli("plan", "--snapshot", self.read(request=request), "--request", request, "--out", self.work / "짧은.json")
        self.assertIs(short["scope_card"], True, "짧은 답에도 있다")

        data, text = self.plan([{"addon": "205", "line": "306"}], 2)
        self.assertIs(data["scope_card"], False)
        row, = [line for line in text.splitlines() if "가격 줄 306번" in line]
        self.assertTrue(row.endswith("설명 비어 있음"), f"카드가 없는 줄은 적용 범위를 보내지 않는다: {row}")
        self.assertNotIn("적용 범위 기록", text, "적용 범위 기록을 만들 수 있다는 말도 없다")


class SameNameTest(Flow):
    """F6 — 오퍼마다 이름 · 줄 이름 · 적용 대상이 같은 부가옵션이 있다(첫 실호텔 시험의 모양). 담당자에게 줄을 말하는 곳마다 오퍼로
    가른다: 빨간 줄의 예, 미리보기, 결과, 장부 목록(범위 · 오퍼), 되돌리기 미리보기."""

    SPRING, SUMMER = "데모 봄 오퍼", "데모 여름 오퍼"
    TWINS = [{"addon": "204", "line": "680"}, {"addon": "205", "line": "681"}]

    def setUp(self):
        super().setUp()
        self.erp = scene.Erp([scene.line("204", "성인 엑스트라베드", "680", "성인 엑스트라베드 1개", "30.00", "25.00", offer=self.SPRING),
                              scene.line("205", "성인 엑스트라베드", "681", "성인 엑스트라베드 1개", "30.00", "25.00", offer=self.SUMMER)])

    def page(self, kind, *flags, name):
        return self.cli("render", kind, *flags, "--text", "--out", self.work / name)["text"]

    def test_every_place_that_names_a_line_tells_two_same_named_add_ons_apart_by_their_offer(self):
        spring = f"{self.SPRING} · 성인 엑스트라베드 · 성인 엑스트라베드 1개 · 전체"
        _first, below = self.preview(self.request(lines=self.TWINS[:1], value="20.00"))
        red, = json.loads(below.read_text(encoding="utf-8"))["red"]
        self.assertEqual(red["examples"][0]["name"], spring, "빨간 줄의 예가 그 줄을 오퍼로 부른다")

        change, plan = self.preview(self.request("request-2.json", lines=self.TWINS[:1], percent="10"), "plan-2.json")
        preview = self.page("preview", "--plan", plan, name="미리보기.html")
        self.assertIn(spring, preview)
        self.assertNotIn(self.SUMMER, preview)
        self.apply(change, plan)
        result = self.page("result", "--change", change, name="결과.html")
        self.assertIn(spring, result)
        other, _ = self.preview(self.request("request-3.json", lines=self.TWINS[1:], percent="10"), "plan-3.json")

        listed = {entry["id"]: entry for entry in self.cli("list")["changes"]}
        self.assertEqual((listed[change]["offer"], listed[other]["offer"]), (self.SPRING, self.SUMMER))
        self.assertIn(f"({spring})", listed[change]["scope"])
        self.assertIn(f"({self.SUMMER} · 성인 엑스트라베드 · 성인 엑스트라베드 1개 · 전체)", listed[other]["scope"])

        out = self.work / "rollback-1.json"
        back = self.cli("rollback", "--change", change, "--snapshot", self.read(record=change), "--record", "--out", out)
        self.assertIn(spring, self.page("rollback", "--plan", out, name="되돌리기.html"))
        self.assertIn(f"({spring})", {e["id"]: e for e in self.cli("list")["changes"]}[back["change_id"]]["scope"],
                      "되돌리기 확인이 읽는 줄도 오퍼로 가른다")

        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("오퍼 이름(`offer`)부터 댄다", skill, "안내문이 담당자에게 줄을 오퍼로 말하라고 한다")


class PageObjectTest(Flow):
    def test_a_reading_with_pieces_still_to_take_tells_the_helper_to_call_this_helpers_take(self):
        scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)[:1]])
        error = self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json", code=2)
        self.assertIn("stayAddonPrice.take('blook', 0, 800)", error["error"])
        self.assertNotIn("stayPrice.take(", error["error"], "이 도우미는 가격 캘린더 도우미의 페이지 모듈을 부르지 않는다")
        self.assertEqual([item["id"] for item in error["refetch"]], ["blook"])

        folder = self.work / "읽기-1"
        folder.mkdir()
        self.cli("read-calls", "--request", self.request(), "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["lines"]
        scene.write_answers(folder, "line", [self.erp.read_line(call)[:1] for call in calls])
        error = self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json", code=2)
        self.assertEqual(error["error"].count("stayAddonPrice.take("), 2, error["error"])
        self.assertNotIn("stayPrice.take(", error["error"])


class TrapLineTest(Flow):
    def test_a_line_whose_amount_records_the_screen_cannot_see_is_never_saved(self):
        request = self.file("request.json", dict(kind="addon_change", hotel=scene.HOTEL, all=True, field="sell", percent="5",
                                                 sentence="부가옵션 전부 5% 올려줘"))
        scene.write_answers(self.work / "look", "look", [scene.look_answer(self.erp)])
        self.cli("look", "--answers", self.work / "look", "--out", self.work / "look.json")
        self.readings += 1
        folder = self.work / f"읽기-{self.readings}"
        folder.mkdir()
        self.cli("read-calls", "--request", request, "--look", self.work / "look.json", "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))["lines"]
        self.assertEqual(len(calls), 4)
        scene.write_answers(folder, "line", [self.erp.read_line(call) for call in calls])
        short = self.cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        self.assertEqual(short["doubt"], ["303"])
        plan = self.cli("plan", "--snapshot", folder / "snapshot.json", "--request", request, "--record",
                        "--out", self.work / "plan-1.json")
        self.assertEqual([(item["line"], item["rule"]) for item in plan["blocked"]], [("303", "HIDDEN")])
        self.assertEqual(plan["saves"], 3)
        steps = json.loads((self.work / "plan-1.json").read_text(encoding="utf-8"))["steps"]
        self.assertNotIn("303", [step["line"] for step in steps])


if __name__ == "__main__":
    unittest.main()
