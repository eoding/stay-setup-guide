"""V1 — 미리보기가 보이는 값과 저장 단계가 넣는 값과 장부가 같다. 빨간 줄을 고른 뒤에도.

그림의 장면과 두 번째 시운전의 모양(객실 둘 · 아동 줄 · 박수 층 둘 · 1박 이상 줄이 모두 정가를 넘음)마다, 고름 넷(정가도 올림 ·
정가 지움 · 안 바꿈 · 칸마다 섞음)을 명령으로 돌린다(plan → render preview → begin). 그리고 페이지의 칸 표를 사람이 읽듯
객실 · 요금제 머리, 날짜 열, 인원 · 박수 줄로 읽어 견준다.

    - 저장 단계의 값 하나하나가 페이지의 그 칸 옆에 같은 숫자로 있다(판매가는 굵은 새 값, 정가 · 공급 원가는 「정가 전 → 후」 줄).
    - 페이지에서 바뀐다고 보이는 값 하나하나가 꼭 한 저장 단계에 같은 값으로 있다.
    - 장부가 그 미리보기를 적은 줄로 begin 이 받아들인다(장부의 줄과 저장 단계가 같다).

    python3 -m unittest discover -s tests
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "price_change.py"
sys.path.insert(0, str(SCRIPT.parent))

import scene  # noqa: E402
import trial_scene  # noqa: E402
from change_core.ledger import now_text  # noqa: E402
from price_browser import ask_sum  # noqa: E402
from price_model import (  # noqa: E402
    FIELD_LABELS, CellKey, day_label, decode_step, encode_key, encode_request, encode_snapshot, line_label,
)

CLEAR = "비움"
LABEL_FIELDS = {label: name for name, label in FIELD_LABELS.items()}


class GridReader(HTMLParser):
    """「칸마다 바뀌는 값」 아래의 칸 표 → {(객실 · 요금제 머리, 열 머리, 줄 머리): [(태그, class, 글자)]}. 머리는 그 칸의 첫 글자다."""

    def __init__(self):
        super().__init__()
        self.cells, self.section, self.heading, self.heads = {}, None, "", []
        self.label, self.row, self.parts, self.inline = None, None, None, None

    def handle_starttag(self, tag, attrs):
        if tag in ("h2", "h3", "th"):
            self.label = [tag, None]
        elif tag == "table":
            self.heads = []
        elif tag == "tr":
            self.row = []
        elif tag == "td":
            if self.row:
                self.parts = []
            else:
                self.label = ["td", None]
        elif tag in ("span", "small") and self.parts is not None:
            self.inline = (tag, dict(attrs).get("class", ""))

    def handle_data(self, data):
        if self.label is not None and self.label[1] is None and data.strip():
            self.label[1] = data.strip()
        if self.parts is not None and data.strip():
            tag, cls = self.inline or ("td", "")
            self.parts.append((tag, cls, data.strip()))

    def handle_endtag(self, tag):
        if tag in ("span", "small"):
            self.inline = None
        elif tag in ("h2", "h3", "th") or (tag == "td" and self.parts is None):
            text = (self.label or [None, None])[1] or ""
            self.label = None
            if tag == "h2":
                self.section = text
            elif tag == "h3":
                self.heading = text
            elif tag == "th":
                self.heads.append(text)
            elif self.row is not None:
                self.row.append(text)
        elif tag == "td":
            if self.section == "칸마다 바뀌는 값":
                self.cells[(self.heading, self.heads[len(self.row)], self.row[0])] = self.parts
            self.row.append(None)
            self.parts = None


def read_grid(page: str) -> dict:
    reader = GridReader()
    reader.feed(page)
    return reader.cells


def money(text: str):
    return None if text == CLEAR else Decimal(text.replace(",", ""))


def shown_moves(parts) -> dict:
    """칸 하나의 글자 조각 → 바뀐다고 보이는 필드 → 새 값(비우면 None). 판매가는 「전 → 새」 굵은 값, 나머지는 「정가 전 → 후」 줄."""
    moves = {}
    tags = [(tag, cls) for tag, cls, _text in parts]
    if ("span", "arrow") in tags:
        moves["sell"] = money(next(text for tag, cls, text in parts if cls == "now"))
    for tag, cls, text in parts:
        found = re.fullmatch(r"(판매가|정가|공급 원가) (\S+) → (\S+)", text) if cls == "more" else None
        if found:
            moves[LABEL_FIELDS[found.group(1)]] = money(found.group(3))
    return moves


def step_writes(steps) -> list[tuple[CellKey, str, Decimal | None]]:
    """plan.json 의 저장 단계 → (칸, 필드, 넣는 값) 하나하나. 묶음 저장은 날마다 · 줄마다, 셀 창 저장은 비우는 필드마다."""
    out = []
    for step in steps:
        if step["kind"] == "cell_edit":
            key = step["key"]
            out += [(CellKey(key["room"], key["rate_plan"], key["date"], key["occupancy"], key["nights"]), name, None)
                    for name in step["clear"]]
            continue
        for day in step["dates"]:
            for row in step["rows"]:
                key = CellKey(step["room"], step["rate_plan"], day, row["occupancy"], row["nights"])
                out += [(key, name, Decimal(row[name])) for name in ("sell", "list", "supply") if row[name] is not None]
    return out


def place(key: CellKey) -> tuple[str, str, str]:
    """페이지에서 그 칸을 찾는 자리 — 객실 · 요금제 머리, 날짜 열 머리, 인원 · 박수 줄 머리."""
    return f"{key.room} · {key.rate_plan}", day_label(key.date), line_label(key.occupancy, key.nights)


def above_list_cells(snapshot, request, *where):
    from price_plan import plan_change
    return [change.key for change in plan_change(snapshot, request).changes
            if change.verdict == "ABOVE_LIST" and all(test(change.key) for test in where)]


class CommandCase(unittest.TestCase):
    """명령을 임시 장부로 부른다."""

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

    def run_cli(self, *args):
        done = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr or done.stdout)
        return json.loads(done.stdout)


class PreviewTruthTest(CommandCase):
    def check(self, name, snapshot, request, choices):
        """명령으로 계획하고 페이지를 만들어 저장 단계와 견준다 → plan 답."""
        folder = self.dir / name
        folder.mkdir()
        snap = self.write(f"{name}/snapshot.json", encode_snapshot(snapshot))
        planned = self.run_cli("plan", "--snapshot", snap, "--request", self.write(f"{name}/request.json", encode_request(request)),
                               "--resolutions", self.write(f"{name}/choices.json", choices), "--record",
                               "--out", folder / "plan.json")
        self.assertEqual(planned["unresolved"], [], name)
        page = Path(self.run_cli("render", "preview", "--plan", folder / "plan.json", "--out", folder / "preview.html")["page"])
        grid = read_grid(page.read_text(encoding="utf-8"))
        writes = step_writes(planned["steps"])
        self.assertTrue(writes, name)

        for key, field, value in writes:
            self.assertIn(place(key), grid, f"{name}: 저장하는 칸이 페이지에 없다 {key}")
            self.assertEqual(shown_moves(grid[place(key)]).get(field, "보이지 않음"), value,
                             f"{name}: {key} · {field} — 저장은 {value}, 페이지는 {grid[place(key)]}")
        by_cell = {}
        for key, field, value in writes:
            by_cell.setdefault((place(key), field), []).append(value)
        shown = [(spot, field, value) for spot, parts in grid.items() for field, value in shown_moves(parts).items()]
        self.assertTrue(shown, name)
        for spot, field, value in shown:
            self.assertEqual(by_cell.get((spot, field)), [value], f"{name}: 페이지에서 바뀐다는 {spot} · {field} = {value} 는 "
                                                                  "꼭 한 저장 단계에 같은 값으로 있어야 한다")
        fresh = self.write(f"{name}/fresh.json", dict(encode_snapshot(snapshot), read_at=now_text()))
        begun = self.run_cli("begin", "--change", planned["change_id"], "--plan", folder / "plan.json", "--snapshot", fresh)
        self.assertEqual((begun["status"], begun["steps"]), ("applying", len(planned["steps"])), f"{name}: 장부의 줄 = 저장 단계")
        return planned, page.read_text(encoding="utf-8")

    def test_the_approved_scene_for_every_choice(self):
        snapshot, request = scene.snapshot(), scene.request()
        over = above_list_cells(snapshot, request)
        cases = {
            "raise": ([{"rule": "ABOVE_LIST", "choice": "raise_list"}], 8),
            "clear": ([{"rule": "ABOVE_LIST", "choice": "clear_list"}], 10),
            "keep": ([{"rule": "ABOVE_LIST", "choice": "keep"}], 8),
            # 1/2 만 정가를 지우면 1/1 · 1/2 의 줄이 서로 달라 스위트 · 조식 포함이 묶음 셋 + 셀 창 하나가 된다
            "mixed": ([{"rule": "ABOVE_LIST", "choice": "raise_list"},
                       {"rule": "ABOVE_LIST", "choice": "clear_list", "cells": [encode_key(over[1])]}], 10),
        }
        for name, (choices, saves) in cases.items():
            with self.subTest(name):
                planned, _page = self.check(f"scene-{name}", snapshot, request, choices)
                self.assertEqual(len(planned["steps"]), saves, "그림의 숫자 — 정가도 올림 8번 · 정가 지움 10번")

    def test_the_trial_shape_for_every_choice(self):
        snapshot, request = trial_scene.snapshot(), trial_scene.request()
        over = above_list_cells(snapshot, request)
        self.assertEqual(len(over), 24)
        sea = [key for key in over if key.room == "스탠다드 바다 전망"]
        cases = {
            "raise": ([{"rule": "ABOVE_LIST", "choice": "raise_list"}], 2),
            "clear": ([{"rule": "ABOVE_LIST", "choice": "clear_list"}], 26),
            "keep": ([{"rule": "ABOVE_LIST", "choice": "keep"}], 1),
            "mixed": ([{"rule": "ABOVE_LIST", "choice": "raise_list"},
                       {"rule": "ABOVE_LIST", "choice": "clear_list", "cells": [encode_key(sea[0])]},
                       {"rule": "ABOVE_LIST", "choice": "keep", "cells": [encode_key(over[0]), encode_key(sea[-1])]}], 6),
        }
        for name, (choices, saves) in cases.items():
            with self.subTest(name):
                planned, page = self.check(f"trial-{name}", snapshot, request, choices)
                self.assertEqual(len(planned["steps"]), saves)
                self.assertEqual((planned["counts"]["cells"], planned["counts"]["red"], planned["counts"]["chosen"]), (36, 0, 24))
                self.assertNotIn("골라 주세요", page)

    def test_the_trial_shape_says_the_raised_list_price_in_the_red_line_box_and_the_cell(self):
        planned, page = self.check("trial-words", trial_scene.snapshot(), trial_scene.request(),
                                   [{"rule": "ABOVE_LIST", "choice": "raise_list"}])
        text = " ".join(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", page, flags=re.S)).split())
        self.assertIn("고르신 빨간 줄 · 24칸 (정가보다 비싸집니다) 정가도 12% 올림 (아동이 있는 칸은 아동 추가분은 그대로) · 24칸 정가도 그렇게 옮겨 저장합니다(ERP 「정가도 같이 조정」과 같은 계산). "
                      "예: 12/7 월 · 스탠다드 · 조식 포함 · 성인 2 · 1박 이상 — 판매가 100.00 → 112.00 정가 110.00 → 123.20", text)
        cell = read_grid(page)[("스탠다드 · 조식 포함", "12/7 월", "성인 2 · 1박 이상")]
        self.assertEqual([text for _tag, _cls, text in cell],
                         ["100.00", "→", "112.00", "정가 110.00 → 123.20", "정가도 12% 올림", "정가보다 비싸집니다 · 고르신 대로"])
        self.assertEqual(planned["plan"]["changes"][0]["after"]["list"], "123.20", "plan.json 의 칸도 올린 정가를 갖는다")
        self.assertEqual(planned["plan"]["changes"][0]["choice"], "raise_list")


class ChosenListThroughLedgerTest(CommandCase):
    """V1 — 고른 대로 올리거나 지운 정가는 장부에 넣은 값으로 적히고, 결과 페이지에 보이고, 되돌리면 원래 정가로 돌아온다."""

    def apply(self, name, snapshot, plan_file, change_id):
        """begin → calls → 저장마다 record-result(페이지가 저장했다고 답함) → 그 저장이 들어간 지금 값(scene.applied)."""
        fresh = self.write(f"{name}-fresh.json", dict(encode_snapshot(snapshot), read_at=now_text()))
        self.run_cli("begin", "--change", change_id, "--plan", plan_file, "--snapshot", fresh)
        for call in self.run_cli("calls", "--change", change_id)["calls"]:
            reply = {"ok": True, "op": call["op"], "no": call["no"], "ask": ask_sum(call["payload"]), "saved": True,
                     "pressed": True, "note": "저장했습니다"}
            last = self.run_cli("record-result", "--change", change_id, "--result", self.write(f"{name}-r{call['no']}.json", reply))
        self.assertEqual(last["status"], "applied")
        steps = json.loads(Path(plan_file).read_text(encoding="utf-8"))["steps"]
        return scene.applied(snapshot, map(decode_step, steps), now_text())

    def round_trip(self, choice):
        before, over = scene.snapshot(), CellKey("스위트", "조식 포함", "2027-01-01", "A2", 1)
        planned = self.run_cli("plan", "--snapshot", self.write(f"{choice}-snapshot.json", encode_snapshot(before)),
                               "--request", self.write(f"{choice}-request.json", encode_request(scene.request())),
                               "--resolutions", self.write(f"{choice}-choices.json", [{"rule": "ABOVE_LIST", "choice": choice}]),
                               "--record", "--out", self.dir / f"{choice}-plan.json")
        after = self.apply(choice, before, self.dir / f"{choice}-plan.json", planned["change_id"])
        rows = {row["field"]: row for row in self.ledger_rows(planned["change_id"], over)}
        verified = self.run_cli("verify", "--change", planned["change_id"],
                                "--snapshot", self.write(f"{choice}-after.json", encode_snapshot(after)))
        self.assertTrue(verified["same"])
        result = Path(self.run_cli("render", "result", "--change", planned["change_id"],
                                   "--out", self.dir / f"{choice}-result.html")["page"]).read_text(encoding="utf-8")
        back = self.run_cli("rollback", "--change", planned["change_id"], "--snapshot", self.dir / f"{choice}-after.json", "--record",
                            "--out", self.dir / f"{choice}-rollback.json")
        restored = next(item for item in back["rollback"]["restored"] if json.loads(item["key"]) == encode_key(over))
        undone = self.apply(f"{choice}-back", after, self.dir / f"{choice}-rollback.json", back["change_id"])
        return before, over, after, rows, result, restored, undone

    def ledger_rows(self, change_id, key):
        import sqlite3
        db = sqlite3.connect(self.dir / "기록" / "가격장부.sqlite3")
        db.row_factory = sqlite3.Row
        found = [dict(row) for row in db.execute("SELECT field, before, after, action, step, verdict, choice FROM item_values"
                                                 " WHERE change_id = ? AND item_key = ?",
                                                 (change_id, json.dumps(encode_key(key), ensure_ascii=False, sort_keys=True,
                                                                        separators=(",", ":"))))]
        db.close()
        return found

    def test_raise_list_is_written_shown_and_rolled_back(self):
        before, over, after, rows, result, restored, undone = self.round_trip("raise_list")
        self.assertEqual(after.cells[over].list, Decimal("550.00"))
        self.assertEqual({name: (row["after"], row["action"], row["choice"]) for name, row in rows.items()},
                         {"sell": ("528.00", "set", "raise_list"), "list": ("550.00", "set", "raise_list"),
                          "supply": (None, None, "raise_list")})
        self.assertIsNotNone(rows["list"]["step"], "올린 정가는 저장 단계가 넣은 값으로 적힌다")
        self.assertIn("정가 500.00 → 550.00", result)
        self.assertEqual(restored["targets"], {"sell": "480.00", "list": "500.00"})
        self.assertEqual(undone.cells[over], before.cells[over], "되돌리면 판매가와 정가가 모두 원래 값")

    def test_clear_list_is_written_shown_and_rolled_back(self):
        before, over, after, rows, result, restored, undone = self.round_trip("clear_list")
        self.assertIsNone(after.cells[over].list)
        self.assertEqual({name: (row["after"], row["action"]) for name, row in rows.items()},
                         {"sell": ("528.00", "set"), "list": (None, "clear"), "supply": (None, None)})
        self.assertIsNotNone(rows["list"]["step"], "지운 정가는 저장 단계가 비운 값으로 적힌다")
        self.assertIn("정가 500.00 → 비움", result)
        self.assertEqual(restored["targets"], {"sell": "480.00", "list": "500.00"})
        self.assertEqual(undone.cells[over], before.cells[over], "되돌리면 지운 정가가 다시 들어간다")


if __name__ == "__main__":
    unittest.main()
