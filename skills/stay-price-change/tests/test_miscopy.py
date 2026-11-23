"""옮겨 적다 틀린 쪽 하나가 호텔을 막지 않는다 — 앞선 읽기 폴더의 어긋난 것은 말없이 건너뛰고(R1), 이번 읽기의 틀린 쪽은 그 쪽을
한 번 다시 받으면 된다(R2). 세 번째 시운전(적용한 뒤 확인 읽기에서 쪽 하나를 두 글자 모자라게 옮겨 적음)을 그대로 되풀이한다.

    python3 -m unittest discover -s tests

장부와 기록 폴더는 `STAY_PRICE_LEDGER_DIR` 로 임시 폴더에 둔다. 값과 이름은 모두 지어낸 것이다.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
from browser_replies import done_at, pack, reply  # noqa: E402
from change_core.answers import BrowserError, ask_sum, unpack  # noqa: E402
from erp_read import parse_html  # noqa: E402

ERP = HERE / "fixtures" / "erp"
PRICE = (ERP / "price-runs-closed-absent-list.html").read_text(encoding="utf-8")
REJECTED = (ERP / "adjust-rejected.html").read_text(encoding="utf-8").replace("<td>스위트</td>", "<td>디럭스</td>")
ASKED = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "room": "디럭스", "ratePlan": "조식 포함", "from": "2026-12-24",
         "to": "2026-12-31", "weekdays": list("월화수목금토일")}
PROBE = {"hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "rooms": ["디럭스"], "ratePlans": ["조식 포함"], "from": "2026-12-24",
         "to": "2026-12-31", "weekdays": list("월화수목금토일"), "occupancy": "*", "nights": "all"}


def folder_state(folder: Path) -> dict:
    """폴더 안 파일마다 (바이트, 고친 시각) — 명령이 앞선 폴더를 건드리지 않았는지 견준다."""
    return {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in sorted(folder.iterdir())}


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.records = self.dir / "기록"
        self.env = scene.env(str(self.records))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, code=0):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, code, done.stderr or done.stdout)
        return json.loads(done.stdout) if code != 2 else json.loads(done.stderr)

    def reading(self, job: str, name: str = "읽기-1") -> Path:
        folder = self.records / "작업" / job / name
        folder.mkdir(parents=True)
        (folder / "calls.json").write_text(json.dumps({"pairs": [ASKED], "reserved": [PROBE]}, ensure_ascii=False), encoding="utf-8")
        return folder

    @staticmethod
    def save(folder: Path, name: str, item) -> Path:
        path = folder / name
        if isinstance(item, bytes):
            path.write_bytes(item)
        else:
            path.write_text(item if isinstance(item, str) else json.dumps(item, ensure_ascii=False), encoding="utf-8")
        return path


class EarlierFolderTest(Cli):
    """R1 — 앞선 읽기 폴더에서는 다 받아 모든 검사를 지난 화면만 빌린다. 그 밖의 것(스스로 말하는 길이와 다른 쪽 · 빠진 쪽 ·
    검사값이 다른 머리 · JSON 이 아닌 파일 · 글자로 읽히지 않는 파일)은 말없이 건너뛰고, 이번 읽기는 그 폴더가 없는 것처럼
    `refetch` 로 받을 것을 댄다."""

    def test_r1_bad_pieces_in_an_earlier_folder_are_skipped_and_the_new_reading_asks_as_if_the_folder_were_not_there(self):
        old = self.reading("A")
        pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p1")
        resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=3, body_id="r1")
        self.save(old, "pair-1.json", pair[0])
        self.save(old, "resv-1.json", resv[0])
        # 가격 조각: 둘째 쪽이 두 글자 모자란다(시운전) — 스스로 말하는 길이와 다르다. 셋째 쪽은 빠졌다
        short = dict(pair[2], text=pair[2]["text"][:-2])
        for index, item in ((1, pair[1]), (2, short), (4, pair[4])):
            self.save(old, f"take-p1-{item['at']}.json", item)
        # 예약 조각: 쪽은 다 있는데 한 쪽이 글자 수는 같고 글자가 다르다(이은 글자의 검사값이 머리와 다르다) · JSON 이 아닌 파일 ·
        # 글자로 읽히지 않는 파일 · 칸이 빠진 머리 · 검사값이 틀린 머리
        typo = dict(resv[2], text=resv[2]["text"].replace("<", ">", 1))
        self.assertEqual(len(typo["text"]), len(resv[2]["text"]))
        for item in (resv[1], typo, *resv[3:]):
            self.save(old, f"take-r1-{item['at']}.json", item)
        self.save(old, "resv-2.json", dict(resv[0], ask="00000000", body=dict(resv[0]["body"], crc32="00000000", id="r2")))
        self.save(old, "take-r1-x.json", '{"op": "take", "ok": true, "id": "r1", "at": 0, "text": "<div')
        self.save(old, "take-r1-y.json", b"\xff\xfe\x00 not text")
        self.save(old, "pair-2.json", {"op": "readPair", "ok": True, "ask": "00000000", "body": {"id": "p1"}})
        before = folder_state(old)

        new = self.reading("B")
        again_pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p2")
        again_resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=3, body_id="r3")
        self.save(new, "pair-1.json", again_pair[0])
        self.save(new, "resv-1.json", again_resv[0])
        calls = new / "calls.json"
        asked = self.run_cli("reserved", "--calls", calls, "--answers", new, code=2)
        self.assertEqual([(item["id"], item["at"]) for item in asked["refetch"]], [("r3", 0)],
                         "예약 조각은 앞선 폴더에 쪽이 다 있어도 머리가 어긋난 곳의 것이라 이번 답의 쪽을 받는다")
        read = self.run_cli("read", "--calls", calls, "--answers", new, code=2)
        self.assertEqual(sorted((item["id"], item["at"]) for item in read["refetch"]), [("p2", 0), ("r3", 0)],
                         "앞선 폴더가 없는 것처럼 — 어긋난 쪽은 오류가 아니다")
        for item in again_pair[1:] + again_resv[1:]:
            self.save(new, f"take-{item['id']}-{item['at']}.json", item)
        self.assertTrue(self.run_cli("reserved", "--calls", calls, "--answers", new)["done"])
        snapshot = self.run_cli("read", "--calls", calls, "--answers", new)
        self.assertEqual((snapshot["offer"], len(snapshot["cells"])), ("샘플 오퍼", 16))
        self.assertEqual(folder_state(old), before, "앞선 폴더의 파일은 그대로다")

    def test_r1_a_whole_checked_screen_in_an_earlier_folder_is_still_borrowed_next_to_broken_ones(self):
        old = self.reading("A")
        pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p1")
        for item in pair[1:]:
            self.save(old, f"take-p1-{item['at']}.json", item)
        self.save(old, "take-p1-broken.json", dict(pair[2], text=pair[2]["text"][:-2]))
        new = self.reading("B")
        self.save(new, "pair-1.json", reply("readPair", ASKED, {"fragment": PRICE}, pieces=4, body_id="p2")[0])
        resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=3, body_id="r3")
        for item in resv:
            self.save(new, f"resv-1-{item.get('at', 'answer')}.json", item)
        snapshot = self.run_cli("read", "--calls", new / "calls.json", "--answers", new)
        self.assertEqual(len(snapshot["cells"]), 16, "같은 글자의 다 받은 화면은 어긋난 쪽 곁에 있어도 빌린다")


RANGE = {"kind": "range", "hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "pairs": [{"room": "디럭스", "rate_plan": "조식 포함"}],
         "dates": [f"2026-12-{day}" for day in range(24, 32)]}
TARGETS = {"kind": "targets", "hotel": scene.HOTEL_REF, "offer": "샘플 오퍼", "sentence": "12/31 디럭스 조식 성인 2 는 170",
           "targets": [{"key": {"room": "디럭스", "rate_plan": "조식 포함", "date": "2026-12-31", "occupancy": "A2", "nights": 1},
                        "values": {"sell": "170"}}]}
APPLIED = PRICE.replace('stay-numeric">160.00<', 'stay-numeric">170.00<', 1)


class TrialTest(Cli):
    """세 번째 시운전 — 가격을 적용하고, 적용 뒤 확인 읽기에서 쪽 하나를 두 글자 모자라게 옮겨 적었다. 그 뒤로 (a) 같은 읽기가 그 쪽
    하나를 새 파일로 다시 받아 끝나고, (b) 새 폴더의 새 읽기가 앞 폴더를 건드리지 않고 끝나고, (c) 되돌리기가 끝까지 간다."""

    def read(self, job: str, name: str, fragment: str, calls_args, ids: str, pages_too=True, at: str | None = None) -> tuple[Path, list]:
        """읽기 한 번 — `at` 은 그 읽기가 끝난 시각(ISO, 주지 않으면 시험의 지금). 적용 직전의 읽기는 미리보기를 적은 뒤의 것이다."""
        folder = self.records / "작업" / job / name
        folder.mkdir(parents=True)
        self.run_cli("read-calls", *calls_args, "--out", folder / "calls.json")
        calls = json.loads((folder / "calls.json").read_text(encoding="utf-8"))
        moment = {} if at is None else {"doneAt": done_at(datetime.fromisoformat(at))}
        pair = reply("readPair", calls["pairs"][0], {"fragment": fragment}, pieces=4, body_id=f"{ids}p", **moment)
        resv = reply("readReserved", calls["reserved"][0], {"fragment": REJECTED}, pieces=3, body_id=f"{ids}r", **moment)
        self.save(folder, "pair-1.json", pair[0])
        self.save(folder, "resv-1.json", resv[0])
        if pages_too:
            for item in pair[1:] + resv[1:]:
                self.save(folder, f"take-{item['id']}-{item['at']}.json", item)
        return folder, pair

    def snapshot(self, folder: Path) -> Path:
        self.run_cli("read", "--calls", folder / "calls.json", "--answers", folder, "--out", folder / "snapshot.json")
        return folder / "snapshot.json"

    def apply(self, change: int, plan: Path, snapshot: Path, folder: Path) -> None:
        self.assertEqual(self.run_cli("begin", "--change", change, "--plan", plan, "--snapshot", snapshot)["status"], "applying")
        for call in self.run_cli("calls", "--change", change)["calls"]:
            saved = {"op": call["op"], "no": call["no"], "ok": True, "saved": True, "pressed": True, "ask": ask_sum(call["payload"]),
                     "note": "저장했습니다", "doneAt": done_at()}
            result = self.save(folder, f"{call['no']}.json", saved)
            self.run_cli("record-result", "--change", change, "--result", result)

    def test_r2_trial_one_page_two_characters_short_after_applying_costs_one_retake(self):
        self.run_cli("work")   # 일의 첫 명령(SKILL.md 「준비」 3) — 작업 폴더보다 장부가 먼저다
        job = self.records / "작업" / "A"
        first, _ = self.read("A", "읽기-1", PRICE, ["--request", self.save(self.dir, "range.json", RANGE)], "a1")
        plan = self.run_cli("plan", "--snapshot", self.snapshot(first), "--request", self.save(self.dir, "targets.json", TARGETS),
                            "--record", "--out", job / "plan-1.json")
        change = plan["change_id"]
        self.assertEqual(plan["saves"], 1)
        before, _ = self.read("A", "읽기-2", PRICE, ["--record", change], "a2", pages_too=False, at=scene.READ_AGAIN)
        (job / "적용-1").mkdir()
        self.apply(change, job / "plan-1.json", self.snapshot(before), job / "적용-1")

        # 적용 뒤 확인 읽기 — 둘째 쪽을 두 글자 모자라게 옮겨 적었다(시운전의 `\\\"` → `\"`)
        verify, pair = self.read("A", "읽기-3", APPLIED, ["--record", change], "a3")
        page = pair[2]
        miscopied = self.save(verify, f"take-{page['id']}-{page['at']}.json", dict(page, text=page["text"][:40] + page["text"][42:]))
        asked = self.run_cli("read", "--calls", verify / "calls.json", "--answers", verify, code=2)
        self.assertEqual(asked["refetch"], [{"id": page["id"], "at": page["at"], "size": 800, "until": page["next"],
                                             "save": f"take-{page['id']}-2-", "bad": [
            {"file": miscopied.name, "at": page["at"],
             "why": "옮겨 적은 글의 길이가 쪽이 말하는 길이와 다릅니다 — 그 쪽을 다시 받아 새 파일로 저장합니다"}]}],
                         "그 쪽 하나를 새 이름으로 다시 받으라고 한다 — 앞뒤 쪽은 이미 맞다")
        after_trial = folder_state(verify)

        # (b) 새 폴더의 새 읽기 — 앞 폴더의 틀린 쪽은 오류가 아니고, 앞 폴더는 그대로다
        fresh, _ = self.read("A", "읽기-4", APPLIED, ["--record", change], "a4", pages_too=False)
        self.assertEqual([(item["id"], item["at"], item["bad"]) for item in
                          self.run_cli("read", "--calls", fresh / "calls.json", "--answers", fresh, code=2)["refetch"]],
                         [("a4p", 0, [])], "확인 읽기의 가격 조각은 앞 폴더에서 다 이어지지 않아 빌리지 않는다 — 처음부터 받는다")
        for item in reply("readPair", json.loads((fresh / "calls.json").read_text(encoding="utf-8"))["pairs"][0], {"fragment": APPLIED},
                          pieces=4, body_id="a4p")[1:]:
            self.save(fresh, f"take-a4p-{item['at']}.json", item)
        self.assertTrue(self.run_cli("verify", "--change", change, "--snapshot", self.snapshot(fresh))["same"])
        self.assertEqual(folder_state(verify), after_trial, "새 읽기는 앞 폴더의 파일을 건드리지 않는다")

        # (a) 같은 읽기 — 그 쪽 하나를 명령이 고른 새 이름으로 다시 받으면 끝난다(틀린 파일은 그대로 둔다)
        self.save(verify, f"take-{page['id']}-2-{page['at']}.json", page)
        self.assertTrue(self.run_cli("verify", "--change", change, "--snapshot", self.snapshot(verify))["same"])
        self.assertEqual(miscopied.read_text(encoding="utf-8"), after_trial[miscopied.name][0].decode("utf-8"))

        # (c) 되돌리기 — 같은 범위를 다시 읽어 계산하고 적용하고 확인한다
        back = self.records / "작업" / "B"
        now, _ = self.read("B", "읽기-1", APPLIED, ["--record", change], "b1", pages_too=False)
        rollback = self.run_cli("rollback", "--change", change, "--snapshot", self.snapshot(now), "--record",
                                "--out", back / "rollback-1.json")
        self.assertEqual((rollback["restored"], rollback["saves"]), (1, 1))
        again, _ = self.read("B", "읽기-2", APPLIED, ["--record", rollback["change_id"]], "b2", pages_too=False, at=scene.READ_AGAIN)
        (back / "적용-1").mkdir()
        self.apply(rollback["change_id"], back / "rollback-1.json", self.snapshot(again), back / "적용-1")
        undone, _ = self.read("B", "읽기-3", PRICE, ["--record", rollback["change_id"]], "b3", pages_too=False)
        self.assertTrue(self.run_cli("verify", "--change", rollback["change_id"], "--snapshot", self.snapshot(undone))["same"],
                        "되돌린 뒤 값은 처음 값이다(조각은 처음 읽기에서 빌린다)")


def corrupt(page: dict, how: str) -> str:
    """쪽 하나를 옮겨 적다 틀린 파일 글자 — 글자를 빠뜨림 · 더함 · 하나를 바꿈(글자 수는 그대로) · 파일이 중간에 끊김."""
    text, middle = page["text"], len(page["text"]) // 2
    if how == "drop":
        return json.dumps(dict(page, text=text[:middle] + text[middle + 2:]), ensure_ascii=False)
    if how == "add":
        return json.dumps(dict(page, text=text[:middle] + "가a" + text[middle:]), ensure_ascii=False)
    if how == "change":
        other = "x" if text[middle] != "x" else "y"
        return json.dumps(dict(page, text=text[:middle] + other + text[middle + 1:]), ensure_ascii=False)
    shown = json.dumps(page, ensure_ascii=False)
    return shown[:len(shown) // 2]


class PageMiscopyTest(Cli):
    """R2 — 여러 쪽인 조각의 어느 쪽이든, 어떻게 잘못 옮겨 적었든 명령은 꼭 그 쪽 하나를 짚고, 그 쪽을 한 번 다시 받으면 읽기가
    끝난다. 기록 폴더 밖에서 읽어 앞선 읽기가 빌려 주지 않게 한다."""

    def setUp(self):
        super().setUp()
        self.pair = reply("readPair", ASKED, {"fragment": PRICE}, pieces=5, body_id="p1")
        self.resv = reply("readReserved", PROBE, {"fragment": REJECTED}, pieces=1, body_id="r1")

    def folder(self, name: str, skip: int) -> Path:
        folder = self.dir / name
        folder.mkdir()
        (folder / "calls.json").write_text(json.dumps({"pairs": [ASKED], "reserved": [PROBE]}, ensure_ascii=False), encoding="utf-8")
        self.save(folder, "pair-1.json", self.pair[0])
        self.save(folder, "resv-1.json", self.resv[0])
        for item in self.resv[1:]:
            self.save(folder, f"take-r1-{item['at']}.json", item)
        for index, item in enumerate(self.pair[1:]):
            if index != skip:
                self.save(folder, f"take-p1-{item['at']}.json", item)
        return folder

    def test_r2_every_page_corrupted_four_ways_is_named_alone_and_one_retake_completes_the_reading(self):
        pages = self.pair[1:]
        self.assertEqual(len(pages), 5)
        for index, page in enumerate(pages):
            for how in ("drop", "add", "change", "truncate"):
                with self.subTest(page=index, how=how):
                    folder = self.folder(f"{index}-{how}", skip=index)
                    bad = self.save(folder, f"take-p1-{page['at']}.json", corrupt(page, how))
                    asked = self.run_cli("read", "--calls", folder / "calls.json", "--answers", folder, code=2)["refetch"]
                    self.assertEqual([(item["id"], item["at"], item["until"], [b["file"] for b in item["bad"]]) for item in asked],
                                     [("p1", page["at"], page["next"], [bad.name])], "꼭 그 쪽 하나")
                    self.save(folder, f"{asked[0]['save']}{page['at']}.json", page)
                    self.assertEqual(len(self.run_cli("read", "--calls", folder / "calls.json", "--answers", folder)["cells"]), 16)

    def test_r2_retakes_that_are_miscopied_again_each_get_a_new_name_until_one_is_right(self):
        page = self.pair[3]
        folder = self.folder("again", skip=2)
        self.save(folder, f"take-p1-{page['at']}.json", corrupt(page, "change"))
        for round_, how in ((2, "drop"), (3, "truncate")):
            asked, = self.run_cli("read", "--calls", folder / "calls.json", "--answers", folder, code=2)["refetch"]
            self.assertEqual(asked["save"], f"take-p1-{round_}-", "다시 받은 쪽은 언제나 새 이름")
            self.assertEqual(len(asked["bad"]), round_ - 1, "그 자리의 틀린 파일을 모두 짚는다")
            self.save(folder, f"{asked['save']}{page['at']}.json", corrupt(page, how))
        asked, = self.run_cli("read", "--calls", folder / "calls.json", "--answers", folder, code=2)["refetch"]
        self.save(folder, f"{asked['save']}{page['at']}.json", page)
        self.assertEqual(len(self.run_cli("read", "--calls", folder / "calls.json", "--answers", folder)["cells"]), 16)


class QuoteFreeFormTest(unittest.TestCase):
    """R3 — 페이지가 두는 조각은 따옴표 없는 JSON 이고 화면 조각의 속성은 따옴표 없이 적는다. 읽기는 그 모양을 푼다(페이지 쪽의 같은
    모양은 test_page_dotted.mjs · test_page_scrub_reduce.mjs 가 진짜 stay_price.js 로 본다)."""

    def test_r3_the_quote_free_body_round_trips_every_awkward_value_and_has_no_quote_or_backslash(self):
        value = {"op": "readPair", "hotel": {"id": "1", "name": 'L\'호텔 "본관" \\ & 1<2'}, "noSale": ["2026-12-24"],
                 "fragment": '<td data-stay-name=a&#32;b>"3" &amp; 4\n</td>', "n": [1, 2.5, None, True, False], "": ""}
        text = pack(value)
        self.assertNotRegex(text, r'["\\]', "큰따옴표 · 역슬래시가 없다")
        self.assertNotIn("\\", json.dumps({"text": text}, ensure_ascii=False), "도구가 보이는 모양에도 이스케이프가 붙지 않는다")
        self.assertEqual(unpack(text), value)
        for broken in (text.replace("&#34;", '"', 1), text[:-1] + "\\}"):
            with self.assertRaises(BrowserError):
                unpack(broken)

    def test_r3_the_reader_takes_attributes_without_quotes_and_characters_written_as_numbers(self):
        root = parse_html("<table data-stay-rows=prices><tbody data-stay-occupancy-key=A2C1_CHD data-stay-los-nights=3 "
                          "data-stay-name=디럭스&#32;&#34;킹&#34;&#32;a&#61;b&#47; data-stay-existing><tr><td colspan=4>x</td></tr></tbody></table>")
        tbody, = root.find_all("tbody")
        self.assertEqual(tbody.attrs, {"data-stay-occupancy-key": "A2C1_CHD", "data-stay-los-nights": "3",
                                       "data-stay-name": '디럭스 "킹" a=b/', "data-stay-existing": ""})
        self.assertEqual(tbody.find_all("td")[0].attrs, {"colspan": "4"})


if __name__ == "__main__":
    unittest.main()
