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
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from browser_replies import done_at, reply  # noqa: E402
from change_core.ledger import now_text  # noqa: E402
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

    def fresh(self, snapshot):
        """적용 직전에 방금 읽은 값 — 미리보기 때와 같은 칸, 읽은 시각만 지금(15분 안)"""
        data = json.loads(Path(snapshot).read_text(encoding="utf-8")) if isinstance(snapshot, str) else snapshot
        return self.write("fresh.json", dict(data, read_at=now_text()))

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

        # 읽기 한 번 — 부를 값 파일 하나(calls.json)와 답 폴더 하나. 명령이 서로 그 파일을 넘겨받는다(G4)
        asked = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일")}
        probe = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}
        folder = self.dir / "읽기-1"
        folder.mkdir()
        calls = self.write("읽기-1/calls.json", {"pairs": [asked], "reserved": [probe]})
        first = self.run_cli("reserved", "--calls", calls)
        self.assertEqual((first["done"], first["ask"], first["answered"]), (False, [probe], 0))
        self.assertIn("readPair 답이 없는", self.run_cli("read", "--calls", calls, "--answers", folder, code=2)["error"])
        # 시작하지 않은 답(started false)은 잘못 저장해 두어도 실패한 읽기가 아니라 없는 답이다
        self.write("읽기-1/pair-0.json", {"ok": False, "op": "readPair", "ask": ask_sum(asked), "started": False, "wait": 5,
                                         "error": "앞 화면(드로어·요청)이 아직 정리되지 않았습니다"})
        self.assertIn("readPair 답이 없는", self.run_cli("read", "--calls", calls, "--answers", folder, code=2)["error"])
        for index, item in enumerate(reply("readPair", asked, {"fragment": PRICE})):
            self.write(f"읽기-1/pair-1{'' if index == 0 else '-' + str(index)}.json", item)
        self.assertIn("물음이 1개 남았습니다", self.run_cli("read", "--calls", calls, "--answers", folder, code=2)["error"])

        for index, item in enumerate(reply("readReserved", probe, {"fragment": REJECTED})):
            self.write(f"읽기-1/resv-1{'' if index == 0 else '-' + str(index)}.json", item)
        self.assertTrue(self.run_cli("reserved", "--calls", calls, "--answers", folder)["done"])
        self.run_cli("read", "--calls", calls, "--answers", folder, "--out", folder / "snapshot.json")
        snapshot = decode_snapshot(json.loads((folder / "snapshot.json").read_text(encoding="utf-8")))
        self.assertEqual((snapshot.offer, snapshot.currency, len(snapshot.cells)), ("샘플 오퍼", "USD", 16))
        self.assertEqual((snapshot.hotel_id, snapshot.hotel), (scene.HOTEL_ID, scene.HOTEL), "호텔은 페이지의 답에서")
        self.assertIn(("디럭스", "2026-12-24"), snapshot.reserved)
        self.assertEqual(snapshot.dates, tuple(f"2026-12-{day}" for day in range(24, 32)), "읽은 범위의 날짜가 지금 값에 남는다")

        wrong_asked = dict(asked, ratePlan="룸온리")
        wrong = self.write("wrong.json", reply("readPair", wrong_asked, {"fragment": PRICE}))
        wrong_calls = self.write("wrong-calls.json", {"pairs": [wrong_asked], "reserved": []})
        self.assertIn("물었는데 화면은", self.run_cli("read", "--calls", wrong_calls, "--answers", wrong, code=2)["error"])

    def test_z6_read_at_is_when_the_page_finished_the_earliest_operation_not_when_the_command_ran(self):
        asked = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일")}
        probe = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}
        calls = self.write("calls.json", {"pairs": [asked], "reserved": [probe]})
        now = datetime.now(timezone.utc).replace(microsecond=0)
        # 시운전처럼 — 페이지 작업은 3분 전과 2분 전에 끝났고, 명령은 지금 부른다
        pair = reply("readPair", asked, {"fragment": PRICE}, doneAt=done_at(now - timedelta(minutes=3)))
        resv = reply("readReserved", probe, {"fragment": REJECTED}, doneAt=done_at(now - timedelta(minutes=2)))
        read = self.run_cli("read", "--calls", calls, "--answers", self.write("answers.json", pair + resv))
        self.assertEqual(datetime.fromisoformat(read["read_at"]), now - timedelta(minutes=3), "가장 이른 작업이 끝난 시각")
        self.assertEqual(datetime.fromisoformat(read["read_at"]).utcoffset(), datetime.now().astimezone().utcoffset(), "지금 시각대로")
        self.assertIn("--read-at", self.run_cli("read", "--calls", calls, "--answers", self.dir / "answers.json", "--read-at",
                                                "2026-11-20T18:00:00+09:00", code=2)["error"], "답의 시각을 덮어쓰지 않는다")
        timeless = [dict(pair[0], doneAt=None), *pair[1:]] + resv
        self.assertIn("끝난 시각", self.run_cli("read", "--calls", calls, "--answers", self.write("timeless.json", timeless),
                                            code=2)["error"], "시각이 없는 답으로 모은 읽기는 거절한다")

    def test_z4_a_reading_whose_answer_was_lost_is_taken_from_last_or_from_calling_the_read_again(self):
        asked = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일")}
        probe = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}
        now = datetime.now(timezone.utc).replace(microsecond=0)
        resv = reply("readReserved", probe, {"fragment": REJECTED}, doneAt=done_at(now - timedelta(minutes=1)))
        first = reply("readPair", asked, {"fragment": PRICE}, body_id="p1", doneAt=done_at(now - timedelta(minutes=4)))
        cut = json.dumps(first[0], ensure_ascii=False)[:120] + "[TRUNCATED]"   # 도구가 보인 그대로 저장한 잘린 답

        def reading(name, files):
            folder = self.dir / name
            folder.mkdir()
            calls = self.write(f"{name}/calls.json", {"pairs": [asked], "reserved": [probe]})
            for index, item in enumerate(resv):
                self.write(f"{name}/resv-1{'' if index == 0 else '-' + str(index)}.json", item)
            for file, item in files.items():
                (folder / file).write_text(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False), encoding="utf-8")
            return calls, folder

        # (1) stayPrice.last() — 너무 일찍 받으면 아직 도는 중({running})이고, 그 뒤에 받은 것이 끝난 답이다. 잘린 답 파일은 남아 있다
        calls, folder = reading("읽기-1", {"pair-1.txt": cut, "pair-1-last.json": {"running": {"op": "readPair", "at": first[0]["doneAt"]}}})
        lost = self.run_cli("read", "--calls", calls, "--answers", folder, code=2)["error"]
        self.assertIn("readPair 답이 없는 부를 값이 1개", lost)
        self.assertIn("stayPrice.last()", lost)
        self.write("읽기-1/pair-1-last-2.json", first[0])
        for index, item in enumerate(first[1:], 1):
            self.write(f"읽기-1/take-p1-{index}.json", item)
        from_last = self.run_cli("read", "--calls", calls, "--answers", folder)
        self.assertEqual(datetime.fromisoformat(from_last["read_at"]), now - timedelta(minutes=4))

        # (2) 같은 값으로 다시 부름 — 새 조각 id 로 온 둘째 답만 받았다. 잘린 첫 답은 답이 아니다
        second = reply("readPair", asked, {"fragment": PRICE}, body_id="p2", doneAt=done_at(now - timedelta(minutes=2)))
        calls, folder = reading("읽기-2", {"pair-1.txt": cut, **{f"pair-2{'' if i == 0 else '-' + str(i)}.json": item
                                                                 for i, item in enumerate(second)}})
        again = self.run_cli("read", "--calls", calls, "--answers", folder)
        self.assertEqual((again["cells"], datetime.fromisoformat(again["read_at"])), (from_last["cells"], now - timedelta(minutes=2)),
                         "같은 지금 값, 읽은 시각은 다시 부른 답에서")

        # (3) 둘 다 온전히 저장됨 — last() 로 받은 첫 답(조각은 받지 않음)과 그 사이 값이 바뀐 뒤 다시 부른 답. 늦게 끝난 답 하나로 읽는다
        changed = PRICE.replace('stay-numeric">140.00<', 'stay-numeric">150.00<', 1)
        later = reply("readPair", asked, {"fragment": changed}, body_id="p3", doneAt=done_at(now - timedelta(minutes=2)))
        calls, folder = reading("읽기-3", {"pair-1.json": first[0], **{f"pair-2{'' if i == 0 else '-' + str(i)}.json": item
                                                                     for i, item in enumerate(later)}})
        both = self.run_cli("read", "--calls", calls, "--answers", folder, "--out", folder / "snapshot.json")
        self.assertEqual(datetime.fromisoformat(both["read_at"]), now - timedelta(minutes=2))
        cells = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))["cells"]
        first_cell = [(cell["date"], cell["occupancy"], cell["sell"]) for cell in cells][0]
        self.assertEqual(first_cell, ("2026-12-24", "A2", "150.00"), "다시 부른 답의 값(첫 답은 140.00)")
        self.assertEqual(from_last["cells"][0]["sell"], "140.00")
        self.assertTrue(self.run_cli("reserved", "--calls", calls, "--answers", folder)["done"])

    def test_g4_a_range_with_no_operation_gives_the_calls_and_g5_a_record_number_gives_them_again(self):
        range_ = {"kind": "range", "hotel": scene.HOTEL_REF, "offer": scene.OFFER,
                  "pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}, {"room": "스위트", "rate_plan": "룸온리"}],
                  "dates": list(scene.DATES)}
        calls = self.run_cli("read-calls", "--request", self.write("range.json", range_))
        self.assertEqual([(call["room"], call["ratePlan"]) for call in calls["pairs"]], [("디럭스", "조식 포함"), ("스위트", "룸온리")])
        self.assertEqual(calls["pairs"][0]["hotel"], scene.HOTEL_REF)
        self.assertNotIn("operation", json.dumps(calls))
        for bad, why in ((dict(range_, hotel="데모 호텔"), "호텔 번호 없이"), (dict(range_, dates=["2027-01-02", "2026-12-25"]), "오름차순"),
                         (dict(range_, pairs=[]), "하나 이상")):
            self.assertIn(why, self.run_cli("read-calls", "--request", self.write("bad.json", bad), code=2)["error"])

        # 장부 번호마다 그 계산이 바탕으로 삼은 읽은 값이 남는다 — 같은 범위를 번호로 다시 읽고, 낡음 확인도 번호로 한다
        snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        whole = self.run_cli("read-calls", "--request", self.write("request.json", encode_request(scene.request())))
        change = self.run_cli("plan", "--snapshot", snapshot, "--request", self.dir / "request.json", "--record")["change_id"]
        saved = self.run_cli("save-snapshot", "--snapshot", snapshot)["change_id"]
        def same_range(calls):   # 같은 범위면 부를 값의 차례만 다를 수 있고, 물음(지문)은 같다 — 앞선 읽기의 조각을 빌릴 수 있다(T3)
            return sorted(ask_sum(call) for call in calls["pairs"] + calls["reserved"])
        for number in (change, saved):
            self.assertEqual(same_range(self.run_cli("read-calls", "--record", number)), same_range(whole), f"{number}번의 범위")
        self.assertTrue(self.run_cli("stale", "--change", change, "--snapshot", snapshot)["same"])
        elsewhere = dict(encode_snapshot(scene.snapshot()), hotel={"id": "2", "name": scene.HOTEL})
        self.assertIn("호텔 2", self.run_cli("stale", "--change", change, "--snapshot", self.write("x.json", elsewhere), code=2)["error"])
        self.assertIn("999번", self.run_cli("read-calls", "--record", 999, code=2)["error"])

    def test_calls_list_unsaved_steps_and_record_result_writes_only_the_step_it_answers(self):
        snapshot = self.write("snapshot.json", encode_snapshot(scene.snapshot()))
        request = self.write("request.json", encode_request(scene.request()))
        choice = self.write("choice.json", [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        change = self.run_cli("plan", "--snapshot", snapshot, "--request", request, "--resolutions", choice, "--record",
                              "--out", self.dir / "plan.json")["change_id"]
        self.assertIn("begin", self.run_cli("calls", "--change", change, code=2)["error"])
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json", "--snapshot", self.fresh(snapshot))
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
        self.assertIn("check", self.run_cli("calls", "--change", change, code=2)["error"],
                      "멈춘 변경은 다시 읽어 check 가 이어서 해도 된다고 하기 전에는 남은 단계를 내지 않는다")

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
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json", "--snapshot", self.fresh(snapshot))
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
        self.run_cli("begin", "--change", change, "--plan", self.dir / "plan.json", "--snapshot", self.fresh(snapshot))
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
        calls = self.write("calls.json", {"pairs": [asked], "reserved": []})
        error = self.run_cli("read", "--calls", calls, "--answers", self.write("pair.json", [result, takes[0], cut, takes[2]]), code=2)
        self.assertEqual(error["refetch"], [{"id": result["body"]["id"], "at": takes[1]["at"], "size": 600}])
        self.assertIn("stayPrice.take(", error["error"])
        raw = self.dir / "cut.txt"
        raw.write_text(cut, encoding="utf-8")
        again = self.run_cli("read", "--calls", calls, "--answers", self.write("rest.json", [result, takes[0], takes[2]]),
                             "--answers", raw, code=2)
        self.assertEqual(again["refetch"][0]["size"], 600, "JSON 이 아닌 파일은 도구가 보인 그대로의 답으로 읽는다")
        whole = self.run_cli("read", "--calls", calls, "--answers", self.write("whole.json", [result, *takes]))
        self.assertEqual(whole["offer"], "샘플 오퍼")

    def test_z5_read_and_reserved_borrow_whole_screens_from_earlier_readings_of_the_hotel_in_the_record_folder(self):
        """한 변경의 세 읽기(미리보기 · 적용 직전 · 적용 뒤)와 다른 일의 읽기 — 읽기 폴더는 모두 기록 폴더의 `작업/<작업>/<읽기>/`
        이다. read · reserved 는 그 가운데 같은 호텔의 읽기 폴더에서 다 받은 같은 조각을 스스로 찾아 빌린다(폴더를 대 주지 않는다)."""
        asked = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일")}
        probe = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24",
                 "to": "2026-12-31", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}

        def reading(where, pair=None, resv=None, hotel=scene.HOTEL_REF):
            folder = self.dir / where
            folder.mkdir(parents=True)
            calls = self.write(f"{where}/calls.json", {"pairs": [dict(asked, hotel=hotel)], "reserved": [dict(probe, hotel=hotel)]})
            for prefix, items in (("pair", pair), ("resv", resv)):
                for index, item in enumerate(items or ()):
                    self.write(f"{where}/{prefix}-1{'' if index == 0 else '-' + str(index)}.json", item)
            return calls, folder

        # 기록 폴더 밖의 읽기는 보지 않는다 — 조각을 다 받아 두었어도
        outside = reading("다른 곳/읽기-1", reply("readPair", asked, {"fragment": PRICE}, body_id="o1"),
                          reply("readReserved", probe, {"fragment": REJECTED}, body_id="o2"))
        self.assertTrue(self.run_cli("reserved", "--calls", outside[0], "--answers", outside[1])["done"])
        # 미리보기 때 읽기(일 A) — 조각을 다 받기 전에는 빌릴 곳이 없다
        pair1 = reply("readPair", asked, {"fragment": PRICE}, body_id="b1")
        calls1, first = reading("기록/작업/A/읽기-1", pair1[:1], reply("readReserved", probe, {"fragment": REJECTED}, body_id="b2"))
        self.assertEqual([item["id"] for item in self.run_cli("read", "--calls", calls1, "--answers", first, code=2)["refetch"]], ["b1"],
                         "기록 폴더 밖의 같은 조각은 빌리지 않는다")
        for index, item in enumerate(pair1[1:], 1):
            self.write(f"기록/작업/A/읽기-1/take-b1-{index}.json", item)
        before = self.run_cli("read", "--calls", calls1, "--answers", first)

        # 적용 직전(같은 일의 읽기-2) — 페이지는 새 조각 id 로 같은 글자를 내놓았고, 짧은 답만 저장했다
        pair2, resv2 = reply("readPair", asked, {"fragment": PRICE}, body_id="b3")[0], reply("readReserved", probe, {"fragment": REJECTED}, body_id="b4")[0]
        calls2, second = reading("기록/작업/A/읽기-2", [pair2], [resv2])
        self.assertTrue(self.run_cli("reserved", "--calls", calls2, "--answers", second)["done"], "예약 조각은 읽기-1 에서")
        self.assertEqual(self.run_cli("read", "--calls", calls2, "--answers", second)["cells"], before["cells"], "앞선 읽기의 같은 글자로 같은 지금 값")

        # 적용 뒤 — 값이 바뀐 가격 조각만 다시 받는다. 예약 조각은 그대로 같은 글자다
        changed = PRICE.replace('stay-numeric">140.00<', 'stay-numeric">150.00<', 1)
        pair3 = reply("readPair", asked, {"fragment": changed}, body_id="b5")
        calls3, third = reading("기록/작업/A/읽기-3", pair3[:1], [reply("readReserved", probe, {"fragment": REJECTED}, body_id="b6")[0]])
        self.assertEqual(self.run_cli("read", "--calls", calls3, "--answers", third, code=2)["refetch"], [{"id": "b5", "at": 0, "size": 800}],
                         "어디에도 없는 조각만 이름이 나온다")
        for index, item in enumerate(pair3[1:], 1):
            self.write(f"기록/작업/A/읽기-3/take-b5-{index}.json", item)
        self.assertNotEqual(self.run_cli("read", "--calls", calls3, "--answers", third)["cells"], before["cells"])

        # 다른 일(일 B)의 읽기도 같은 호텔이면 빌려 준다
        calls_b, other_job = reading("기록/작업/B/읽기-1", [reply("readPair", asked, {"fragment": PRICE}, body_id="c1")[0]],
                                     [reply("readReserved", probe, {"fragment": REJECTED}, body_id="c2")[0]])
        self.assertEqual(self.run_cli("read", "--calls", calls_b, "--answers", other_job)["cells"], before["cells"])

        # 앞선 읽기의 답은 조각만 빌려 준다 — 이번 읽기에서 부르지 않은 작업을 메우지 않는다
        calls4, fourth = reading("기록/작업/C/읽기-1", None, [resv2])
        self.assertIn("readPair 답이 없는", self.run_cli("read", "--calls", calls4, "--answers", fourth, code=2)["error"])
        # 알아볼 값 넷이 모두 같아야 같은 조각이다 — 두 번째 값(FNV-1a)만 달라도 빌리지 않는다
        odd = dict(pair2, body=dict(pair2["body"], fnv="00000000"))
        calls5, fifth = reading("기록/작업/C/읽기-2", [odd], [resv2])
        self.assertEqual([item["id"] for item in self.run_cli("read", "--calls", calls5, "--answers", fifth, code=2)["refetch"]], ["b3"])
        # 다른 호텔을 읽은 폴더는 빌려 주지 않는다 — 같은 글자의 파일이 들어 있어도(calls.json 이 다른 호텔을 부른다)
        other_hotel = {"id": "9", "name": scene.HOTEL}
        _calls, elsewhere = reading("기록/작업/D/읽기-1", pair1, None, hotel=other_hotel)
        lonely = reply("readPair", asked, {"fragment": PRICE.replace('stay-numeric">140.00<', 'stay-numeric">141.00<', 1)}, body_id="e1")
        for index, item in enumerate(lonely[1:], 1):
            self.write(f"기록/작업/D/읽기-1/take-e1-{index}.json", item)
        calls6, sixth = reading("기록/작업/E/읽기-1", lonely[:1], [resv2])
        self.assertEqual([item["id"] for item in self.run_cli("read", "--calls", calls6, "--answers", sixth, code=2)["refetch"]], ["e1"])

if __name__ == "__main__":
    unittest.main()