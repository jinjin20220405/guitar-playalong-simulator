#!/usr/bin/env python3
"""吉他曲谱工程数据：校验、展开、生成离线 HTML 播放器。

用法：
  python3 gsh.py check  score.json
  python3 gsh.py build  score.json [-i 原谱1.png -i 原谱2.png] [-o 输出.html]
  python3 gsh.py order  score.json        # 列出展开后的播放顺序
  python3 gsh.py pitchcheck score.json --part g2 [--melody vox]   # 吉他旋律与简谱逐音互校
  python3 gsh.py crop   原谱.png 左 上 宽 高 -o 裁图.png [--ref 2000]  # 裁图放大，供逐小节识读（macOS sips）
  python3 gsh.py shrink 原谱.png -o 缩小.png [--width 4000]           # 缩小原谱，供嵌入播放器

只依赖 Python 3.8+ 标准库。数据格式见 ../references/format.md。
"""
import argparse
import base64
import json
import mimetypes
import re
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "template" / "player.html"
FORMAT_VERSION = 1
STD_TUNING = {"6": "E2", "5": "A2", "4": "D3", "3": "G3", "2": "B3", "1": "E4"}
MAX_EXPANDED = 5000

NOTE_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
JP_STEP = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}


class ScoreError(Exception):
    pass


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}：{msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}：{msg}")


def frac(v, where, rep):
    """把 "3/8"、"0"、"1" 之类转成精确分数；拒绝小数，避免误差。"""
    if isinstance(v, int) and not isinstance(v, bool):
        return Fraction(v)
    if isinstance(v, str) and re.fullmatch(r"\s*\d+\s*(/\s*\d+\s*)?", v):
        a, _, b = v.partition("/")
        if b and int(b) == 0:
            rep.err(where, f"分母为 0：{v!r}")
            return None
        return Fraction(int(a), int(b) if b else 1)
    rep.err(where, f"时值或拍位应写成分数字符串，如 \"1/8\"，实际为 {v!r}")
    return None


