"""명령 한 바퀴 — 화면 조각 읽기, 미리보기, 페이지, 낡음 확인, 적용 시작, 저장마다 적기, 확인, 되돌리기, 목록.

    python3 -m unittest discover -s tests

장부는 `STAY_PRICE_LEDGER_DIR` 로 임시 폴더에 둔다.
"""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from change_core.answers import ask_sum  # noqa: E402
from change_core.ledger import DB_NAME  # noqa: E402
from price_browser import PAGE_KEEPS  # noqa: E402
from price_model import CellKey, Snapshot, decode_snapshot, decode_step, encode_request, encode_snapshot  # noqa: E402


def answer(call, **over):
    """페이지가 그 저장 단계를 저장했다고 돌려준 답(stayPrice.applyBulk · applyCell 의 모양)."""
    return dict({"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True,
                 "note": "저장했습니다"}, **over)


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = scene.env(str(self.dir / "기록"))
        self.snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        self.request = self.write("request.json", encode_request(scene.request()))
        self.choice = self.write("resolutions.json", [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": "정가도 같이 올려"}])

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def write_text(self, name, text):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def test_read_builds_a_snapshot_from_fragments(self):
        erp = HERE / "fixtures" / "erp"
        adjust = (erp / "adjust-rejected.html").read_text(encoding="utf-8").replace("<td>스위트</td>", "<td>디럭스</td>")
        result = self.run_cli("read", "--hotel", "데모 호텔", "--hotel-id", "1", "--price-page", f"디럭스={erp / 'price-runs-closed-absent-list.html'}",
                              "--adjust-page", self.write_text("adjust.html", adjust), "--read-at", "2026-11-20T14:02:00+09:00",
                              "--out", self.dir / "read.json")
        snapshot = decode_snapshot(json.loads((self.dir / "read.json").read_text(encoding="utf-8")))
        self.assertEqual((result["offer"], len(snapshot.cells), snapshot.currency), ("샘플 오퍼", 16, "USD"))
        self.assertIn(("디럭스", "2026-12-24"), snapshot.reserved)
        error = self.run_cli("read", "--hotel", "H", "--hotel-id", "9", "--price-page", f"디럭스={erp / 'calendar-adjust--step2.html'}", code=2)
        self.assertIn("가격 수정", error["error"])
        self.assertIn("캘린더의 객실 이름=파일", self.run_cli("read", "--hotel", "H", "--hotel-id", "9", "--price-page", erp / "calendar-adjust--step2.html", code=2)["error"])

    def brief(self, *args):
        """`--out` 을 준 명령 → (표준 출력의 짧은 답, 파일의 온 답, 표준 출력의 글자)."""
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = Path(str(args[args.index("--out") + 1]))
        short = json.loads(done.stdout)
        self.assertEqual(short["out"], str(out.resolve()), "짧은 답은 온 답이 있는 파일을 말한다")
        return short, json.loads(out.read_text(encoding="utf-8")), done.stdout

    def test_y6_commands_that_write_a_file_answer_briefly_and_never_with_the_cell_list(self):
        short, whole, text = self.brief("read-calls", "--request", self.request, "--out", self.dir / "calls.json")
        self.assertEqual((short["pairs"], short["reads"]["readPair"]), (whole["pairs"], len(whole["pairs"])),
                         "readPair 에 그대로 넣을 값은 싣는다")
        self.assertNotIn("reserved", short)

        erp = HERE / "fixtures" / "erp"
        short, whole, text = self.brief("read", "--hotel", "데모 호텔", "--hotel-id", "1",
                                        "--price-page", f"디럭스={erp / 'price-runs-closed-absent-list.html'}",
                                        "--read-at", "2026-11-20T14:02:00+09:00", "--out", self.dir / "read.json")
        self.assertEqual((short["cells"], short["read_at"], short["dates"]["count"]),
                         (len(whole["cells"]), "2026-11-20T14:02:00+09:00", len(whole["dates"])))
        self.assertNotIn('"rate_plan"', text, "칸 목록을 싣지 않는다")
        self.assertEqual(short["rooms"], [{"room": "디럭스", "drawer": "샘플 오퍼 · 디럭스"}],
                         "F3 — 요금표의 객실을 맞출 때 ERP 가 그 객실을 부르는 이름 둘(캘린더 칩 · 가격 수정 창)")

        short, whole, text = self.brief("plan", "--snapshot", self.snapshot, "--request", self.request, "--record",
                                        "--out", self.dir / "plan-1.json")
        self.assertEqual((short["counts"]["red"], short["saves"], [line["rule"] for line in short["red"]]), (2, None, ["ABOVE_LIST"]))
        self.assertEqual(short["red"][0]["choices"][0]["example"],
                         "1/1 금 · 스위트 · 조식 포함 · 성인 2 · 1박 이상 — 정가 500.00 → 550.00")
        self.assertEqual(len(whole["plan"]["changes"]), 90)
        for bulky in ('"plan"', '"unresolved"', '"steps"', '"before"', '"tiers"'):
            self.assertNotIn(bulky, text, f"plan 의 짧은 답에 {bulky} 가 없다")
        short, whole, text = self.brief("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                                        "--record", "--replaces", short["change_id"], "--out", self.dir / "plan-2.json")
        self.assertEqual((short["saves"], [line["words"] for line in short["chosen"]]), (len(whole["steps"]), ["정가도 10% 올림"]))

        change = short["change_id"]
        fresh = self.write("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan-2.json", "--snapshot", fresh)
        for call in self.run_cli("calls", "--change", change)["calls"]:
            self.run_cli("record-result", "--change", change, "--result", self.write(f"r{call['no']}.json", answer(call)))
        after = scene.applied(scene.snapshot(), map(decode_step, whole["steps"]))
        key = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1)
        moved = self.write("moved.json", encode_snapshot(replace(after, cells={**after.cells, key: replace(after.cells[key], sell=D("1.00"))})))
        short, whole, text = self.brief("rollback", "--change", change, "--snapshot", moved, "--record", "--out", self.dir / "rollback-1.json")
        self.assertEqual((short["restored"], short["kept"], short["saves"], short["reserved"]),
                         (len(whole["rollback"]["restored"]), 1, len(whole["steps"]), 23))
        self.assertEqual([(why["outside"], why["cells"]) for why in short["kept_why"]], [(True, 1)], "그대로 두는 까닭마다의 수")
        self.assertNotIn('"rollback": {', text)
        saved = self.run_cli("save-snapshot", "--snapshot", self.snapshot)["change_id"]
        short, whole, text = self.brief("restore", "--saved", saved, "--snapshot", moved, "--record", "--out", self.dir / "rollback-2.json")
        self.assertEqual((short["mode"], short["restored"]), ("restore", len(whole["rollback"]["restored"])))
        self.assertNotIn('"targets"', text)

    def test_render_text_gives_the_words_the_page_shows_and_writes_no_file(self):
        self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--out", self.dir / "plan-1.json")
        page = Path(self.run_cli("render", "preview", "--plan", self.dir / "plan-1.json")["page"])
        before = sorted(page.parent.iterdir())
        shown = self.run_cli("render", "preview", "--plan", self.dir / "plan-1.json", "--text")
        self.assertEqual(sorted(page.parent.iterdir()), before, "F9 — 글을 읽는 것은 「… (2).html」 같은 새 파일을 만들지 않는다")
        self.assertEqual(set(shown), {"text"})
        self.assertIn("--out 과 같이 주지 않습니다", self.run_cli("render", "preview", "--plan", self.dir / "plan-1.json", "--text",
                                                         "--out", self.dir / "p.html", code=2)["error"])
        self.assertEqual(shown["text"], self.run_cli("render", "preview", "--plan", self.dir / "plan-1.json", "--text")["text"])
        lines = shown["text"].splitlines()
        self.assertEqual(lines[0], "미리보기 · 데모 호텔 · 기본 오퍼 · 판매가 +10%")
        self.assertIn("빨간 줄 · 2칸이 정가(줄 그은 값)를 넘습니다.", shown["text"])
        self.assertIn("성인 2 · 1박 이상 | 200.00 → 220.00", shown["text"], "표의 줄은 한 줄, 칸은 | 로")
        self.assertNotIn("<", shown["text"])
        self.assertNotIn("text", self.run_cli("render", "preview", "--plan", self.dir / "plan-1.json", "--out", self.dir / "p.html"))

    def test_g4_the_words_said_with_a_red_line_choice_are_kept_and_shown_next_to_the_choice(self):
        said = "500 넘는 두 칸은 정가도 같이 올려 주세요"
        bare = self.write("bare.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        refused = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", bare, "--record",
                               "--out", self.dir / "plan-0.json", code=2)
        self.assertIn("(said)", refused["error"], "담당자의 말이 없는 고름은 받지 않는다")
        self.assertEqual(self.run_cli("list", "--all")["changes"], [], "장부에 아무것도 적지 않았다")

        choices = self.write("choices.json", [{"rule": "ABOVE_LIST", "choice": "raise_list", "said": said}])
        short = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", choices, "--record",
                             "--out", self.dir / "plan.json")
        change = short["change_id"]
        db = sqlite3.connect(self.dir / "기록" / DB_NAME)
        kept = set(db.execute("SELECT DISTINCT item_key, choice, said FROM item_values WHERE change_id = ? AND choice IS NOT NULL",
                              (change,)))
        db.close()
        self.assertEqual({(choice, words) for _key, choice, words in kept}, {("raise_list", said)}, "장부가 고른 칸마다 그 말을 적는다")
        self.assertEqual(len(kept), 2)

        plan = json.loads((self.dir / "plan.json").read_text(encoding="utf-8"))
        fresh = self.write("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json", "--snapshot", fresh)
        for call in self.run_cli("calls", "--change", change)["calls"]:
            self.run_cli("record-result", "--change", change, "--result", self.write(f"r{call['no']}.json", answer(call)))
        after = self.write("after.json", encode_snapshot(scene.applied(scene.snapshot(), map(decode_step, plan["steps"]))))
        self.assertTrue(self.run_cli("verify", "--change", change, "--snapshot", after)["same"])
        text = self.run_cli("render", "result", "--change", change, "--text")["text"].splitlines()
        self.assertIn("고르신 빨간 줄", text)
        self.assertIn(f"정가보다 비싸집니다 | 정가도 10% 올림 | 2 | “{said}”", text, "고른 것 옆에 담당자의 말")

    def test_preview_apply_verify_rollback_and_list(self):
        first = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record",
                             "--out", self.dir / "plan1.json")
        change = first["change_id"]
        self.assertEqual((first["counts"]["cells"], first["counts"]["red"], first["saves"]), (90, 2, None))
        fresh = self.write("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        self.assertIn("빨간 줄", self.run_cli("begin", "--change", change, "--plan", self.dir / "plan1.json", "--snapshot", fresh, code=2)["error"])

        change = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                              "--record", "--replaces", change, "--out", self.dir / "plan.json")["change_id"]
        plan = json.loads((self.dir / "plan.json").read_text(encoding="utf-8"))
        self.assertEqual(len(plan["steps"]), 8)
        page = Path(self.run_cli("render", "preview", "--plan", self.dir / "plan.json")["page"])
        self.assertEqual(page.parent, self.dir / "기록")
        self.assertTrue(page.name.endswith("· 데모 호텔 · 미리보기.html"))
        self.assertIn("ERP 에 8번 나눠 저장합니다", page.read_text(encoding="utf-8"))
        again = Path(self.run_cli("render", "preview", "--plan", self.dir / "plan.json")["page"])
        self.assertNotEqual(again, page)

        self.assertTrue(self.run_cli("stale", "--change", change, "--snapshot", self.snapshot)["same"])
        moved = scene.snapshot()
        key = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1)
        moved = replace(moved, cells={**moved.cells, key: replace(moved.cells[key], sell=moved.cells[key].sell + 1)})
        stale = self.run_cli("stale", "--change", change, "--snapshot", self.write("moved.json", encode_snapshot(moved)), code=1)
        self.assertEqual([item["key"]["date"] for item in stale["differences"]], ["2026-12-25"])

        self.assertEqual(self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json", "--snapshot", fresh)["status"], "applying")
        for call in self.run_cli("calls", "--change", change)["calls"]:
            last = self.run_cli("record-result", "--change", change, "--result", self.write(f"r{call['no']}.json", answer(call)))
        self.assertEqual(last["status"], "applied")

        after = self.write("after.json", encode_snapshot(scene.applied(scene.snapshot(), map(decode_step, plan["steps"]))))
        self.assertTrue(self.run_cli("verify", "--change", change, "--snapshot", after)["same"])
        result = Path(self.run_cli("render", "result", "--change", change, "--out", self.dir / "result.html")["page"])
        self.assertIn("90칸 모두 넣은 값과 같습니다", result.read_text(encoding="utf-8"))

        rollback = self.run_cli("rollback", "--change", change, "--snapshot", after, "--record", "--sentence", "방금 것 되돌려",
                                "--out", self.dir / "rollback.json")
        self.assertEqual((rollback["restored"], rollback["kept"], rollback["saves"]), (90, 0, 8))
        page = Path(self.run_cli("render", "rollback", "--plan", self.dir / "rollback.json")["page"])
        self.assertIn("에 적어 둔 값으로 되돌립니다", page.read_text(encoding="utf-8"))
        fresh_after = self.write("fresh-after.json", encode_snapshot(scene.fresh(scene.applied(scene.snapshot(), map(decode_step, plan["steps"])))))
        self.assertEqual(self.run_cli("begin", "--change", rollback["change_id"], "--plan", self.dir / "rollback.json",
                                      "--snapshot", fresh_after)["steps"], 8)
        self.assertEqual(self.run_cli("read-calls", "--record", rollback["change_id"]), self.run_cli("read-calls", "--record", change),
                         "G5 — 되돌리기 번호도 다시 읽을 범위를 안다")
        self.assertTrue(self.run_cli("stale", "--change", rollback["change_id"], "--snapshot", after)["same"],
                        "G5 — 되돌리기의 낡음 확인은 그 계산이 바탕으로 삼은 읽은 값(after)과 견준다")

        snapshot_id = self.run_cli("save-snapshot", "--snapshot", after)["change_id"]
        listed = self.run_cli("list", "--all")
        self.assertEqual([(row["id"], row["kind"], row["status"]) for row in listed["changes"]],
                         [(snapshot_id, "snapshot", "saved"), (rollback["change_id"], "rollback", "applying"),
                          (change, "change", "applied"), (first["change_id"], "change", "replaced")])
        self.assertTrue(listed["ledger"].endswith("가격장부.sqlite3"))

    def test_v3_planning_again_writes_a_new_file_and_replaces_the_preview_it_names(self):
        first = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record",
                             "--out", self.dir / "plan-1.json")["change_id"]
        refused = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                               "--record", "--replaces", first, "--out", self.dir / "plan-1.json", code=2)["error"]
        self.assertIn("이미 있는 파일입니다", refused)
        self.assertEqual([row["id"] for row in self.run_cli("list", "--all")["changes"]], [first], "덮어쓰기를 거절하면 장부에도 적지 않는다")
        self.assertIsNone(json.loads((self.dir / "plan-1.json").read_text(encoding="utf-8"))["steps"], "앞 계산 파일은 그대로")

        second = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                              "--record", "--replaces", first, "--out", self.dir / "plan-2.json")
        self.assertEqual(second["replaces"], first)
        listed = {row["id"]: row for row in self.run_cli("list", "--all")["changes"]}
        self.assertEqual((listed[first]["status"], listed[first]["replaces"]), ("replaced", None))
        self.assertEqual((listed[second["change_id"]]["status"], listed[second["change_id"]]["replaces"]), ("previewed", first))

        fresh = self.write("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        old = self.run_cli("begin", "--change", first, "--plan", self.dir / "plan-2.json", "--snapshot", fresh, code=2)["error"]
        self.assertIn(f"{first}번 미리보기는 다시 계산해 {second['change_id']}번으로 바뀌었습니다", old)
        again = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                             "--record", "--replaces", first, "--out", self.dir / "plan-3.json", code=2)["error"]
        self.assertIn(f"이미 {second['change_id']}번으로 바뀌었습니다", again)
        self.assertEqual(self.run_cli("begin", "--change", second["change_id"], "--plan", self.dir / "plan-2.json",
                                      "--snapshot", fresh)["status"], "applying")
        started = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                               "--record", "--replaces", second["change_id"], "--out", self.dir / "plan-4.json", code=2)["error"]
        self.assertIn("바꿀 수 있는 미리보기가 아닙니다", started, "적용을 시작한 번호는 바꾸지 않는다")
        self.assertIn("--record", self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request,
                                               "--replaces", first, code=2)["error"])
        other = self.write("other-hotel.json", {**encode_snapshot(scene.snapshot()), "hotel": {"id": "9", "name": "다른 호텔"}})
        other_request = self.write("other-request.json", {**encode_request(scene.request()), "hotel": {"id": "9", "name": "다른 호텔"}})
        third = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record")["change_id"]
        self.assertIn("같은 호텔 · 오퍼의 미리보기만", self.run_cli("plan", "--snapshot", other, "--request", other_request,
                                                          "--resolutions", self.choice, "--record", "--replaces", third,
                                                          code=2)["error"])
        self.assertEqual({row["id"]: row["status"] for row in self.run_cli("list", "--all")["changes"]}[third], "previewed",
                         "거절한 바꾸기는 앞 번호를 그대로 둔다")

    def applied_change(self):
        """적용까지 끝난 변경 하나 → (번호, 적용 뒤 지금 값)."""
        change = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--resolutions", self.choice,
                              "--record", "--out", self.dir / "plan-1.json")["change_id"]
        fresh = self.write("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan-1.json", "--snapshot", fresh)
        for call in self.run_cli("calls", "--change", change)["calls"]:
            self.run_cli("record-result", "--change", change, "--result", self.write(f"r{call['no']}.json", answer(call)))
        steps = json.loads((self.dir / "plan-1.json").read_text(encoding="utf-8"))["steps"]
        return change, scene.applied(scene.snapshot(), map(decode_step, steps))

    def test_w3_a_rollback_calculated_again_writes_a_new_file_and_replaces_the_preview_it_names(self):
        change, after = self.applied_change()
        key = CellKey("디럭스", "조식 포함", "2026-12-25", "A2", 1)
        moved = replace(after, cells={**after.cells, key: replace(after.cells[key], sell=after.cells[key].sell + 1)})
        now = self.write("now.json", encode_snapshot(moved))
        rollback = ("rollback", "--change", change, "--snapshot", now, "--record", "--sentence", "방금 것 되돌려")
        first = self.run_cli(*rollback, "--out", self.dir / "rollback-1.json")
        self.assertEqual(first["kept"], 1, "그 사이 달라진 칸 하나는 그대로 둔다")
        before = self.run_cli("list", "--all")["changes"]

        refused = self.run_cli(*rollback, "--include-kept", "--replaces", first["change_id"], "--out", self.dir / "rollback-1.json",
                               code=2)["error"]
        self.assertIn("이미 있는 파일입니다", refused)
        self.assertEqual(self.run_cli("list", "--all")["changes"], before, "덮어쓰기를 거절하면 장부에도 적지 않는다")
        self.assertEqual(len(json.loads((self.dir / "rollback-1.json").read_text(encoding="utf-8"))["rollback"]["kept"]), 1,
                         "앞 계산 파일은 그대로")
        self.assertIn("--record", self.run_cli("rollback", "--change", change, "--snapshot", now, "--include-kept",
                                               "--replaces", first["change_id"], code=2)["error"])

        second = self.run_cli(*rollback, "--include-kept", "--replaces", first["change_id"], "--out", self.dir / "rollback-2.json")
        self.assertEqual((second["replaces"], second["restored"]), (first["change_id"], first["restored"] + 1),
                         "그대로 두던 칸도 되돌린다")
        listed = {row["id"]: row for row in self.run_cli("list", "--all")["changes"]}
        self.assertEqual((listed[first["change_id"]]["status"], listed[second["change_id"]]["status"],
                          listed[second["change_id"]]["replaces"]), ("replaced", "previewed", first["change_id"]))
        self.assertEqual([row["id"] for row in listed.values() if row["sentence"] == "방금 것 되돌려" and row["status"] == "previewed"],
                         [second["change_id"]], "같은 문장의 미리보기는 하나만 남는다")
        fresh = self.write("fresh-now.json", encode_snapshot(scene.fresh(moved)))
        old = self.run_cli("begin", "--change", first["change_id"], "--plan", self.dir / "rollback-2.json", "--snapshot", fresh,
                           code=2)["error"]
        self.assertIn(f"{first['change_id']}번 미리보기는 다시 계산해 {second['change_id']}번으로 바뀌었습니다", old)
        self.assertEqual(self.run_cli("begin", "--change", second["change_id"], "--plan", self.dir / "rollback-2.json",
                                      "--snapshot", fresh)["status"], "applying")

    def test_w3_a_restore_calculated_again_writes_a_new_file_and_replaces_only_a_restore_of_the_same_state(self):
        saved = self.run_cli("save-snapshot", "--snapshot", self.snapshot)["change_id"]
        change, after = self.applied_change()
        now = self.write("now.json", encode_snapshot(after))
        restore = ("restore", "--saved", saved, "--snapshot", now, "--record", "--sentence", "저장해 둔 대로")
        first = self.run_cli(*restore, "--out", self.dir / "rollback-1.json")
        before = self.run_cli("list", "--all")["changes"]
        self.assertIn("이미 있는 파일입니다", self.run_cli(*restore, "--replaces", first["change_id"],
                                                    "--out", self.dir / "rollback-1.json", code=2)["error"])
        self.assertEqual(self.run_cli("list", "--all")["changes"], before, "덮어쓰기를 거절하면 장부에도 적지 않는다")
        self.assertIn("--record", self.run_cli("restore", "--saved", saved, "--snapshot", now, "--replaces", first["change_id"],
                                               code=2)["error"])

        second = self.run_cli(*restore, "--room", "디럭스", "--replaces", first["change_id"], "--out", self.dir / "rollback-2.json")
        self.assertEqual(second["replaces"], first["change_id"])
        listed = {row["id"]: row for row in self.run_cli("list", "--all")["changes"]}
        self.assertEqual((listed[first["change_id"]]["status"], listed[second["change_id"]]["status"]), ("replaced", "previewed"))
        fresh = self.write("fresh-now.json", encode_snapshot(scene.fresh(after)))
        self.assertIn("다시 계산해", self.run_cli("begin", "--change", first["change_id"], "--plan", self.dir / "rollback-2.json",
                                              "--snapshot", fresh, code=2)["error"])

        # 다른 것을 하는 미리보기는 바꾸지 않는다 — 바꾸기 · 변경 되돌리기 · 다른 저장 상태로 되돌리기
        rollback = self.run_cli("rollback", "--change", change, "--snapshot", now, "--record")["change_id"]
        preview = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record")["change_id"]
        other_saved = self.run_cli("save-snapshot", "--snapshot", now)["change_id"]
        for args, target in ((restore, rollback), (restore, preview),
                             (("restore", "--saved", other_saved, "--snapshot", now, "--record"), second["change_id"]),
                             (("rollback", "--change", change, "--snapshot", now, "--record"), second["change_id"]),
                             (("plan", "--snapshot", self.snapshot, "--request", self.request, "--record"), second["change_id"])):
            self.assertIn("같은 것을 다시 계산한 미리보기만", self.run_cli(*args, "--replaces", target, code=2)["error"], (args[0], target))
        statuses = {row["id"]: row["status"] for row in self.run_cli("list", "--all")["changes"]}
        self.assertEqual([statuses[n] for n in (rollback, preview, second["change_id"])], ["previewed"] * 3,
                         "거절한 바꾸기는 앞 번호를 그대로 둔다")

    def test_w2_a_reading_larger_than_the_page_keeps_is_refused_before_anything_is_called(self):
        year = [(date(2027, 1, 1) + timedelta(days=n)).isoformat() for n in range(365)]

        def year_of(pairs: int) -> str:
            return self.write(f"range-{pairs}.json", {"kind": "range", "hotel": {"id": "1", "name": "데모 호텔"}, "offer": "기본 오퍼",
                                                      "pairs": [{"room": f"객실 {n}", "rate_plan": "조식 포함"} for n in range(1, pairs + 1)],
                                                      "dates": year})
        example = self.run_cli("read-calls", "--request", year_of(20))
        self.assertEqual((len(example["pairs"]), len(example["reserved"])), (40, 1),
                         "1년 · 객실 · 요금제 20개(가격 읽기 40번 + 예약 있는 날 읽기 1번)는 한 번에 읽는다")
        most = (PAGE_KEEPS - 1) // 2
        self.assertEqual(len(self.run_cli("read-calls", "--request", year_of(most))["pairs"]), 2 * most)
        refused = self.run_cli("read-calls", "--request", year_of(most + 1), code=2)["error"]
        for words in ("이 범위는 읽기 한 번에 들지 않습니다", f"가격 읽기 {2 * most + 2}번 + 예약 있는 날 읽기 1번", f"{PAGE_KEEPS}번까지",
                      "KEEP_BODIES", "나눠"):
            self.assertIn(words, refused)

    def test_a_request_on_another_value_and_a_clear_request_plan_through_the_command(self):
        clear = self.write("clear.json", encode_request(scene.request(operation="clear", value=None, field="list")))
        result = self.run_cli("plan", "--snapshot", self.snapshot, "--request", clear)
        self.assertEqual([(step["kind"], step["clear"]) for step in result["steps"]], [("cell_edit", ["list"])] * 2)
        self.assertEqual(result["counts"]["skipped"], 94)
        supply = self.write("supply.json", encode_request(scene.request(operation="percent", value=D("10"), field="supply")))
        self.assertEqual(self.run_cli("plan", "--snapshot", self.snapshot, "--request", supply)["counts"]["skipped"], 96)

    def test_r6_a_currency_the_person_named_must_be_the_offers_or_nothing_is_planned(self):
        """담당자가 금액에 통화를 말했으면("1,000엔") 요청의 `currency` 로 적는다. 오퍼의 통화와 다르면 plan 은 아무것도 적지 않고
        거절한다 — 바꿔 셈하지 않는다(요금표의 통화와 같은 규칙). 같으면(대소문자는 상관없다) 그대로 계산한다."""
        request = dict(encode_request(replace(scene.request(), operation="amount", value=D("1000"))), currency="JPY")
        refused = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.write("yen.json", request), "--record", code=2)
        self.assertIn("말씀하신 통화는 JPY 인데 ERP 의 이 오퍼는 USD 입니다", refused["error"])
        self.assertEqual(self.run_cli("list", "--all")["changes"], [], "장부에 아무것도 적지 않았다")
        same = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.write("usd.json", dict(request, currency="usd")))
        self.assertGreater(same["counts"]["will_change"], 0)

    def test_mismatched_input_and_a_plan_for_another_request_are_refused(self):
        other = self.write("other.json", {**encode_request(scene.request()), "hotel": {"id": "2", "name": "데모 호텔"}})
        refused = self.run_cli("plan", "--snapshot", self.snapshot, "--request", other, code=2)["error"]
        self.assertIn("호텔 1 (데모 호텔)", refused, "G2 — 이름이 같아도 번호가 다르면 다른 호텔이다")
        self.assertIn("호텔 2 (데모 호텔)", refused)
        nameless = self.write("nameless.json", {**encode_request(scene.request()), "hotel": "데모 호텔"})
        self.assertIn("호텔 번호 없이", self.run_cli("plan", "--snapshot", self.snapshot, "--request", nameless, code=2)["error"])
        change = self.run_cli("plan", "--snapshot", self.snapshot, "--request", self.request, "--record")["change_id"]
        fifteen = self.write("request15.json", encode_request(scene.request("15")))
        self.run_cli("plan", "--snapshot", self.snapshot, "--request", fifteen, "--resolutions", self.choice,
                     "--out", self.dir / "plan15.json")
        fresh = self.write("fresh.json", encode_snapshot(scene.fresh(scene.snapshot())))
        self.assertIn("다른 계산", self.run_cli("begin", "--change", change, "--plan", self.dir / "plan15.json", "--snapshot", fresh,
                                            code=2)["error"])
        self.assertIn("파일이 없습니다", self.run_cli("stale", "--change", change, "--snapshot", "없는.json", code=2)["error"])


if __name__ == "__main__":
    unittest.main()
