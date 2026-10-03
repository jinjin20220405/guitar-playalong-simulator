#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect.py  从一张"六线谱 + 简谱"的吉他谱图片中检测版面几何，并输出转录辅助材料。

用法:
    python detect.py 谱.png --out work/

输出 (work/ 下):
    geometry.json   每行谱(system)的裁切范围、每小节的左右小节线、首个八分位 x 坐标与八分位间距
    report.txt      每小节每个拍位上、哪几根弦有记号（x 或数字），供转录时对照
    zoom/sN.png     每行谱 2 倍放大图
    zoom/sNa.png、sNb.png   六线谱+简谱 左、右半行 4 倍放大图

依赖: Pillow, numpy
检测不准时: 调参数重跑，或直接手改 geometry.json（坐标均为原图像素）。
"""
import argparse, json, os, statistics
from PIL import Image
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('image')
ap.add_argument('--out', default='work')
ap.add_argument('--line-thr', type=int, default=235, help='谱线像素阈值(谱线常为浅灰)')
ap.add_argument('--ink-thr', type=int, default=150, help='记号/符干像素阈值')
ap.add_argument('--gap', type=int, default=12, help='判定为行间空白的最小连续空行数')
ap.add_argument('--clef', type=int, default=42, help='每行首小节左侧要忽略的宽度(TAB 字样、拍号、小节号)')
ap.add_argument('--slot-min', type=float, default=10, help='相邻八分位最小间距(px)')
ap.add_argument('--slot-max', type=float, default=17, help='相邻八分位最大间距(px)')
A = ap.parse_args()

os.makedirs(os.path.join(A.out, 'zoom'), exist_ok=True)
im = Image.open(A.image).convert('RGB')
a = np.array(im.convert('L')); H, W = a.shape

# 1) 谱线：找"很长的横线"所在行，合并成线，再每 6 条等距线归为一个六线谱
long_rows = [y for y in range(H) if (a[y] < A.line_thr).mean() > 0.55]
groups = []
for y in long_rows:
    if groups and y - groups[-1][-1] <= 1: groups[-1].append(y)
    else: groups.append([y])
lines = [g[0] for g in groups]
staffs, i = [], 0
while i + 5 < len(lines):
    seg = lines[i:i + 6]; d = [seg[k + 1] - seg[k] for k in range(5)]
    if max(d) - min(d) <= 3 and max(d) < 25:
        staffs.append((seg[0], seg[5])); i += 6
    else: i += 1
if not staffs: raise SystemExit('没有检测到六线谱，请调 --line-thr')

# 2) 行间空白带 -> 每行谱的上下边界
blank = (a < 200).sum(1) == 0
bands, s = [], None
for y in range(H + 1):
    b = y < H and not blank[y]
    if b and s is None: s = y
    if not b and s is not None:
        bands.append([s, y]); s = None
merged = []
for b in bands:
    if merged and b[0] - merged[-1][1] < A.gap: merged[-1][1] = b[1]
    else: merged.append(list(b))
def band_of(y):
    for b in merged:
        if b[0] <= y <= b[1]: return b
    return [y - 60, y + 120]
tops = [band_of(t)[0] for t, _ in staffs]
systems = []
for k, (t, b) in enumerate(staffs):
    y0 = tops[k]
    limit = tops[k + 1] if k + 1 < len(staffs) else H
    y1 = max([bb[1] for bb in merged if bb[0] >= y0 and bb[1] <= limit] or [b + 80])
    systems.append({'y0': max(0, y0 - 3), 'y1': min(H, y1 + 3), 't': t, 'b': b})

# 3) 小节线：在谱线范围内整列为墨色、且不向下延伸（向下延伸的是符干）
ink = a < A.ink_thr
measures, report = [], []
for si, S in enumerate(systems):
    t, b = S['t'], S['b']
    xs_line = np.where(a[t] < A.line_thr)[0]
    left, right = int(xs_line[0]), int(xs_line[-1])
    cols = [x for x in range(left + 4, right + 1)
            if (a[t:b + 1, x] < 200).mean() > 0.9 and (a[b + 3:b + 11, x] < 200).mean() < 0.3]
    bars = []
    for x in cols:
        if bars and x - bars[-1][-1] <= 6: bars[-1].append(x)
        else: bars.append([x])
    bars = [left] + [g[0] for g in bars]
    if right - bars[-1] > 20: bars.append(right)
    S['bars'] = bars
    # 谱线下方的文字横带（简谱行、歌词行），只给位置，供填写 lyricRows 时参考
    cnt_rows = (a[b + 18:S['y1'], left + 2:right - 1] < A.ink_thr).sum(1)
    tb, s0 = [], None
    for i2, v in enumerate(list(cnt_rows) + [0]):
        if v > 0 and s0 is None: s0 = i2
        if v == 0 and s0 is not None: tb.append([b + 18 + s0, b + 18 + i2]); s0 = None
    S['textBands'] = tb
    # 4) 记号：每根弦线附近（去掉线本身）的成团墨迹
    ys = [round(t + k * (b - t) / 5) for k in range(6)]
    marks = []
    for k, y in enumerate(ys):
        rows = [y - 3, y - 2, y - 1, y + 2, y + 3]
        cnt = ink[rows, :].sum(0)
        x = max(0, left - 6); xe = min(W, right + 6)
        while x < xe:
            if cnt[x] > 0:
                s0 = x
                while x < xe and cnt[x] > 0: x += 1
                if x - s0 >= 3:
                    tall = bool(ink[y - 4, s0:x].any() or ink[y + 4, s0:x].any())
                    marks.append(((s0 + x - 1) / 2, k + 1, tall))
            else: x += 1
    for mi in range(len(bars) - 1):
        l, r = bars[mi], bars[mi + 1]
        ms = sorted((xc - l, k, tall) for xc, k, tall in marks if l + 3 < xc < r - 2)
        ms = [m for m in ms if m[0] >= 12 and not (mi == 0 and m[0] <= A.clef)]
        cl = []
        for x, k, tall in ms:
            if cl and x - cl[-1][0] <= 5: cl[-1][1].append((k, tall))
            else: cl.append([x, [(k, tall)]])
        df = [q for q in (cl[j + 1][0] - cl[j][0] for j in range(len(cl) - 1)) if A.slot_min <= q <= A.slot_max]
        d = statistics.median(df) if df else 13.5
        x1 = cl[0][0] if cl else 16
        idx = len(measures)
        measures.append({'s': si, 'l': l, 'r': r, 'x1': round(l + x1, 1), 'd': round(d, 2)})
        slots = ' | '.join(f"{round(x)}:" + ','.join(str(k) + ('?' if tall and k <= 3 else '') for k, tall in sorted(v)) for x, v in cl)
        flag = '' if len(cl) == 8 else f'   <-- 拍位数 {len(cl)}≠8，需对照放大图人工核对'
        report.append(f'[{idx}] 第{si + 1}行第{mi + 1}小节 宽{r - l}: {slots}{flag}')
    # 放大图
    c = im.crop((0, S['y0'], W, S['y1'])); c.resize((c.width * 2, c.height * 2), Image.LANCZOS).save(f'{A.out}/zoom/s{si + 1}.png')
    mid = (left + right) // 2
    for tag, (xa, xb) in (('a', (max(0, left - 8), mid + 12)), ('b', (mid - 12, min(W, right + 8)))):
        c = im.crop((xa, t - 14, xb, S['y1'])); c.resize((c.width * 4, c.height * 4), Image.LANCZOS).save(f'{A.out}/zoom/s{si + 1}{tag}.png')

X0 = max(0, min(S['bars'][0] for S in systems) - 8); X1 = min(W, max(S['bars'][-1] for S in systems) + 8)
geo = {'image': os.path.basename(A.image), 'crop': [X0, X1],
       'systems': [{'y0': S['y0'], 'y1': S['y1'], 't': S['t'], 'b': S['b'], 'bars': S['bars'], 'textBands': S['textBands']} for S in systems],
       'measures': measures}
json.dump(geo, open(f'{A.out}/geometry.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
head = ['说明: 每小节一行；"x偏移:弦号,弦号" 表示该拍位上有记号的弦(1=最细弦)。',
        '带 ? 的是疑似数字(品位)，其余多为 x(按和弦指型)。数字是几、4-6 弦上是不是数字，一律以放大图为准。',
        '序号 [n] 即 geometry.json 中 measures 的下标，也是 song.json 中 measures 的下标。', '']
open(f'{A.out}/report.txt', 'w', encoding='utf-8').write('\n'.join(head + report) + '\n')
print(f'检测到 {len(systems)} 行谱、{len(measures)} 个小节。输出在 {A.out}/')
for S in systems: print('  行', S['y0'], S['y1'], '谱线', S['t'], S['b'], '小节线', S['bars'], '谱线下文字横带', S['textBands'])