def pitch_to_midi(name):
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d)", str(name).strip())
    if not m:
        return None
    n = NOTE_BASE[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return 12 * (int(m.group(3)) + 1) + n


def key_to_midi(key):
    """简谱 1 的音高，落在 C4 所在八度。"""
    m = re.fullmatch(r"([#b]?)([A-Ga-g])", str(key).strip())
    if not m:
        return None
    return 60 + NOTE_BASE[m.group(2).upper()] + {"#": 1, "b": -1, "": 0}[m.group(1)]


def jp_to_midi(jp, tonic):
    m = re.fullmatch(r"([#b]?)([1-7])([',]*)", str(jp).strip())
    if not m:
        return None
    v = tonic + JP_STEP[int(m.group(2))] + {"#": 1, "b": -1, "": 0}[m.group(1)]
    v += 12 * m.group(3).count("'") - 12 * m.group(3).count(",")
    return v


def parse_time(sig):
    m = re.fullmatch(r"(\d+)/(\d+)", str(sig))
    if not m or int(m.group(1)) == 0 or int(m.group(2)) not in (1, 2, 4, 8, 16):
        return None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------- 校验与编译

def lyric_list(ev):
    """lyric 可写一个字，也可写列表（多段歌词，第 n 项为第 n 段，没有的写空串）。统一返回列表或 None。"""
    v = ev.get("lyric")
    if isinstance(v, list):
        out = ["" if x is None else str(x) for x in v]
        return out if any(out) else None
    return [str(v)] if v else None


def compile_score(score):
    """校验整份数据，并编译成播放器用的结构。返回 (compiled, report)。"""
    rep = Report()
    if not isinstance(score, dict):
        rep.err("文件", "顶层必须是 JSON 对象")
        return None, rep
    if score.get("format") != "guitar-score":
        rep.err("format", "应为 \"guitar-score\"")
    if score.get("version") != FORMAT_VERSION:
        rep.err("version", f"本脚本只支持版本 {FORMAT_VERSION}，文件中为 {score.get('version')!r}")

    meta = score.get("meta") or {}
    if not meta.get("title"):
        rep.err("meta.title", "缺少曲名")

    # 调弦与变调夹
    tuning_src = score.get("tuning") or STD_TUNING
    tuning = {}
    for s in range(1, 7):
        name = tuning_src.get(str(s))
        midi = pitch_to_midi(name) if name is not None else None
        if midi is None:
            rep.err("tuning", f"{s} 弦的空弦音高无法识别：{name!r}")
        tuning[s] = midi
    capo = score.get("capo", 0)
    if not isinstance(capo, int) or not 0 <= capo <= 12:
        rep.err("capo", f"变调夹品位应为 0–12 的整数，实际为 {capo!r}")
        capo = 0
    tonic = key_to_midi(score.get("key", "C"))
    if tonic is None:
        rep.err("key", f"无法识别的调：{score.get('key')!r}")
        tonic = 60

    # 声部
    parts = score.get("parts") or []
    part_kind = {}
    for i, p in enumerate(parts):
        pid = p.get("id")
        if not pid or pid in part_kind:
            rep.err(f"parts[{i}]", f"声部 id 缺失或重复：{pid!r}")
            continue
        if p.get("kind") not in ("guitar", "melody"):
            rep.err(f"parts[{i}]", f"kind 只能是 guitar 或 melody，实际为 {p.get('kind')!r}")
        part_kind[pid] = p.get("kind")
    if not parts:
        rep.err("parts", "至少要有一个声部")

    # 指型
    shapes = {}
    for key, sh in (score.get("shapes") or {}).items():
        fr = (sh or {}).get("frets") or {}
        out = {}
        for s in range(1, 7):
            v = fr.get(str(s))
            if v == "x":
                out[s] = None
            elif isinstance(v, int) and 0 <= v <= 24:
                out[s] = v
            else:
                rep.err(f"shapes.{key}", f"{s} 弦应为 0–24 的品位或 \"x\"，实际为 {v!r}")
                out[s] = None
        shapes[key] = {"name": sh.get("name", key), "frets": out}

    # 速度表
    tempo = {}
    for i, t in enumerate(score.get("tempo") or []):
        bpm = t.get("bpm")
        if not isinstance(t.get("bar"), int) or not isinstance(bpm, (int, float)) or not 20 <= bpm <= 300:
            rep.err(f"tempo[{i}]", f"应为 {{\"bar\": 小节号, \"bpm\": 20–300}}，实际为 {t!r}")
            continue
        tempo[t["bar"]] = float(bpm)
    if 1 not in tempo:
        rep.err("tempo", "第 1 小节必须有速度")
        tempo.setdefault(1, 80.0)

    # 小节
    bars = score.get("bars") or []
    if not bars:
        rep.err("bars", "没有小节")
    cbars = {}
    time_sig, cur_shape, cur_bpm = None, None, tempo.get(1, 80.0)
    bar_abs = Fraction(0)  # 本小节在谱面顺序中的绝对起点，用于跨小节延音线
    last_note = {pid: {} for pid in part_kind}  # 声部 → 弦号或 "m" → (事件, 绝对结束位置)
    for bi, bar in enumerate(bars):
        n = bar.get("n")
        here = f"第{n}小节"
        if n != bi + 1:
            rep.err(f"bars[{bi}]", f"小节号应为 {bi + 1}（连续编号），实际为 {n!r}")
            n = bi + 1
            here = f"第{n}小节"
        if n in tempo:
            cur_bpm = tempo[n]
        if "time" in bar:
            ts = parse_time(bar["time"])
            if not ts:
                rep.err(here, f"拍号无法识别：{bar['time']!r}")
            else:
                time_sig = ts
        if time_sig is None:
            rep.err(here, "缺少拍号（第一小节必须写 time）")
            time_sig = (4, 4)
        full_len = Fraction(time_sig[0], time_sig[1])
        length = full_len
        if bar.get("partial") is not None:
            pl = frac(bar["partial"], f"{here} partial", rep)
            if pl is not None:
                if not 0 < pl <= full_len:
                    rep.err(here, f"partial 应大于 0 且不超过拍号长度 {full_len}")
                else:
                    length = pl

        # 和弦生效位置
        chords = []
        last_pos = Fraction(-1)
        for ci, c in enumerate(bar.get("chords") or []):
            pos = frac(c.get("pos", "0"), f"{here} chords[{ci}]", rep)
            key = c.get("shape")
            if key not in shapes:
                rep.err(here, f"和弦指型 {key!r} 未在 shapes 中定义")
                continue
            if pos is None:
                continue
            if pos <= last_pos or pos >= length:
                rep.err(here, f"和弦 {key} 的位置 {pos} 不在小节内或未按顺序")
                continue
            chords.append((pos, key))
            last_pos = pos

        def shape_at(pos, _chords=chords, _start=cur_shape):
            k = _start
            for p, key in _chords:
                if pos >= p:
                    k = key
            return k

        bar_events, bar_disp = [], []
        voices = bar.get("voices") or {}
        for pid, evs in voices.items():
            if pid not in part_kind:
                rep.err(here, f"声部 {pid!r} 未在 parts 中定义")
                continue
            kind = part_kind[pid]
            pos = Fraction(0)
            ln = last_note[pid]
            for ei, ev in enumerate(evs):
                w = f"{here} {pid} 第{ei + 1}个事件"
                d = frac(ev.get("dur"), w, rep)
                if d is None:
                    break
                if d <= 0:
                    rep.err(w, "时值必须大于 0")
                    break
                if "pos" in ev:
                    given = frac(ev["pos"], w, rep)
                    if given is not None and given != pos:
                        rep.err(w, f"标注拍位为 {given}，但按前面时值累计应为 {pos}")
                vel = ev.get("vel", 0.8)
                if not isinstance(vel, (int, float)) or not 0 < vel <= 1:
                    rep.err(w, f"力度 vel 应在 0–1 之间，实际为 {vel!r}")
                    vel = 0.8
                if ev.get("accent"):
                    vel = min(1.0, vel + 0.2)
                kinds = [k for k in ("notes", "shape", "strum", "rest", "jp", "pitch") if k in ev]
                if len(kinds) != 1:
                    rep.err(w, f"事件必须且只能是 notes/shape/strum/rest/jp/pitch 之一，实际为 {kinds or '无'}")
                    pos += d
                    continue
                k = kinds[0]
                # 谱面显示用：按原写法记录（时值不受延音线合并影响）
                dv = {"part": pid, "o": pos, "d": d, "k": k}
                for flag in ("accent", "mute", "tie"):
                    if ev.get(flag):
                        dv[flag] = True
                if k == "notes" and isinstance(ev["notes"], list):
                    dv["notes"] = [{x: nt[x] for x in ("s", "f", "x", "tie", "tech") if x in nt}
                                   for nt in ev["notes"] if isinstance(nt, dict)]
                elif k in ("shape", "strum") and shape_at(pos) is not None:
                    fr = shapes[shape_at(pos)]["frets"]
                    if k == "shape":
                        dv["strings"] = [s for s in ev["shape"] if isinstance(s, int) and 1 <= s <= 6]
                    else:
                        dv["dir"] = "d" if ev["strum"] == "down" else "u"
                        dv["strings"] = [s for s in (ev.get("strings") or [s for s in range(1, 7) if fr[s] is not None])
                                         if isinstance(s, int) and 1 <= s <= 6]
                    dv["frets"] = {str(s): fr[s] for s in dv["strings"]}
                elif k in ("jp", "pitch"):
                    dv["lab"] = str(ev[k])
                    if lyric_list(ev):
                        dv["ly"] = lyric_list(ev)
                bar_disp.append(dv)
                if kind == "melody" and k in ("notes", "shape", "strum"):
                    rep.err(w, "旋律声部只能用 jp、pitch 或 rest")
                elif kind == "guitar" and k in ("jp", "pitch"):
                    rep.err(w, "吉他声部不能用 jp 或 pitch，应写弦号和品位")
                elif k == "rest":
                    pass
                elif k in ("jp", "pitch"):
                    midi = jp_to_midi(ev[k], tonic) if k == "jp" else pitch_to_midi(ev[k])
                    if midi is None:
                        rep.err(w, f"无法识别的音高：{ev[k]!r}")
                    elif not 36 <= midi <= 96:
                        rep.err(w, f"音高超出合理范围：{ev[k]!r}")
                    elif ev.get("tie"):
                        prev, end = ln.get("m", (None, None))
                        if prev is None or prev["midi"] != midi or end != bar_abs + pos:
                            rep.err(w, "延音线前面没有紧邻的同音高音符")
                        else:
                            prev["d"] += d
                            ln["m"] = (prev, end + d)
                    else:
                        e = {"part": pid, "o": pos, "d": d, "t": "m", "midi": midi, "v": vel, "lab": str(ev[k])}
                        if lyric_list(ev):
                            e["ly"] = lyric_list(ev)
                        bar_events.append(e)
                        ln["m"] = (e, bar_abs + pos + d)
                elif k == "notes":
                    if not ev["notes"]:
                        rep.err(w, "notes 为空")
                    seen = set()
                    for nt in ev["notes"]:
                        s, f = nt.get("s"), nt.get("f", 0 if nt.get("x") else None)
                        if not isinstance(s, int) or not 1 <= s <= 6:
                            rep.err(w, f"弦号应为 1–6，实际为 {s!r}")
                            continue
                        if s in seen:
                            rep.err(w, f"{s} 弦在同一时刻出现两次")
                        seen.add(s)
                        if not isinstance(f, int) or not 0 <= f <= 24:
                            rep.err(w, f"{s} 弦品位应为 0–24，实际为 {f!r}")
                            continue
                        if nt.get("tech"):
                            rep.warn(w, f"技巧 {nt['tech']!r} 本版只记录、不演奏")
                        midi = tuning[s] + f + capo if tuning[s] is not None else 60
                        if nt.get("tie"):
                            prev, end = ln.get(s, (None, None))
                            if prev is None or prev["midi"] != midi or end != bar_abs + pos:
                                rep.err(w, f"{s} 弦的延音线前面没有紧邻的同音")
                            else:
                                prev["d"] += d
                                ln[s] = (prev, end + d)
                            continue
                        e = {"part": pid, "o": pos, "d": d, "t": "x" if nt.get("x") else "n",
                             "s": s, "f": f, "midi": midi, "v": vel}
                        bar_events.append(e)
                        ln[s] = (e, bar_abs + pos + d)
                elif k == "shape":
                    sk = shape_at(pos)
                    if sk is None:
                        rep.err(w, "按指型拨弦，但此前没有任何和弦生效")
                    else:
                        for s in ev["shape"]:
                            if not isinstance(s, int) or not 1 <= s <= 6:
                                rep.err(w, f"弦号应为 1–6，实际为 {s!r}")
                                continue
                            f = shapes[sk]["frets"][s]
                            if f is None:
                                rep.err(w, f"当前和弦 {shapes[sk]['name']} 的 {s} 弦标为不弹，却要求拨该弦")
                                continue
                            e = {"part": pid, "o": pos, "d": d, "t": "n", "s": s, "f": f,
                                 "midi": tuning[s] + f + capo, "v": vel, "c": 1}
                            bar_events.append(e)
                            ln[s] = (e, bar_abs + pos + d)
                elif k == "strum":
                    direction = ev["strum"]
                    if direction not in ("down", "up"):
                        rep.err(w, f"strum 只能是 down 或 up，实际为 {direction!r}")
                        direction = "down"
                    sk = shape_at(pos)
                    if sk is None:
                        rep.err(w, "扫弦时没有生效的和弦")
                    else:
                        frets = shapes[sk]["frets"]
                        strings = ev.get("strings") or [s for s in range(6, 0, -1) if frets[s] is not None]
                        strings = sorted(strings, reverse=(direction == "down"))
                        playable = []
                        for s in strings:
                            if not isinstance(s, int) or not 1 <= s <= 6:
                                rep.err(w, f"弦号应为 1–6，实际为 {s!r}")
                            elif frets[s] is None and not ev.get("mute"):
                                rep.err(w, f"当前和弦 {shapes[sk]['name']} 的 {s} 弦标为不弹，却在扫弦范围内")
                            else:
                                playable.append(s)
                        for i, s in enumerate(playable):
                            f = frets[s] or 0
                            e = {"part": pid, "o": pos, "d": d, "t": "x" if ev.get("mute") else "n",
                                 "s": s, "f": f, "midi": tuning[s] + f + capo,
                                 "v": vel * (0.9 if direction == "up" else 1.0),
                                 "sd": i, "dir": direction[0]}
                            bar_events.append(e)
                            ln[s] = (e, bar_abs + pos + d)
                pos += d
            if pos != length:
                hint = "（若为弱起小节，请写 partial）" if pos < length else ""
                rep.err(here, f"声部 {pid} 总时值为 {pos}，小节长度应为 {length}{hint}")

        rs = bar.get("repeatEnd", 0) or 0
        if not isinstance(rs, int) or rs < 0 or rs == 1 or rs > 8:
            rep.err(here, f"repeatEnd 应为 0 或 2–8 的整数，实际为 {rs!r}")
            rs = 0
        ending = bar.get("ending")
        if ending is not None and (not isinstance(ending, list) or not ending
                                   or not all(isinstance(x, int) and x >= 1 for x in ending)):
            rep.err(here, f"ending 应为如 [1] 或 [1,2] 的列表，实际为 {ending!r}")
            ending = None
        if bar.get("status", "draft") not in ("draft", "doubt", "confirmed"):
            rep.err(here, f"status 只能是 draft、doubt、confirmed，实际为 {bar.get('status')!r}")
        img = bar.get("img")
        if img is not None:
            box = img.get("box") if isinstance(img, dict) else None
            if not (isinstance(box, list) and len(box) == 4 and all(isinstance(x, (int, float)) for x in box)):
                rep.err(here, "img 应为 {\"page\": 0, \"box\": [左, 上, 宽, 高]}")
                img = None

        bar_events.sort(key=lambda e: (e["o"], e.get("sd", 0)))
        # 本小节所有可能出现的指型（含沿用的），用于显示
        shown = []
        if cur_shape is not None and (not chords or chords[0][0] > 0):
            shown.append((Fraction(0), cur_shape, False))
        shown += [(p, k, True) for p, k in chords]
        cbars[n] = {
            "n": n, "time": f"{time_sig[0]}/{time_sig[1]}", "beats": time_sig[0], "unit": time_sig[1],
            "len": length, "bpm": cur_bpm, "events": bar_events, "disp": bar_disp,
            "chords": [(p, shapes[k]["name"], k, written) for p, k, written in shown],
            "repeatStart": bool(bar.get("repeatStart")), "repeatEnd": rs, "ending": ending,
            "img": img, "status": bar.get("status", "draft"),
            "showTime": "time" in bar or n == 1,
        }
        if chords:
            cur_shape = chords[-1][1]
        bar_abs += length

    for pid, kind in part_kind.items():
        if not any(e["part"] == pid for b in cbars.values() for e in b["events"]):
            rep.warn(f"声部 {pid}", "全曲没有任何发声事件")

    order = expand_order(score, cbars, rep)
    sections = resolve_sections(score, cbars, order, rep)

    issues = score.get("issues") or []
    for i, q in enumerate(issues):
        if q.get("bar") is not None and q.get("bar") not in cbars:
            rep.err(f"issues[{i}]", f"引用了不存在的小节 {q.get('bar')!r}")
        if q.get("status") not in ("open", "resolved"):
            rep.err(f"issues[{i}]", "status 只能是 open 或 resolved")
        if q.get("level") not in ("key", "minor"):
            rep.err(f"issues[{i}]", "level 只能是 key 或 minor")

    if rep.errors:
        return None, rep
    payload = build_payload(score, parts, cbars, order, capo, sections)
    payload["leaps"] = melody_leaps(payload)
    return payload, rep


def expand_order(score, cbars, rep):
    """返回 [(小节号, 第几遍)]。playOrder 优先，否则按反复记号展开。"""
    nbars = len(cbars)
    if not nbars:
        return []
    po = score.get("playOrder")
    if po:
        out, count = [], {}
        for i, seg in enumerate(po):
            if not (isinstance(seg, list) and len(seg) == 2 and all(isinstance(x, int) for x in seg)
                    and 1 <= seg[0] <= seg[1] <= nbars):
                rep.err(f"playOrder[{i}]", f"应为 [起始小节, 结束小节]，且在 1–{nbars} 之内，实际为 {seg!r}")
                return []
            for n in range(seg[0], seg[1] + 1):
                count[n] = count.get(n, 0) + 1
                out.append((n, count[n]))
        return out

    # 先检查反复记号是否配对
    open_at = None
    for n in range(1, nbars + 1):
        b = cbars[n]
        if b["repeatStart"]:
            if open_at is not None and not any(cbars[k]["repeatEnd"] for k in range(open_at, n)):
                rep.err(f"第{n}小节", f"第{open_at}小节的反复开始记号还没有对应的结束记号")
            open_at = n
        if b["repeatEnd"]:
            open_at = None
    endings = [n for n in range(1, nbars + 1) if cbars[n]["ending"]]
    for n in endings:
        if not any(cbars[k]["repeatEnd"] for k in range(n, nbars + 1)) and 1 in cbars[n]["ending"]:
            rep.err(f"第{n}小节", "第一房后面没有反复结束记号")

    out, i, start, passes, count = [], 1, 1, {}, {}
    while i <= nbars:
        if len(out) > MAX_EXPANDED:
            rep.err("反复结构", f"展开后超过 {MAX_EXPANDED} 个小节，反复记号可能有误")
            return []
        b = cbars[i]
        if b["repeatStart"] and start != i:
            start = i
            passes[start] = passes.get(start, 1)
        cur_pass = passes.get(start, 1)
        if b["ending"] and cur_pass not in b["ending"]:
            i += 1
            continue
        count[i] = count.get(i, 0) + 1
        out.append((i, count[i]))
        if b["repeatEnd"] and cur_pass < b["repeatEnd"]:
            passes[start] = cur_pass + 1
            i = start
            continue
        if b["repeatEnd"]:
            passes[start] = 1
            start = i + 1
        i += 1
    return out


def resolve_sections(score, cbars, order, rep):
    """段落按钮：把 [起止小节, 第几遍] 换算成播放序列中的起止位置（从 0 起，含两端）。"""
    out = []
    for i, sec in enumerate(score.get("sections") or []):
        where = f"sections[{i}]"
        if not isinstance(sec, dict) or not sec.get("name"):
            rep.err(where, "每个段落应为对象，且有 name")
            continue
        a, b, p = sec.get("from"), sec.get("to"), sec.get("pass", 1)
        if not (isinstance(a, int) and isinstance(b, int) and a in cbars and b in cbars):
            rep.err(where, f"from、to 应为存在的小节号，实际为 {a!r}、{b!r}")
            continue
        if not isinstance(p, int) or p < 1:
            rep.err(where, f"pass 应为从 1 起的整数，实际为 {p!r}")
            continue
        start = next((k for k, x in enumerate(order) if x == (a, p)), None)
        if start is None:
            rep.err(where, f"播放顺序里没有第{a}小节的第{p}遍")
            continue
        end = next((k for k in range(start, len(order)) if order[k][0] == b), None)
        if end is None:
            rep.err(where, f"从第{a}小节（第{p}遍）往后，播放顺序里没有第{b}小节")
            continue
        out.append({"name": sec["name"], "a": start, "b": end})
    return out


def fnum(x):
    return float(x)


def build_payload(score, parts, cbars, order, capo, sections=()):
    """播放器只拿编译结果：每小节的事件按“全音符”偏移，播放序列带起始秒数（原速）。"""
    bars_out = {}
    for n, b in cbars.items():
        bars_out[n] = {
            "n": n, "time": b["time"], "showTime": b["showTime"], "beats": b["beats"], "unit": b["unit"],
            "len": fnum(b["len"]), "bpm": b["bpm"], "status": b["status"],
            "chords": [[fnum(p), name, key, written] for p, name, key, written in b["chords"]],
            "rs": b["repeatStart"], "re": b["repeatEnd"], "end": b["ending"], "img": b["img"],
            "ev": [{k: (fnum(v) if isinstance(v, Fraction) else v) for k, v in e.items()} for e in b["events"]],
            "dv": [{k: (fnum(v) if isinstance(v, Fraction) else v) for k, v in e.items()} for e in b["disp"]],
        }
    seq, t = [], Fraction(0)
    for n, p in order:
        b = cbars[n]
        dur = b["len"] * 4 * 60 / Fraction(b["bpm"]).limit_denominator(1000)
        seq.append({"bar": n, "pass": p, "t": fnum(t), "dur": fnum(dur)})
        t += dur
    open_key = [q for q in score.get("issues") or [] if q.get("level") == "key" and q.get("status") == "open"]
    return {
        "title": score["meta"].get("title", ""),
        "meta": score.get("meta", {}),
        "kind": score["meta"].get("kind", "transcription"),
        "capo": capo, "key": score.get("key", "C"),
        "parts": [{"id": p["id"], "name": p.get("name", p["id"]), "kind": p["kind"]} for p in parts],
        "shapes": {k: {"name": (v or {}).get("name", k), "frets": (v or {}).get("frets") or {}}
                   for k, v in (score.get("shapes") or {}).items()},
        "bars": bars_out, "seq": seq, "total": fnum(t), "sections": list(sections),
        "issues": score.get("issues") or [], "assumptions": score.get("assumptions") or [],
        "draft": bool(open_key),
    }


# ---------------------------------------------------------------- 命令

def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise ScoreError(f"找不到文件：{path}")
    except json.JSONDecodeError as e:
        raise ScoreError(f"JSON 语法错误：第 {e.lineno} 行第 {e.colno} 列，{e.msg}")


def print_report(rep):
    for w in rep.warnings:
        print("  提醒 · " + w)
    for e in rep.errors:
        print("  错误 · " + e)


def cmd_check(args):
    score = load(args.score)
    payload, rep = compile_score(score)
    print_report(rep)
    if payload is None:
        print(f"校验未通过：{len(rep.errors)} 处错误。")
        return 1
    leaps = payload["leaps"]
    for x in leaps:
        print("  大跳 · " + x)
    nbar = len(payload["bars"])
    print(f"校验通过：{nbar} 个小节，展开后 {len(payload['seq'])} 个播放位置，"
          f"原速时长 {payload['total']:.1f} 秒，{len(rep.warnings)} 条提醒，{len(leaps)} 处旋律大跳待核对八度。")
    if payload["draft"]:
        print("存在未解决的关键疑点：生成的播放器将标为“待校对试听版”。")
    return 0


def cmd_order(args):
    payload, rep = compile_score(load(args.score))
    print_report(rep)
    if payload is None:
        return 1
    for i, s in enumerate(payload["seq"], 1):
        print(f"{i:4d}  第{s['bar']}小节（第{s['pass']}遍）  {s['t']:7.2f}s")
    return 0


def cmd_build(args):
    score = load(args.score)
    payload, rep = compile_score(score)
    print_report(rep)
    if payload is None:
        print(f"未生成：{len(rep.errors)} 处错误，请先修正。")
        return 1
    images = []
    for p in args.image or []:
        path = Path(p)
        if not path.exists():
            print(f"找不到原谱图片：{p}")
            return 1
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        images.append("data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode()))
    html = TEMPLATE.read_text(encoding="utf-8")
    blob = {"source": score, "play": payload, "images": images}
    # 防止数据里的 </script> 提前结束脚本块
    data = json.dumps(blob, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    if "/*__SCORE_DATA__*/null" not in html:
        print("播放器模板缺少数据占位符，模板文件可能已损坏。")
        return 1
    html = html.replace("/*__SCORE_DATA__*/null", data, 1)
    i18n = TEMPLATE.parent / "i18n.json"
    if "/*__I18N__*/null" not in html or not i18n.exists():
        print("播放器模板缺少界面语言文字表（template/i18n.json），模板文件可能不完整。")
        return 1
    html = html.replace("/*__I18N__*/null", i18n.read_text(encoding="utf-8").strip().replace("</", "<\\/"), 1)
    html = html.replace("__TITLE__", payload["title"].replace("<", "&lt;"), 1)
    out = Path(args.output) if args.output else Path(args.score).with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    size = out.stat().st_size / 1024
    print(f"已生成：{out}（{size:.0f} KB）")
    if payload["draft"]:
        print("注意：存在未解决的关键疑点，页面已标为“待校对试听版”。")
    return 0


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_name(m):
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def pitch_check(payload, part, melody):
    """旋律每个音起点处，part 声部正在发声的音里有没有同音名的；返回 (不同音名, 只差八度) 两张清单。"""
    mismatch, octave = [], []
    for n in sorted(payload["bars"], key=int):
        ev = payload["bars"][n]["ev"]
        for m in (e for e in ev if e["part"] == melody and e["t"] == "m"):
            sounding = [e for e in ev if e["part"] == part and e["t"] == "n"
                        and e["o"] <= m["o"] + 1e-9 < e["o"] + e["d"]]
            if not sounding:
                continue
            where = f"第{n}小节 拍位 {Fraction(m['o']).limit_denominator(96)}"
            got = "、".join(f"{e['s']}弦{e['f']}品={midi_name(e['midi'])}" for e in sounding)
            want = f"简谱 {m['lab']}={midi_name(m['midi'])}"
            if not any(e["midi"] % 12 == m["midi"] % 12 for e in sounding):
                mismatch.append(f"{where}：{want}；{part} 为 {got}")
            elif not any(e["midi"] == m["midi"] for e in sounding):
                octave.append(f"{where}：{want}；{part} 为 {got}")
    return mismatch, octave


def melody_leaps(payload, big=10, near=2):
    """按播放顺序找旋律里可疑的大跳：相邻两音（中间没有休止）相差 big 个半音以上，
    而把其中一个音挪一个八度后只差 near 个半音以内，即本来像是级进。
    这种大跳多半是简谱八度点读错（点被三连音记号、连线压住，或扫描不清）。
    两个音都在已确认小节里的不报；两个音都在某条已解决疑点的 leapOk 小节里的不报；同一处反复出现只报一次。"""
    out, seen = [], set()
    ok_sets = [set(q.get("leapOk") or []) for q in payload["issues"] if q.get("status") == "resolved" and q.get("leapOk")]
    for pid in [p["id"] for p in payload["parts"] if p["kind"] == "melody"]:
        prev, base = None, 0.0
        for s in payload["seq"]:
            n, bar = s["bar"], payload["bars"][s["bar"]]
            for m in sorted((e for e in bar["ev"] if e["part"] == pid and e["t"] == "m"), key=lambda e: e["o"]):
                at = base + m["o"]
                if prev and at <= prev["end"] + 1e-6:
                    d = m["midi"] - prev["midi"]
                    key = (pid, prev["n"], prev["o"], n, m["o"])
                    both_ok = (payload["bars"][prev["n"]]["status"] == "confirmed" and bar["status"] == "confirmed") \
                        or any(prev["n"] in k and n in k for k in ok_sets)
                    alt = min(abs(d - 12), abs(d + 12))
                    if abs(d) >= big and alt <= near and not both_ok and key not in seen:
                        seen.add(key)
                        out.append(f"{pid} 第{prev['n']}小节 {prev['lab']} → 第{n}小节 {m['lab']}："
                                   f"{'上' if d > 0 else '下'}跳 {abs(d)} 个半音；其中一个音换八度后只差 {alt} 个半音。"
                                   f"请回原图核对这几个音的八度点")
                prev = {"n": n, "o": m["o"], "lab": m["lab"], "midi": m["midi"], "end": at + m["d"]}
            base += bar["len"]
    return out


def cmd_pitchcheck(args):
    payload, rep = compile_score(load(args.score))
    if payload is None:
        print_report(rep)
        return 1
    ids = {p["id"] for p in payload["parts"]}
    for pid in (args.part, args.melody):
        if pid not in ids:
            print(f"错误：声部 {pid!r} 不存在，现有声部：{'、'.join(sorted(ids))}")
            return 1
    mismatch, octave = pitch_check(payload, args.part, args.melody)
    print(f"音名不一致（需回原图复核）：{len(mismatch)} 处")
    for x in mismatch:
        print("  " + x)
    print(f"音名一致、八度不同（多为记谱习惯，记入假设即可）：{len(octave)} 处")
    for x in octave:
        print("  " + x)
    return 0


def _sips(*a):
    import shutil
    import subprocess
    if not shutil.which("sips"):
        raise ScoreError("找不到 sips（macOS 自带）；其他系统请用看图软件手工裁图")
    r = subprocess.run(["sips", *map(str, a)], capture_output=True, text=True)
    if r.returncode:
        raise ScoreError("sips 处理失败：" + (r.stderr or r.stdout).strip())
    return r.stdout


def image_size(path):
    out = _sips("-g", "pixelWidth", "-g", "pixelHeight", path)
    w = int(re.search(r"pixelWidth: (\d+)", out).group(1))
    h = int(re.search(r"pixelHeight: (\d+)", out).group(1))
    return w, h


def cmd_crop(args):
    W, H = image_size(args.image)
    k = W / (args.ref or W)
    x, y, w, h = (round(v * k) for v in (args.x, args.y, args.w, args.h))
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    if w <= 0 or h <= 0:
        raise ScoreError("裁剪范围在图片之外")
    _sips("-c", h, w, "--cropOffset", y, x, args.image, "--out", args.output)
    _sips("-Z", args.max, args.output)
    print(f"已裁出原图像素 左{x} 上{y} 宽{w} 高{h} → {args.output}")
    return 0


def cmd_shrink(args):
    W, _ = image_size(args.image)
    _sips("-Z", min(args.width, W), args.image, "--out", args.output)
    print(f"已生成 {args.output}（宽 {min(args.width, W)} 像素；img 坐标按此图计算）")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="吉他曲谱工程数据：校验与生成离线播放器")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="校验 score.json")
    c.add_argument("score")
    o = sub.add_parser("order", help="列出展开后的播放顺序")
    o.add_argument("score")
    b = sub.add_parser("build", help="生成 HTML 播放器")
    b.add_argument("score")
    b.add_argument("-i", "--image", action="append", help="原谱图片，可多次指定，按页序")
    b.add_argument("-o", "--output")
    pc = sub.add_parser("pitchcheck", help="吉他旋律声部与简谱逐音互校")
    pc.add_argument("score")
    pc.add_argument("--part", required=True, help="吉他声部 id，如 g2")
    pc.add_argument("--melody", default="vox", help="简谱声部 id，默认 vox")
    cr = sub.add_parser("crop", help="裁剪并放大原谱局部（macOS）")
    cr.add_argument("image")
    for k in ("x", "y", "w", "h"):
        cr.add_argument(k, type=float)
    cr.add_argument("-o", "--output", required=True)
    cr.add_argument("--ref", type=float, help="坐标所依据的图宽（例如看图时显示的宽度）；默认为原图宽")
    cr.add_argument("--max", type=int, default=1900, help="输出长边像素，默认 1900")
    sh = sub.add_parser("shrink", help="缩小原谱供嵌入（macOS）")
    sh.add_argument("image")
    sh.add_argument("-o", "--output", required=True)
    sh.add_argument("--width", type=int, default=4000)
    args = ap.parse_args(argv)
    try:
        return {"check": cmd_check, "order": cmd_order, "build": cmd_build, "pitchcheck": cmd_pitchcheck,
                "crop": cmd_crop, "shrink": cmd_shrink}[args.cmd](args)
    except ScoreError as e:
        print(f"错误：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
