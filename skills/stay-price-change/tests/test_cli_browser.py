"""브라우저 쪽과 명령 — read-calls · reserved · read(브라우저 답으로) · calls · record-result.

    python3 -m unittest discover -s tests

장부는 `STAY_PRICE_LEDGER_DIR` 로 임시 폴더에 둔다. 브라우저 답은 `window.stayPrice` 가 돌려주는 모양을 그대로 쓴다.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from browser_replies import reply  # noqa: E402
from price_browser import ask_sum  # noqa: E402
from price_model import decode_snapshot, encode_request, encode_snapshot  # noqa: E402

ERP = HERE / "fixtures" / "erp"
PRICE = (ERP / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")
REJECTED = (ERP / "adjust-rejected.html").read_text(encoding="utf-8").replace("<td>스위트</td>", "<td>디럭스</td>")


class BrowserCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = {**os.environ, "STAY_PRICE_LEDGER_DIR": str(self.dir / "기록")}

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def test_read_calls_then_reserved_rounds_then_read_from_browser_answers(self):
        request = self.write("request.json", encode_request(scene.request()))
        calls = self.run_cli("read-calls", "--request", request)
        self.assertEqual(len(calls["pairs"]), 4)
        self.assertEqual(calls["pairs"][0]["weekdays"], ["금", "토"])
        self.assertEqual(len(calls["reserved"]), 1)

        probe = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24", "to": "2026-12-31",
                 "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}
        probes = self.write("probes.json", [probe])
        first = self.run_cli("reserved", "--probes", probes)
        self.assertEqual((first["done"], first["ask"], first["answered"]), (False, [probe], 0))
        pair = self.write("pair.json", reply("readPair", {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24", "to": "2026-12-31", "weekdays": list("월화수목금토일")}, {"fragment": PRICE}))
        left = self.run_cli("read", "--pair-result", pair, "--reserved-probes", probes, code=2)
        self.assertIn("물음이 1개 남았습니다", left["error"])

        answers = self.write("answers.json", reply("readReserved", probe, {"fragment": REJECTED}))
        self.assertTrue(self.run_cli("reserved", "--probes", probes, "--result", answers)["done"])
        self.run_cli("read", "--pair-result", pair, "--reserved-probes", probes, "--reserved-result", answers,
                     "--read-at", "2026-11-20T18:00:00+09:00", "--out", self.dir / "snapshot.json")
        snapshot = decode_snapshot(json.loads((self.dir / "snapshot.json").read_text(encoding="utf-8")))
        self.assertEqual((snapshot.offer, snapshot.currency, len(snapshot.cells)), ("샘플 오퍼", "USD", 16))
        self.assertIn(("디럭스", "2026-12-24"), snapshot.reserved)

        wrong = self.write("wrong.json", reply("readPair", {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "룸온리", "from": "2026-12-24", "to": "2026-12-31", "weekdays": list("월화수목금토일")}, {"fragment": PRICE}))
        self.assertIn("물었는데 화면은", self.run_cli("read", "--pair-result", wrong, code=2)["error"])

    def test_calls_list_unsaved_steps_and_record_result_writes_only_the_step_it_answers(self):
        snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        request = self.write("request.json", encode_request(scene.request()))
        choice = self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        change = self.run_cli("plan", "--snapshot", snapshot, "--request", request, "--resolutions", choice, "--record",
                              "--out", self.dir / "plan.json")["change_id"]
        self.assertIn("begin", self.run_cli("calls", "--change", change, code=2)["error"])
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json")
        calls = self.run_cli("calls", "--change", change)["calls"]
        self.assertEqual([(call["no"], call["op"]) for call in calls], [(index, "applyBulk") for index in range(1, 9)])
        self.assertEqual(calls[0]["payload"]["offer"], scene.request().offer)

        def result(call, **over):
            return dict({"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True,
                         "note": "저장했습니다"}, **over)

        saved = self.run_cli("record-result", "--change", change, "--result", self.write("r1.json", result(calls[0])))
        self.assertEqual((saved["step"], saved["saved"], saved["status"]), (1, True, "applying"))
        self.assertEqual([call["no"] for call in self.run_cli("calls", "--change", change)["calls"]], list(range(2, 9)))

        mixed = dict(result(calls[1]), no=3)
        self.assertIn("다른 값을 물었습니다", self.run_cli("record-result", "--change", change, "--result", self.write("mixed.json", mixed),
                                                     code=2)["error"])
        unsure = result(calls[1], ok=False, saved="unknown", error="결과를 확인하지 못했습니다")
        stopped = self.run_cli("record-result", "--change", change, "--result", self.write("r2.json", unsure))
        self.assertEqual((stopped["saved"], stopped["status"]), (False, "stopped"))
        self.assertIn("다시 읽어", stopped["note"])
        self.assertEqual([call["no"] for call in self.run_cli("calls", "--change", change)["calls"]], list(range(2, 9)),
                         "멈춘 단계는 이어서 할 목록에 남는다")

    def test_g2_the_ledger_keeps_the_hotel_the_page_named_and_rollback_or_restore_elsewhere_is_refused(self):
        snapshot = encode_snapshot(scene.snapshot())
        snapshot["hotel"] = {"id": scene.HOTEL_ID, "name": "페이지가 부르는 이름"}
        read = self.write("snapshot.json", snapshot)
        request = self.write("request.json", encode_request(scene.request()))
        choice = self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        change = self.run_cli("plan", "--snapshot", read, "--request", request, "--resolutions", choice, "--record",
                              "--out", self.dir / "plan.json")["change_id"]
        listed = self.run_cli("list")["changes"][0]
        self.assertEqual((listed["hotel"], listed["hotel_id"]), ("페이지가 부르는 이름", scene.HOTEL_ID),
                         "장부에는 요청에 적은 이름이 아니라 페이지가 알아본 호텔이 적힌다")
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json")
        call = self.run_cli("calls", "--change", change)["calls"][0]
        self.assertEqual(call["payload"]["hotel"], {"id": scene.HOTEL_ID, "name": "페이지가 부르는 이름"}, "부를 값마다 그 호텔이 실린다")
        saved = {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True, "pressed": True}
        self.run_cli("record-result", "--change", change, "--result", self.write("saved.json", saved))
        elsewhere = dict(snapshot, hotel={"id": "2", "name": "페이지가 부르는 이름"})
        other = self.write("other.json", elsewhere)
        refused = self.run_cli("rollback", "--change", change, "--snapshot", other, code=2)["error"]
        self.assertIn("호텔 2 (페이지가 부르는 이름)", refused)
        self.assertIn(f"호텔 {scene.HOTEL_ID} (페이지가 부르는 이름)", refused)
        saved_state = self.run_cli("save-snapshot", "--snapshot", read)["change_id"]
        self.assertIn("호텔 2", self.run_cli("restore", "--saved", saved_state, "--snapshot", other, code=2)["error"])

    def test_g7_a_save_that_never_started_is_not_recorded_and_the_run_goes_on(self):
        snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        request = self.write("request.json", encode_request(scene.request()))
        choice = self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        change = self.run_cli("plan", "--snapshot", snapshot, "--request", request, "--resolutions", choice, "--record",
                              "--out", self.dir / "plan.json")["change_id"]
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json")
        call = self.run_cli("calls", "--change", change)["calls"][0]
        later = {"ok": False, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "started": False, "wait": 5,
                 "clicks": {}, "error": "앞 화면(드로어·요청)이 아직 정리되지 않았습니다"}
        waited = self.run_cli("record-result", "--change", change, "--result", self.write("later.json", later))
        self.assertEqual((waited["started"], waited["wait"], waited["status"]), (False, 5, "applying"))
        self.assertNotIn("saved", waited)
        self.assertEqual(self.run_cli("calls", "--change", change)["calls"][0]["no"], call["no"], "그 단계는 그대로 남는다")
        self.assertEqual(self.run_cli("list")["changes"][0]["status"], "applying", "멈추지 않았다")
        saved = dict(later, ok=True, started=None, wait=None, saved=True, pressed=True, note="저장했습니다", error=None)
        self.assertEqual(self.run_cli("record-result", "--change", change, "--result", self.write("saved.json", saved))["saved"],
                         True, "기다린 뒤 같은 단계를 다시 불러 저장한다")
        pressed = dict(later, no=2, ask=ask_sum(self.run_cli("calls", "--change", change)["calls"][0]["payload"]),
                       op="applyBulk", pressed=True, saved="unknown")
        self.assertEqual(self.run_cli("record-result", "--change", change, "--result", self.write("pressed.json", pressed)
                                      )["status"], "stopped", "저장 단추가 눌린 답은 시작하지 않은 것이 아니다")


    def test_a_cut_piece_makes_read_say_which_piece_to_fetch_again_and_at_what_size(self):
        asked = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24", "to": "2026-12-31",
                 "weekdays": list("월화수목금토일")}
        result, *takes = reply("readPair", asked, {"fragment": PRICE}, pieces=3)
        cut = json.dumps(takes[1], ensure_ascii=False)[:990] + "[TRUNCATED]"
        error = self.run_cli("read", "--pair-result", self.write("pair.json", [result, takes[0], cut, takes[2]]), code=2)
        self.assertEqual(error["refetch"], [{"id": result["body"]["id"], "at": takes[1]["at"], "size": 600}])
        self.assertIn("stayPrice.take(", error["error"])
        raw = self.dir / "cut.txt"
        raw.write_text(cut, encoding="utf-8")
        again = self.run_cli("read", "--pair-result", self.write("rest.json", [result, takes[0], takes[2]]),
                             "--pair-result", raw, code=2)
        self.assertEqual(again["refetch"][0]["size"], 600, "JSON 이 아닌 파일은 도구가 보인 그대로의 답으로 읽는다")
        whole = self.run_cli("read", "--pair-result", self.write("whole.json", [result, *takes]))
        self.assertEqual(whole["offer"], "샘플 오퍼")


if __name__ == "__main__":
    unittest.main()