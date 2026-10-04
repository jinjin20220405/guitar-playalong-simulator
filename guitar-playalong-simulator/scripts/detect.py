#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect.py  第 3 步（定位）和第 5 步（标位置）：全部自动。

用法:
    python detect.py --out work/          （先运行过 prepare.py，work/ 里已有 det.png、disp.png、prep.json）

输出 (work/ 下):
    geometry.json   每行谱的范围、小节线、每小节第一个音的位置、简谱行和歌词行的位置
    report.txt      小节编号表、各小节的弦位、主要拨弦型、需要人工核对的地方
    zoom/sN.png     每行谱的放大图，每个小节上方用红字标了小节下标 [n]，读和弦时照着它数
    zoom/pattern.png  主要拨弦型的示例小节（放得很大），用来看符杠、确定每个音的拍位

坐标一律是 det.png 上的像素。检测结果不对时，直接改 geometry.json 里对应行的 bars（小节线 x 坐标列表），
然后运行  python detect.py --out work/ --keep-bars  重新生成其余内容。

依赖: Pillow, numpy
"""
import argparse, json, os, statistics, sys
from collections import Counter
from PIL import Image, ImageDraw
import numpy as np

Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
ap.add_argument('--out', default='work')
ap.add_argument('--keep-bars', action='store_true', help='沿用 geometry.json 里手改过的小节线，只重算其余内容')
A = ap.parse_args()
W_ = A.out
for f in ('det.png', 'prep.json'):
    if not os.path.exists(os.path.join(W_, f)): sys.exit(f'错误: {W_}/{f} 不存在。请先运行 python scripts/prepare.py 曲谱文件 --out {W_}')
prep = json.load(open(os.path.join(W_, 'prep.json')))
im = Image.open(os.path.join(W_, 'det.png')).convert('L'); a = np.array(im); H, W = a.shape
os.makedirs(os.path.join(W_, 'zoom'), exist_ok=True)

# ---------- 1) 六线谱 ----------
def find_staffs(a):
    H, W = a.shape; dark = a < 235; minlen = W * 0.3; gapfill = max(6, int(W * 0.012)); segs = []
    for y in range(H):
        row = dark[y]
        if row.sum() < minlen * 0.5: continue
        idx = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0])))); merged = []
        for s, e in zip(idx[::2], idx[1::2]):
            if merged and s - merged[-1][1] <= gapfill: merged[-1][1] = e
            else: merged.append([s, e])
        for s, e in merged:
            if e - s >= minlen: segs.append((y, int(s), int(e)))
    lines = []
    for y, s, e in segs:
        for L in lines:
            if y - L['y1'] <= 1 and abs(s - L['s']) < W * 0.03 and abs(e - L['e']) < W * 0.03:
                L['y1'] = y; L['s'] = min(L['s'], s); L['e'] = max(L['e'], e); break
        else: lines.append({'y0': y, 'y1': y, 's': s, 'e': e})
    lines = [L for L in lines if L['y1'] - L['y0'] + 1 <= 4]
    groups = []
    for L in sorted(lines, key=lambda L: (L['s'], L['e'])):
        for g in groups:
            if abs(g[0]['s'] - L['s']) <= W * 0.02 and abs(g[0]['e'] - L['e']) <= W * 0.02: g.append(L); break
        else: groups.append([L])
    out = []
    for g in groups:
        g.sort(key=lambda L: L['y0']); i = 0
        while i + 5 < len(g):
            ys = [g[i + k]['y0'] for k in range(6)]; d = np.diff(ys)
            if d.max() - d.min() <= 3 and 5 < d.mean() < 20:
                out.append({'l': min(L['s'] for L in g[i:i + 6]), 'r': max(L['e'] for L in g[i:i + 6]), 't': ys[0], 'b': g[i + 5]['y1'], 'ys': ys}); i += 6
            else: i += 1
    return sorted(out, key=lambda s: s['t'])

staffs = find_staffs(a)
if not staffs: sys.exit('错误: det.png 上没有找到六线谱。请确认 prepare.py 的输出正常。')
sp = statistics.median((s['b'] - s['t']) / 5 for s in staffs)
ink = a < 150; any200 = a < 200
N = len(staffs)

# ---------- 2) 每行谱的上下边界 ----------
def longest_zero_mid(lo, hi, l, r):
    cnt = any200[lo:hi, l:r].sum(1); best = None; s = None
    for i, v in enumerate(list(cnt) + [1]):
        if v == 0 and s is None: s = i
        if v != 0 and s is not None:
            if best is None or i - s > best[1] - best[0]: best = (s, i)
            s = None
    if best: return lo + (best[0] + best[1]) // 2
    return lo + int(np.argmin(cnt))
for i, S in enumerate(staffs):
    if i + 1 < N:
        gap = staffs[i + 1]['t'] - S['b']
        S['y1'] = longest_zero_mid(int(S['b'] + gap * 0.45), int(staffs[i + 1]['t'] - gap * 0.12), 0, W)
    else:
        y = S['b'] + int(2 * sp); blank = 0
        while y < H and blank < 2.5 * sp: blank = blank + 1 if not any200[y].any() else 0; y += 1
        S['y1'] = min(H, y - blank + 3)
    if i == 0:
        y = S['t'] - int(3 * sp); blank = 0
        while y > 0 and blank < 1.2 * sp: blank = blank + 1 if not any200[y].any() else 0; y -= 1
        S['y0'] = max(0, y + blank - 2)
    else: S['y0'] = staffs[i - 1]['y1'] + 1

# ---------- 3) 简谱行、歌词行（只定位置） ----------
def text_bands(S):
    l, r, b = S['l'], S['r'], S['b']; cnt = ink[b + 1:S['y1'], l + 2:r - 1].sum(1); bands = []; s = None
    eps = max(1, int((r - l) * 0.004))          # 扫描件有噪点：一行里只有零星几个墨点也算空行
    for i, v in enumerate(list(cnt) + [0]):
        if v > eps and s is None: s = i
        if v <= eps and s is not None:
            y0, y1 = b + 1 + s, b + 1 + i; xs = np.flatnonzero(ink[y0:y1, l + 2:r - 1].any(0))
            bands.append({'y0': y0, 'y1': y1, 'ext': (xs.max() - xs.min()) / (r - l) if len(xs) else 0, 'touch': s == 0}); s = None
    return bands
for S in staffs:
    bands = [B for B in text_bands(S) if not B['touch']]
    wide = [B for B in bands if B['ext'] >= 0.45 and B['y1'] - B['y0'] >= 0.9 * sp]
    S['jianpu'] = None; S['lyrics'] = []; S['jdig'] = None
    if not wide: continue
    J = wide[0]; rest = wide[1:]
    prof = ink[J['y0']:J['y1'], S['l'] + 2:S['r'] - 1].sum(1); mx = prof.max(); dT = dB = None; y = 0
    while y < len(prof):
        if prof[y] >= mx * 0.12:
            s = y
            while y < len(prof) and prof[y] >= mx * 0.12: y += 1
            if y - s >= 1.0 * sp and dT is None: dT, dB = J['y0'] + s, J['y0'] + y - 1
        else: y += 1
    if dT is None: dT, dB = J['y0'], J['y1'] - 1
    Hd = dB - dT + 1; S['jdig'] = [dT, dB]
    lyr = [[B['y0'], B['y1']] for B in rest]
    # 简谱和第一行歌词之间没有空行时，两者会连成一条横带：数字行下面若还有一段"和数字行一样密"的行，那就是歌词
    dense = np.median(prof[dT - J['y0']:dB - J['y0'] + 1]) * 0.4; run = best = 0
    for v in prof[dB - J['y0'] + 1:]:
        run = run + 1 if v >= dense else 0; best = max(best, run)
    if best >= max(0.9 * sp, 0.6 * Hd):
        lh = (rest[0]['y1'] - rest[0]['y0']) if rest else min(1.15 * Hd, best)
        lyr.insert(0, [int(J['y1'] - lh), J['y1']])
    if lyr: jb = int(lyr[0][0] + (lyr[0][1] - lyr[0][0]) * 0.5)   # 有歌词：简谱识别带的下边切在第一行歌词中间
    else: jb = min(S['y1'], int(J['y1'] + 0.4 * Hd))
    S['jianpu'] = {'y': max(S['b'] + 2, J['y0'] - 1), 'h': jb - max(S['b'] + 2, J['y0'] - 1)}
    S['lyrics'] = [{'y': y0 - 1, 'h': y1 - y0 + 2} for y0, y1 in lyr]

# ---------- 4) 小节线：六线谱上整列为墨色，并且简谱行同一位置也有竖线 ----------
old = None
if A.keep_bars:
    try: old = json.load(open(os.path.join(W_, 'geometry.json')))['systems']
    except Exception: sys.exit('错误: --keep-bars 需要已有的 geometry.json')
def clusters(cols, tol):
    out = []
    for x in cols:
        if out and x - out[-1][-1] <= tol: out[-1].append(x)
        else: out.append([x])
    return [g[len(g) // 2] for g in out]
warn = []
for si, S in enumerate(staffs):
    t, b, l, r = S['t'], S['b'], S['l'], S['r']
    if old: S['bars'] = old[si]['bars']; continue
    cand = clusters([x for x in range(l + 3, r - 2) if (a[t:b + 1, x] < 200).mean() > 0.9], 0.7 * sp)
    jb = []
    if S['jdig']:
        dT, dB = S['jdig']; m = max(2, int(0.18 * (dB - dT)))
        jb = clusters([x for x in range(l + 3, r + 1) if (a[max(0, dT - m):dB + m + 1, x] < 235).mean() > 0.92], 0.7 * sp)
    if len(jb) >= 2:
        inner = [x for x in cand if any(abs(x - q) <= 1.0 * sp for q in jb)]
        for q in jb:                              # 印得很淡的小节线：简谱行有竖线，六线谱同一位置有一条浅色的整列
            if any(abs(x - q) <= 1.0 * sp for x in inner): continue
            xs = [x for x in range(max(l + 3, int(q - sp)), min(r - 2, int(q + sp)) + 1)]
            fr = [(a[t:b + 1, x] < 235).mean() for x in xs]
            if fr and max(fr) >= 0.8: inner.append(xs[int(np.argmax(fr))])
        inner.sort()
    else: inner = [x for x in cand if (a[b + 3:b + 3 + int(0.9 * sp), x] < 200).mean() < 0.3]   # 没有简谱可对照：向下延伸的是符干
    inner = [x for x in inner if x - l > 1.5 * sp and r - x > 1.5 * sp]
    S['bars'] = [l] + inner + [r]
    ws = np.diff(S['bars']); med = np.median(ws[1:]) if len(ws) > 2 else np.median(ws)
    for k, w in enumerate(ws):
        if k > 0 and w < 0.5 * med: warn.append(f'第{si + 1}行第{k + 1}小节很窄（宽 {w}，同行其他小节约 {med:.0f}）。看 zoom/s{si + 1}.png：如果这里其实不是小节线，就从 geometry.json 第{si + 1}行的 bars 里删掉 {S["bars"][k + 1]}')
        if w > (2.3 if k == 0 else 1.4) * med: warn.append(f'第{si + 1}行第{k + 1}小节很宽（宽 {w}，同行其他小节约 {med:.0f}）。看 zoom/s{si + 1}.png：如果这一格里其实是两个小节（谱上漏画了小节线），就在 geometry.json 第{si + 1}行的 bars 里补上 {int((S["bars"][k] + S["bars"][k + 1]) / 2)}')

# ---------- 5) 弦位记号（在高分辨率图上找，谱线粗细不同的谱都适用） ----------
K = prep.get('K', 1.0); dp = os.path.join(W_, 'disp.png')
if K >= 1.2 and os.path.exists(dp): hi = np.array(Image.open(dp).convert('L')); F = K
else: hi = np.array(im.resize((W * 2, H * 2), Image.LANCZOS)); F = 2.0
hink = hi < 140; sph = sp * F
light = np.median([np.median(a[y, S['l']:S['r']]) for S in staffs for y in S['ys']]) > 150   # 谱线是浅灰细线还是黑粗线
marks_all = []
for si, S in enumerate(staffs):
    marks = []
    if light:
        o1, o2 = max(2, round(0.33 * sp)), max(1, round(0.22 * sp))
        for k in range(6):
            y = round(S['t'] + k * (S['b'] - S['t']) / 5)
            rows = [r for r in list(range(y - o1, y)) + list(range(y + o2, y + o1 + 1)) if 0 <= r < H]
            cnt = ink[rows, :].sum(0); x = max(0, S['l'] - 4); xe = min(W, S['r'] + 4)
            while x < xe:
                if cnt[x] > 0:
                    s0 = x
                    while x < xe and cnt[x] > 0: x += 1
                    if x - s0 >= max(3, 0.3 * sp): marks.append(((s0 + x - 1) / 2, k + 1))
                else: x += 1
        marks_all.append(marks); continue
    for k in range(6):
        yc = (S['t'] + k * (S['b'] - S['t']) / 5) * F
        rows = np.flatnonzero((hi[int(yc - 0.2 * sph):int(yc + 0.3 * sph), int(S['l'] * F):int(S['r'] * F)] < 235).mean(1) > 0.5)
        ya = int(yc - 0.2 * sph) + (rows.min() if len(rows) else int(0.2 * sph)); yb = int(yc - 0.2 * sph) + (rows.max() if len(rows) else int(0.2 * sph))
        up = hink[int(ya - 0.36 * sph):max(int(ya - 0.36 * sph) + 1, ya - 1)].sum(0); dn = hink[yb + 2:int(yb + 0.4 * sph) + 1].sum(0)
        any_ = (up > 0) | (dn > 0); x = int(S['l'] * F) - 3; xe = int(S['r'] * F) + 3
        while x < xe:
            if any_[x]:
                s0 = x
                while x < xe and any_[x]: x += 1
                w = x - s0
                if 0.3 * sph <= w <= 1.15 * sph and up[s0:x].sum() >= 0.4 * sph and dn[s0:x].sum() >= 0.4 * sph:
                    m = (s0 + x) // 2
                    if up[s0:m].sum() > 0.08 * sph and up[m:x].sum() > 0.08 * sph and dn[s0:m].sum() > 0.08 * sph and dn[m:x].sum() > 0.08 * sph:
                        marks.append(((s0 + x - 1) / 2 / F, k + 1))
            else: x += 1
    marks_all.append(marks)

measures, rep, sigs = [], [], []
for si, S in enumerate(staffs):
    bars = S['bars']; S['m0'] = len(measures)
    for mi in range(len(bars) - 1):
        l, r = bars[mi], bars[mi + 1]
        ms = sorted((xc - l, k) for xc, k in marks_all[si] if l + 0.3 * sp < xc < r - 0.25 * sp)
        mm = []                                   # 同一根弦上挨得很近的两个记号其实是一个（低分辨率下一个 x 会被认成左右两半）
        for x, k in ms:
            j = next((j for j, (x2, k2) in enumerate(mm) if k2 == k and x - x2 <= 0.8 * sp), None)
            if j is None: mm.append((x, k))
            else: mm[j] = ((mm[j][0] + x) / 2, k)
        ms = sorted(mm)
        if mi == 0: ms = [m for m in ms if m[0] > 3.6 * sp]            # 每行开头的 TAB 字样、拍号
        cl = []
        for x, k in ms:
            if cl and x - cl[-1][0] <= 0.5 * sp: cl[-1][1].append(k)
            else: cl.append([x, [k]])
        dflt = (5.5 if mi == 0 else 1.7) * sp
        first = cl[0][0] if cl and abs(cl[0][0] - dflt) <= 1.5 * sp else dflt
        idx = len(measures)
        measures.append({'s': si, 'l': l, 'r': r, 'first': round(l + first, 1)})
        span = max(1.0, r - l - first)
        seq = [(round((x - first) / span, 2), sorted(set(v))) for x, v in cl]
        sigs.append((idx, tuple('B' if j == 0 and min(v) >= 4 else ','.join(map(str, v)) for j, (f, v) in enumerate(seq)), [f for f, v in seq], [v for f, v in seq]))
        rep.append(f'  [{idx}] 宽{r - l}: ' + ' | '.join(f'{f:.2f}:' + ','.join(map(str, v)) for f, v in seq))
    S['m1'] = len(measures) - 1

# ---------- 6) 主要拨弦型 ----------
cnt = Counter(s[1] for s in sigs if len(s[1]) >= 3)
pat = None
if cnt:
    sig, n = cnt.most_common(1)[0]; same = [s for s in sigs if s[1] == sig]
    frac = [round(float(np.mean([s[2][j] for s in same])), 2) for j in range(len(sig))]
    bass = Counter(s[3][0][-1] for s in same)
    pat = {'strings': list(sig), 'fractions': frac, 'count': n, 'example': same[len(same) // 2][0]}

# ---------- 7) 输出 ----------
geo = {'image': 'det.png', 'staff_spacing': sp, 'crop': [max(0, min(S['l'] for S in staffs) - 8), min(W, max(S['r'] for S in staffs) + 8)],
       'systems': [{'y0': int(S['y0']), 'y1': int(S['y1']), 't': int(S['t']), 'b': int(S['b']), 'bars': [int(x) for x in S['bars']],
                    'jianpu': S['jianpu'], 'lyrics': S['lyrics'], 'first': S['m0'], 'last': S['m1']} for S in staffs],
       'measures': measures, 'pattern': pat,
       'bass_seen': {str(m['i']): m['b'] for m in [{'i': s[0], 'b': s[3][0][-1]} for s in sigs if s[3] and s[3][0][-1] >= 4]}}
json.dump(geo, open(os.path.join(W_, 'geometry.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

src = Image.open(dp).convert('RGB') if os.path.exists(dp) else im.convert('RGB'); Fz = src.width / W; Z = 2.0 / Fz if Fz < 2 else 1.0
for si, S in enumerate(staffs):
    c = src.crop((0, int(S['y0'] * Fz), src.width, int(S['y1'] * Fz)))
    if Z != 1.0: c = c.resize((int(c.width * Z), int(c.height * Z)), Image.LANCZOS)
    f = Fz * Z; top = 26; canvas = Image.new('RGB', (c.width, c.height + top), 'white'); canvas.paste(c, (0, top)); d = ImageDraw.Draw(canvas)
    for mi in range(len(S['bars']) - 1):
        x = S['bars'][mi] * f; d.line((x, 2, x, top - 2), fill=(200, 0, 0), width=3)
        lab = Image.new('RGB', (44, 12), 'white'); ImageDraw.Draw(lab).text((1, 0), f'[{S["m0"] + mi}]', fill=(200, 0, 0))   # 默认字体太小，放大 2 倍贴上去
        canvas.paste(lab.resize((88, 24), Image.NEAREST), (int(x) + 6, 1))
    canvas.save(os.path.join(W_, 'zoom', f's{si + 1}.png'))
if pat:
    m = measures[pat['example']]; S = staffs[m['s']]; z = 4.0 / Fz
    c = src.crop((int((m['l'] - 4) * Fz), int((S['t'] - 2.5 * sp) * Fz), int((m['r'] + 4) * Fz), int((S['b'] + 3.2 * sp) * Fz)))
    c.resize((int(c.width * z), int(c.height * z)), Image.LANCZOS).save(os.path.join(W_, 'zoom', 'pattern.png'))

out = ['===== 小节编号表（song.txt 的 chords 每行要写的和弦个数 = 该行小节数）=====']
for si, S in enumerate(staffs): out.append(f'第{si + 1}行: 小节 [{S["m0"]}]–[{S["m1"]}]，共 {S["m1"] - S["m0"] + 1} 个；简谱行{"有" if S["jianpu"] else "无"}，歌词 {len(S["lyrics"])} 行')
out.append(f'合计 {len(measures)} 个小节，{N} 行谱。')
out.append(''); out.append('===== 需要人工核对 =====')
out += warn or ['（无）']
out.append(''); out.append('===== 主要拨弦型 =====')
if pat:
    out.append(f'出现 {pat["count"]} 次（共 {len(measures)} 小节），示例见 zoom/pattern.png（小节 [{pat["example"]}]）')
    out.append('弦序: ' + ' '.join(pat['strings']) + '    （B = 低音弦，数字 = 第几弦，1 是最细的弦）')
    out.append('各音在小节内的位置比例: ' + ' '.join(f'{f:.2f}' for f in pat['fractions']))
else: out.append('没有归纳出重复的拨弦型，请看各小节明细。')
out.append(''); out.append('===== 各小节弦位明细（位置比例:弦号）=====')
for si, S in enumerate(staffs):
    out.append(f'第{si + 1}行'); out += rep[S['m0']:S['m1'] + 1]
open(os.path.join(W_, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
# song.txt 模板：只在不存在时生成，已经填过的不覆盖
tp = os.path.join(W_, 'song.txt')
def unfilled(path):                  # 还没填过和弦的模板可以放心重新生成（比如补了小节线之后小节数变了）
    import re as _re
    return not any(_re.match(r'^\d+\s*\([^)]*\):\s*\S', ln) for ln in open(path, encoding='utf-8'))
if not os.path.exists(tp) or unfilled(tp):
    L = ['# 第 4 步：填写本文件。# 开头的是说明，不用删。冒号用英文半角。',
         'title: ', 'credits: ', 'bpm: ', 'beats: 4', 'key: C', 'pickup_rest: 0', 'capo: 0', '',
         '# 拨弦型：一小节里每个音的"拍位:弦"。B=低音弦，数字=第几弦（1 最细），同时拨两根写 1,3',
         '# report.txt 的"主要拨弦型"给出了弦序和位置比例；看 zoom/pattern.png 的符杠确定拍位（见 SKILL.md）',
         'pattern: ', '',
         '# 和弦：每行谱一行，照 zoom/sN.png 从左到右抄和弦名，用空格分开，个数必须等于该行小节数。',
         '# 一小节两个和弦写 F/E；这一小节上方没标和弦（沿用前一个）写 -',
         'chords:']
    for si, S in enumerate(staffs): L.append(f'{si + 1} ({S["m1"] - S["m0"] + 1}个小节 [{S["m0"]}]-[{S["m1"]}]): ')
    L += ['', '# 段落（用于循环按钮）：名称: 起-止（小节下标）。常用名称：前奏 主歌 副歌 间奏 结尾副歌 尾奏 桥段', 'sections:', '',
          '# 演奏顺序：没有反复就写 0-最后一个下标；有反复写成 0-8, 9-23, 24-32, 9-23, 33-60 这样的分段',
          f'sequence: 0-{len(measures) - 1}', '',
          '# 个别小节和主要拨弦型不同时单独写：小节下标: 写法同 pattern；整小节一个琶音和弦写 roll；不弹写 rest',
          'overrides:', '',
          '# 用到的和弦不在内置表里时补充指型（6 弦到 1 弦的品位，x=不弹），例如  shape Bm7: x24232', '']
    open(tp, 'w', encoding='utf-8').write('\n'.join(L))
else: print(f'注意: {tp} 已经填过，没有覆盖。如果小节数变了，请对照上面的小节编号表修改 chords 各行的个数。')
print('\n'.join(out[:len(staffs) + 2 + 2 + len(warn or [1]) + 6]))
print(f'\n第 3、5 步完成。请查看 {W_}/report.txt 和 {W_}/zoom/。下一步: 填写 {W_}/song.txt（见 SKILL.md 第 4 步）')
