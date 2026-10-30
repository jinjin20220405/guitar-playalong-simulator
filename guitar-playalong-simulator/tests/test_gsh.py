"""校验与展开逻辑的自动测试：python3 tests/test_gsh.py"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gsh  # noqa: E402

BASE = json.loads((ROOT / "examples" / "selftest.score.json").read_text(encoding="utf-8"))


def mutate(fn):
    s = copy.deepcopy(BASE)
    fn(s)
    return gsh.compile_score(s)


def errors_of(fn):
    payload, rep = mutate(fn)
    return payload, "\n".join(rep.errors)


def bar(s, n):
    return s["bars"][n - 1]


def simple_score(bars):
    return {"format": "guitar-score", "version": 1, "meta": {"title": "t"}, "tempo": [{"bar": 1, "bpm": 60}],
            "parts": [{"id": "v", "kind": "melody"}], "shapes": {}, "bars": bars}


def mbar(n, **kw):
    b = {"n": n, "voices": {"v": [{"dur": "1", "jp": "1"}]}}
    if n == 1:
        b["time"] = "4/4"
    b.update(kw)
    return b


class Valid(unittest.TestCase):
    def test_selftest_passes(self):
        payload, rep = gsh.compile_score(copy.deepcopy(BASE))
        self.assertIsNotNone(payload, rep.errors)
        order = [(s["bar"], s["pass"]) for s in payload["seq"]]
        self.assertEqual(order, [(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (2, 2), (3, 2), (4, 2), (6, 1),
                                 (7, 1), (8, 1), (9, 1), (10, 1), (11, 1)])

    def test_bar_lengths_and_tempo(self):
        payload, _ = gsh.compile_score(copy.deepcopy(BASE))
        b = payload["bars"]
        self.assertEqual(b[1]["len"], 0.25)       # 弱起
        self.assertEqual(b[8]["len"], 0.75)       # 3/4 沿用
        self.assertEqual(b[9]["len"], 0.5)        # 2/4
        self.assertEqual(b[10]["bpm"], 72)        # 中途变速
        seq = payload["seq"]
        self.assertAlmostEqual(seq[12]["dur"], 4 * 60 / 72)
        # 起始秒数由精确分数累计，最后一项 = 各小节之和
        self.assertAlmostEqual(payload["total"], sum(s["dur"] for s in seq), places=9)

    def test_strum_order_and_shape_lookup(self):
        payload, _ = gsh.compile_score(copy.deepcopy(BASE))
        ev = [e for e in payload["bars"][4]["events"] if e["o"] == 0] if "events" in payload["bars"][4] else \
            [e for e in payload["bars"][4]["ev"] if e["o"] == 0]
        self.assertEqual([e["s"] for e in ev if e["part"] == "g1"], [6, 5, 4, 3, 2, 1])  # F 下扫 6→1
        up = [e for e in payload["bars"][4]["ev"] if e["part"] == "g1" and e["o"] == 0.375]
        self.assertEqual([e["s"] for e in up], [1, 2, 3])                                  # 上扫 1→3
        g = [e for e in payload["bars"][4]["ev"] if e["part"] == "g1" and e["o"] == 0.5]
        self.assertEqual({e["s"]: e["f"] for e in g}, {6: 3, 5: 2, 4: 0, 3: 0, 2: 0, 1: 3})  # 小节中途换 G

    def test_tie_across_bar(self):
        payload, _ = gsh.compile_score(copy.deepcopy(BASE))
        mi = [e for e in payload["bars"][8]["ev"] if e["part"] == "vox"][-1]
        self.assertEqual(mi["lab"], "3")
        self.assertAlmostEqual(mi["d"], 0.5)   # 第8小节 1/4 + 第9小节延音 1/4
        self.assertFalse([e for e in payload["bars"][9]["ev"] if e["part"] == "vox"])

    def test_triplet_exact(self):
        payload, _ = gsh.compile_score(copy.deepcopy(BASE))
        v = [e["o"] for e in payload["bars"][7]["ev"] if e["part"] == "vox"]
        self.assertAlmostEqual(v[3], 0.25)


class Invalid(unittest.TestCase):
    def assertErr(self, fn, needle):
        payload, msg = errors_of(fn)
        self.assertIsNone(payload)
        self.assertIn(needle, msg)

    def test_bar_too_short(self):
        self.assertErr(lambda s: bar(s, 3)["voices"]["vox"].pop(), "总时值为 1/2，小节长度应为 1")

    def test_decimal_duration(self):
        self.assertErr(lambda s: bar(s, 3)["voices"]["vox"][0].update(dur=0.375), "分数字符串")

    def test_pos_mismatch(self):
        self.assertErr(lambda s: bar(s, 2)["voices"]["g1"][4].update(pos="3/8"), "标注拍位为 3/8")

    def test_bad_string(self):
        self.assertErr(lambda s: bar(s, 10)["voices"]["g2"][0]["notes"][0].update(s=7), "弦号应为 1–6")

    def test_bad_fret(self):
        self.assertErr(lambda s: bar(s, 10)["voices"]["g2"][0]["notes"][0].update(f=25), "品位应为 0–24")

    def test_pluck_muted_string(self):
        self.assertErr(lambda s: bar(s, 2)["voices"]["g1"][0].update(shape=[6]), "6 弦标为不弹")

    def test_unknown_shape(self):
        self.assertErr(lambda s: bar(s, 2)["chords"][0].update(shape="Cadd9"), "未在 shapes 中定义")

    def test_tie_without_previous(self):
        self.assertErr(lambda s: bar(s, 3)["voices"]["vox"][0].update(tie=True), "延音线前面没有紧邻的同音高音符")

    def test_bad_jianpu(self):
        self.assertErr(lambda s: bar(s, 3)["voices"]["vox"][0].update(jp="8"), "无法识别的音高")

    def test_melody_in_guitar(self):
        self.assertErr(lambda s: bar(s, 2)["voices"]["g1"][0].update({"jp": "1"}), "必须且只能是")

    def test_bad_time_signature(self):
        self.assertErr(lambda s: bar(s, 7).update(time="3/5"), "拍号无法识别")

    def test_bar_numbering(self):
        self.assertErr(lambda s: bar(s, 4).update(n=7), "小节号应为 4")

    def test_undefined_part(self):
        self.assertErr(lambda s: bar(s, 2)["voices"].update(bass=[{"dur": "1", "rest": True}]), "声部 'bass' 未在 parts 中定义")

    def test_bad_play_order(self):
        self.assertErr(lambda s: s.update(playOrder=[[1, 5], [9, 30]]), "playOrder[1]")

    def test_issue_refers_missing_bar(self):
        self.assertErr(lambda s: s["issues"][0].update(bar=99), "不存在的小节 99")

    def test_json_syntax_error(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            fh.write('{"format": "guitar-score",\n "version": 1,,}')
        with self.assertRaises(gsh.ScoreError) as cm:
            gsh.load(fh.name)
        self.assertIn("第 2 行", str(cm.exception))

    def test_draft_flag(self):
        def f(s):
            s["issues"].append({"id": "Q9", "bar": 3, "level": "key", "status": "open", "desc": "x"})
        payload, rep = mutate(f)
        self.assertTrue(payload["draft"])


class Repeats(unittest.TestCase):
    def order(self, bars, **extra):
        s = simple_score(bars)
        s.update(extra)
        payload, rep = gsh.compile_score(s)
        self.assertIsNotNone(payload, rep.errors)
        return [(x["bar"], x["pass"]) for x in payload["seq"]]

    def test_repeat_without_start_goes_to_bar1(self):
        o = self.order([mbar(1), mbar(2, repeatEnd=2), mbar(3)])
        self.assertEqual([b for b, _ in o], [1, 2, 1, 2, 3])

    def test_three_times_with_endings(self):
        o = self.order([mbar(1), mbar(2, repeatStart=True), mbar(3, ending=[1, 2], repeatEnd=3),
                        mbar(4, ending=[3]), mbar(5)])
        self.assertEqual([b for b, _ in o], [1, 2, 3, 2, 3, 2, 4, 5])

    def test_two_repeat_sections(self):
        o = self.order([mbar(1, repeatStart=True), mbar(2, repeatEnd=2), mbar(3, repeatStart=True),
                        mbar(4, ending=[1], repeatEnd=2), mbar(5, ending=[2]), mbar(6)])
        self.assertEqual([b for b, _ in o], [1, 2, 1, 2, 3, 4, 3, 5, 6])

    def test_play_order_override(self):
        o = self.order([mbar(1), mbar(2), mbar(3), mbar(4)], playOrder=[[1, 3], [2, 2], [4, 4]])
        self.assertEqual(o, [(1, 1), (2, 1), (3, 1), (2, 2), (4, 1)])

    def test_first_ending_without_repeat_end(self):
        s = simple_score([mbar(1), mbar(2, ending=[1]), mbar(3)])
        payload, rep = gsh.compile_score(s)
        self.assertIsNone(payload)
        self.assertIn("第一房后面没有反复结束记号", "\n".join(rep.errors))


class Sections(unittest.TestCase):
    def test_resolve_with_pass(self):
        # 自编谱展开为 1 2 3 4 5 2 3 4 6 ...
        payload, rep = mutate(lambda s: s.update(sections=[{"name": "第1遍", "from": 2, "to": 4},
                                                            {"name": "第2遍", "from": 2, "to": 6, "pass": 2}]))
        self.assertIsNotNone(payload, rep.errors)
        self.assertEqual(payload["sections"], [{"name": "第1遍", "a": 1, "b": 3}, {"name": "第2遍", "a": 5, "b": 8}])

    def test_missing_pass(self):
        _, errs = errors_of(lambda s: s.update(sections=[{"name": "x", "from": 2, "to": 4, "pass": 3}]))
        self.assertIn("第2小节的第3遍", errs)

    def test_to_not_after_from(self):
        _, errs = errors_of(lambda s: s.update(sections=[{"name": "x", "from": 6, "to": 2}]))
        self.assertIn("没有第2小节", errs)

    def test_absent_is_empty(self):
        payload, _ = mutate(lambda s: s.pop("sections"))
        self.assertEqual(payload["sections"], [])

    def test_selftest_sections(self):
        payload, _ = gsh.compile_score(copy.deepcopy(BASE))
        self.assertEqual([(x["a"], x["b"]) for x in payload["sections"]], [(0, 0), (1, 4), (5, 7), (8, 13)])


class Leaps(unittest.TestCase):
    def leaps(self, spec, status="draft"):
        bars = []
        for i, notes in enumerate(spec, 1):
            b = mbar(i, status=status)
            b["voices"]["v"] = [{"dur": "1/4", "jp": x} if x != "0" else {"dur": "1/4", "rest": True} for x in notes]
            bars.append(b)
        payload, rep = gsh.compile_score(simple_score(bars))
        self.assertIsNotNone(payload, rep.errors)
        return payload["leaps"]

    def test_octave_slip_found(self):
        # 4 3 2 读成中音，后面接高音 3：上跳 14 个半音
        got = self.leaps([["4", "3", "2", "3'"]])
        self.assertEqual(len(got), 1)
        self.assertIn("2 → 第1小节 3'", got[0])

    def test_real_leap_and_rest_not_reported(self):
        self.assertEqual(self.leaps([["1", "5", "1'", "5"], ["2", "0", "3'", "2'"]]), [])

    def test_leap_ok_on_resolved_issue(self):
        bars = [mbar(1)]
        bars[0]["voices"]["v"] = [{"dur": "1/4", "jp": x} for x in ("4", "3", "2", "3'")]
        sc = simple_score(bars)
        sc["issues"] = [{"id": "Q1", "bar": 1, "level": "key", "status": "open", "leapOk": [1]}]
        self.assertEqual(len(gsh.compile_score(sc)[0]["leaps"]), 1)      # 未解决时照报
        sc["issues"][0]["status"] = "resolved"
        self.assertEqual(gsh.compile_score(sc)[0]["leaps"], [])

    def test_confirmed_bars_skipped(self):
        self.assertEqual(self.leaps([["4", "3", "2", "3'"]], status="confirmed"), [])


class Build(unittest.TestCase):
    def test_build_embeds_full_source(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.html"
            rc = gsh.main(["build", str(ROOT / "examples" / "selftest.score.json"), "-o", str(out)])
            self.assertEqual(rc, 0)
            html = out.read_text(encoding="utf-8")
            start = html.index("const DATA=") + len("const DATA=")
            end = html.index(";\nconst P=DATA.play")
            blob = json.loads(html[start:end])
            self.assertEqual(blob["source"], BASE)   # 重新打开后内嵌的工程数据与原文件完全一致
            self.assertNotIn("http://", html.replace("http://www.w3.org/2000/svg", ""))
            self.assertNotIn("https://", html)


class PitchCheck(unittest.TestCase):
    def score(self, fret):
        return {"format": "guitar-score", "version": 1, "meta": {"title": "t"}, "tempo": [{"bar": 1, "bpm": 60}],
                "parts": [{"id": "g", "kind": "guitar"}, {"id": "v", "kind": "melody"}], "shapes": {},
                "bars": [{"n": 1, "time": "4/4", "voices": {
                    "g": [{"dur": "1/2", "notes": [{"s": 2, "f": 8}]}, {"dur": "1/2", "notes": [{"s": 1, "f": fret}]}],
                    "v": [{"dur": "1/2", "jp": "5'"}, {"dur": "1/4", "jp": "5'"}, {"dur": "1/4", "rest": True}]}}]}

    def test_octave_and_mismatch(self):
        payload, _ = gsh.compile_score(self.score(12))
        mismatch, octave = gsh.pitch_check(payload, "g", "v")
        self.assertEqual(len(octave), 1)            # 2弦8品 = G4，简谱 5' = G5：只差八度
        self.assertIn("1弦12品=E5", mismatch[0])    # 读错品位：音名不同

    def test_all_match(self):
        payload, _ = gsh.compile_score(self.score(15))
        mismatch, octave = gsh.pitch_check(payload, "g", "v")
        self.assertEqual((len(mismatch), len(octave)), (0, 1))


class Display(unittest.TestCase):
    def test_display_keeps_written_durations(self):
        payload, _ = gsh.compile_score(copy.deepcopy(BASE))
        dv = [e for e in payload["bars"][8]["dv"] if e["part"] == "vox"]
        self.assertEqual([e["d"] for e in dv], [0.5, 0.25])   # 延音线不改变显示时值
        b9 = [e for e in payload["bars"][9]["dv"] if e["part"] == "vox"]
        self.assertTrue(b9[0]["tie"])
        self.assertEqual(b9[1]["k"], "rest")
        self.assertIn("G", payload["shapes"])


class ImageTools(unittest.TestCase):
    """裁图缩图的后端选择与开工自检。真出图需要图片文件，这里只测选择逻辑与自检命令。"""

    def test_backend_is_known(self):
        kind, exe = gsh.image_backend()
        self.assertIn(kind, ("sips", "magick", "convert", "pillow", "none"))
        if kind in ("sips", "magick", "convert"):
            self.assertTrue(exe)

    def test_env_command_runs(self):
        import argparse
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = gsh.cmd_env(argparse.Namespace())
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("图像处理后端", out)
        self.assertIn("播放器模板：有", out)

    def test_fit_only_shrinks_when_asked(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("未安装 Pillow")
        im = Image.new("RGB", (400, 200))
        self.assertEqual(gsh._fit(im, 800, only_shrink=True).size, (400, 200))  # 不放大
        self.assertEqual(gsh._fit(im, 100).size, (100, 50))                     # 按比例缩


if __name__ == "__main__":
    unittest.main(verbosity=1)
