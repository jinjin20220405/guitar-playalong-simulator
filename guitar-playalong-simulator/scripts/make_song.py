#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_song.py  第 4 步的后半：把填好的 work/song.txt 变成 work/song.json。

用法:
    python make_song.py --out work/

有填错的地方会逐条用中文指出（哪一行、应该是几个、写了几个），改完重跑即可。
"""
import argparse, json, os, re, sys

ap = argparse.ArgumentParser(); ap.add_argument('--out', default='work'); A = ap.parse_args()
W_ = A.out
for f in ('geometry.json', 'song.txt'):
    if not os.path.exists(os.path.join(W_, f)): sys.exit(f'错误: {W_}/{f} 不存在。请先运行 detect.py。')
geo = json.load(open(os.path.join(W_, 'geometry.json'), encoding='utf-8'))
NM = len(geo['measures'])

SHAPES = {  # 6 弦 -> 1 弦
 'C': 'x32010', 'C7': 'x32310', 'Cmaj7': 'x32000', 'Cadd9': 'x32030', 'D': 'xx0232', 'Dm': 'xx0231', 'D7': 'xx0212', 'Dm7': 'xx0211', 'Dsus4': 'xx0233',
 'E': '022100', 'Em': '022000', 'E7': '020100', 'Em7': '022030', 'F': '133211', 'Fmaj7': 'xx3210', 'Fm': '133111', 'F#m': '244222',
 'G': '320003', 'G7': '320001', 'Gsus4': '330013', 'A': 'x02220', 'Am': 'x02210', 'A7': 'x02020', 'Am7': 'x02010', 'Asus4': 'x02230',
 'B': 'x24442', 'Bm': 'x24432', 'B7': 'x21202', 'Bm7': 'x24232', 'Bb': 'x13331', 'Bdim': 'x2343x'}
ALIAS = {'Dm': 'Dm', 'Em7': 'Em7'}
errs = []; cfg = {}; chords_rows = {}; sections = []; overrides = {}; mode = None
for ln, raw in enumerate(open(os.path.join(W_, 'song.txt'), encoding='utf-8'), 1):
    line = raw.split('#')[0].rstrip() if not raw.lstrip().startswith('shape') else raw.rstrip()
    line = line.replace('：', ':').strip()
    if not line: continue
    m = re.match(r'^shape\s+(\S+)\s*:\s*([x0-9]{6})$', line)
    if m: SHAPES[m.group(1)] = m.group(2); continue
    if line in ('chords:', 'sections:', 'overrides:'): mode = line[:-1]; continue
    m = re.match(r'^(title|credits|bpm|beats|key|pickup_rest|capo|pattern|sequence)\s*:\s*(.*)$', line)
    if m: cfg[m.group(1)] = m.group(2).strip(); mode = None; continue
    if mode == 'chords':
        m = re.match(r'^(\d+)\s*(\([^)]*\))?\s*:\s*(.*)$', line)
        if m: chords_rows[int(m.group(1))] = m.group(3).split(); continue
    if mode == 'sections':
        m = re.match(r'^(.+?)\s*:\s*(\d+)\s*-\s*(\d+)$', line)
        if m: sections.append([m.group(1).strip(), [int(m.group(2)), int(m.group(3))]]); continue
    if mode == 'overrides':
        m = re.match(r'^(\d+)\s*:\s*(.+)$', line)
        if m: overrides[int(m.group(1))] = m.group(2).strip(); continue
    errs.append(f'song.txt 第 {ln} 行看不懂: {raw.strip()}')

def num(k, d=None, f=float):
    v = cfg.get(k, '')
    if v == '':
        if d is None: errs.append(f'{k} 没有填'); return 0
        return d
    try: return f(v)
    except Exception: errs.append(f'{k} 应该是数字，现在是 "{v}"'); return d or 0
title = cfg.get('title', '')
if not title: errs.append('title（曲名）没有填')
bpm = num('bpm'); beats = num('beats', 4); pick = num('pickup_rest', 0); capo = int(num('capo', 0))
km = re.match(r'^([A-G])([#b]?)$', cfg.get('key', 'C'))
if not km: errs.append('key 写成 C、D、Eb、F# 这样的调名'); tonic = 60
else:
    tonic = {'C': 60, 'D': 62, 'E': 64, 'F': 65, 'G': 55, 'A': 57, 'B': 59}[km.group(1)] + {'#': 1, 'b': -1, '': 0}[km.group(2)]

def parse_pat(s, where):
    out = []
    for tok in s.split():
        m = re.match(r'^(\d*\.?\d+):(B|[1-6](=\d+)?)(,(B|[1-6](=\d+)?))*$', tok)
        if not m: errs.append(f'{where} 里的 "{tok}" 写法不对，应为 拍位:弦，例如 0:B 或 1.5:2 或 1:1,3'); continue
        tm = float(tok.split(':')[0])
        if not (0 <= tm < beats): errs.append(f'{where} 里的拍位 {tm:g} 超出一小节（0 到 {beats:g}）'); continue
        out.append((tm, tok.split(':')[1]))
    return out
pattern = parse_pat(cfg.get('pattern', ''), 'pattern')
if not cfg.get('pattern'):
    pt = geo.get('pattern')
    if pt:   # 按检测到的位置比例给出建议：比例 × 每小节拍数，取最接近的 0.25 拍
        sug = ' '.join(f"{round(f * beats * 4) / 4:g}:{s}" for f, s in zip(pt['fractions'], pt['strings']))
        errs.append(f'pattern（拨弦型）没有填。按检测结果推算的建议是:  pattern: {sug}   请对照 zoom/pattern.png 的符杠确认后填入')
    else: errs.append('pattern（拨弦型）没有填，检测也没有归纳出重复的型。请看 zoom 里的放大图自行填写')

# 和弦逐小节展开
chords = [None] * NM
for si, S in enumerate(geo['systems']):
    need = S['last'] - S['first'] + 1; got = chords_rows.get(si + 1)
    if got is None: errs.append(f'chords 缺第 {si + 1} 行（需要 {need} 个和弦）'); continue
    if len(got) != need: errs.append(f'chords 第 {si + 1} 行需要 {need} 个和弦（小节 [{S["first"]}]-[{S["last"]}]），你写了 {len(got)} 个：{" ".join(got)}'); continue
    for k, c in enumerate(got): chords[S['first'] + k] = c
prev = None
for i in range(NM):
    if chords[i] in ('-', '.', None): chords[i] = prev
    else: prev = chords[i]
first_real = next((c for c in chords if c), None)
chords = [c or first_real for c in chords]
def bass_of(name):
    sh = SHAPES[name]
    return str(6 - next(i for i, ch in enumerate(sh) if ch != 'x'))
seen = geo.get('bass_seen', {})
M = []
for i in range(NM):
    if not chords[i]: continue
    parts = chords[i].split('/')
    for c in parts:
        if c not in SHAPES: errs.append(f'小节 [{i}] 的和弦 {c} 不在内置表里。请在 song.txt 末尾加一行，例如:  shape {c}: x32010（6 弦到 1 弦的品位，x=不弹）')
    if any(c not in SHAPES for c in parts): continue
    ch = [[parts[0], 0]] + ([[parts[1], beats / 2]] if len(parts) > 1 else [])
    ov = overrides.get(i)
    if ov == 'rest': toks = []
    elif ov == 'roll': toks = None
    elif ov: toks = parse_pat(ov, f'overrides 小节 [{i}]')
    else: toks = [t for t in pattern if not (i == 0 and pick and t[0] < pick)]
    m = {'n': i, 'ch': ch, 'acc': [''] * int(beats * 2), 'mel': f'0:{beats:g}'}
    if toks is None:
        lo = int(bass_of(parts[0])); m['acc'] = []; m['x'] = [[round(0.07 * k, 2), str(s)] for k, s in enumerate(range(lo, 0, -1))]
    else:
        xs = []
        for tm, spec in toks:
            cur = parts[1] if len(parts) > 1 and tm >= beats / 2 else parts[0]
            b = str(seen.get(str(i))) if (str(i) in seen and tm == 0 and SHAPES[cur][6 - int(seen[str(i)])] != 'x') else bass_of(cur)
            spec = ','.join(b if p == 'B' else p for p in spec.split(','))
            if abs(tm * 2 - round(tm * 2)) < 1e-6 and not m['acc'][int(round(tm * 2))]: m['acc'][int(round(tm * 2))] = spec
            else: xs.append([tm, spec])
        if xs: m['x'] = xs
    M.append(m)

seq = []
for part in cfg.get('sequence', f'0-{NM - 1}').split(','):
    m = re.match(r'^\s*(\d+)\s*-\s*(\d+)\s*$', part)
    if not m or not (0 <= int(m.group(1)) <= int(m.group(2)) < NM): errs.append(f'sequence 里的 "{part.strip()}" 不对，应为 起-止，且不超过最后一个下标 {NM - 1}'); continue
    seq.append([int(m.group(1)), int(m.group(2))])
for name, (a, b) in sections:
    if not (0 <= a <= b < NM): errs.append(f'sections "{name}" 的范围 {a}-{b} 超出小节下标 0-{NM - 1}')
if errs:
    print('song.txt 有以下问题，改完后重新运行本脚本：'); [print('  -', e) for e in errs]; sys.exit(1)

used = sorted({c for m in M for c, _ in m['ch']})
song = {'title': title, 'credits': [c.strip() for c in cfg.get('credits', '').split('|') if c.strip()], 'bpm': bpm, 'beats': beats, 'tonicMidi': tonic,
        'pickupRest': pick, 'numberOffset': 0 if pick else 1, 'capo': capo, 'tuning': {'1': 64, '2': 59, '3': 55, '4': 50, '5': 45, '6': 40},
        'shapes': {c: {str(6 - i): (0 if ch == 'x' else int(ch)) for i, ch in enumerate(SHAPES[c])} for c in used},
        'jianpuRows': [{'s': si, **S['jianpu']} for si, S in enumerate(geo['systems']) if S.get('jianpu')],
        'lyricRows': [{'s': si, **L} for si, S in enumerate(geo['systems']) for L in S.get('lyrics', [])],
        'sequence': seq, 'sections': sections, 'measures': M}
json.dump(song, open(os.path.join(W_, 'song.json'), 'w', encoding='utf-8'), ensure_ascii=False)
print(f'已生成 {W_}/song.json：{NM} 小节，和弦 {len(used)} 种（{" ".join(used)}），段落 {len(sections)} 个。')
print('第 4 步完成。下一步: python scripts/build.py --out', W_, '--html 曲名跟弹模拟器.html')
