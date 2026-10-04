#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build.py  把 谱面图片 + geometry.json + song.json 合成一个自包含的跟弹模拟器 HTML。

用法:
    python build.py --out work/ --html 曲名跟弹模拟器.html

会先做数据校验：有"错误"则不生成；"提示"不阻断，但要逐条确认是不是有意为之。
依赖: Pillow
"""
import argparse, base64, io, json, os, re, sys
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('--out', default='work', help='工作目录（里面有 disp.png、geometry.json、song.json、prep.json）')
ap.add_argument('--html', required=True, help='生成的网页文件名')
ap.add_argument('--image'); ap.add_argument('--geometry'); ap.add_argument('--song')
ap.add_argument('--template', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'template.html'))
ap.add_argument('--colors', type=int, default=32, help='谱面图片量化颜色数(越小文件越小)')
A = ap.parse_args()
A.geometry = A.geometry or os.path.join(A.out, 'geometry.json'); A.song = A.song or os.path.join(A.out, 'song.json')
for f in (A.geometry, A.song):
    if not os.path.exists(f): sys.exit(f'错误: {f} 不存在。请按顺序先运行 prepare.py、detect.py、make_song.py。')
geo = json.load(open(A.geometry, encoding='utf-8'))
song = json.load(open(A.song, encoding='utf-8'))
K = 1.0                                   # 坐标是 det.png 上的；显示用 disp.png，两者相差 K 倍
pj = os.path.join(A.out, 'prep.json')
if os.path.exists(pj): K = json.load(open(pj)).get('K', 1.0)
if not A.image:
    A.image = os.path.join(A.out, 'disp.png' if os.path.exists(os.path.join(A.out, 'disp.png')) else 'det.png')
    if A.image.endswith('det.png'): K = 1.0
im = Image.open(A.image).convert('RGB')
beats0 = song.get('beats', 4); pk0 = song.get('pickupRest', 0)
for i, g in enumerate(geo['measures']):   # 由"第一个音的位置"算出光标起点和步长
    if 'x1' not in g:
        first = g.get('first', g['l'] + 16); nb = beats0 - (pk0 if i == 0 else 0)
        g['d'] = (g['r'] - first) / max(1, nb * 2); g['x1'] = first - (pk0 * 2 * g['d'] if i == 0 else 0); g['_pk'] = True
def sc(v): return v * K
for s in geo['systems']:
    for k in ('y0', 'y1', 't', 'b'): s[k] = int(round(sc(s[k])))
for g in geo['measures']:
    for k in ('l', 'r', 'x1', 'd'): g[k] = sc(g[k])
geo['crop'] = [int(sc(geo['crop'][0])), min(im.width, int(sc(geo['crop'][1])))]
for key in ('labels', 'lyricRows', 'jianpuRows'):
    for R in song.get(key, []):
        for k in ('x', 'y', 'w', 'h'):
            if k in R: R[k] = int(round(sc(R[k])))

# ---------- 校验 ----------
errs, warns = [], []
M = song.get('measures', []); G = geo['measures']; beats = song.get('beats', 4)
if len(M) != len(G):
    errs.append(f'song.json 有 {len(M)} 个小节，geometry.json 有 {len(G)} 个，必须一致（都从 0 起按谱面顺序排）')
shapes = song.get('shapes', {})
tok = re.compile(r"^[#b]?[0-7][,']*:\d*\.?\d+$")
spec = re.compile(r'^[1-6](=\d+)?(,[1-6](=\d+)?)*$')
for i, m in enumerate(M):
    if not m.get('ch'): errs.append(f'小节[{i}] 缺和弦 ch'); continue
    for name, _ in m['ch']:
        if name not in shapes: errs.append(f'小节[{i}] 和弦 {name} 不在 shapes 里')
    acc = m.get('acc', [])
    if len(acc) > beats * 2: errs.append(f'小节[{i}] acc 有 {len(acc)} 个八分位，超过 {beats * 2}')
    for sp in list(acc) + [e[1] for e in m.get('x', [])]:
        if sp and not spec.match(sp): errs.append(f'小节[{i}] 伴奏写法不合法: "{sp}"')
    for e in m.get('x', []):
        if not (0 <= e[0] < beats): errs.append(f'小节[{i}] x 里的拍位 {e[0]} 超出小节')
    total = 0
    for t in m.get('mel', '').split():
        if not tok.match(t): errs.append(f'小节[{i}] 旋律写法不合法: "{t}"'); continue
        total += float(t.split(':')[1])
    if abs(total - beats) > 1e-6:
        (warns if total > beats else errs).append(
            f'小节[{i}] 旋律时值合计 {total:g} 拍（应为 {beats:g}）' + ('，若是跨小节连音可忽略' if total > beats else '，少了'))
for a, b in song.get('sequence', []):
    if not (0 <= a <= b < len(M)): errs.append(f'sequence 段 [{a},{b}] 越界')
for name, (a, b) in song.get('sections', []):
    if not (0 <= a <= b < len(M)): errs.append(f'sections "{name}" [{a},{b}] 越界')
for i, L in enumerate(song.get('labels', [])):
    if not (0 <= L.get('s', -1) < len(geo['systems'])) or not all(k in L for k in ('x', 'y', 'w', 'h', 'text')):
        errs.append(f'labels[{i}] 需要 s(行号)、x、y、w、h、text，且 s 在行数范围内')
for i, R in enumerate(song.get('lyricRows', [])):
    if not (0 <= R.get('s', -1) < len(geo['systems'])) or not all(k in R for k in ('y', 'h')):
        errs.append(f'lyricRows[{i}] 需要 s(行号)、y、h，且 s 在行数范围内')
for i, P in enumerate(song.get('lyricPhrases', [])):
    if not isinstance(P.get('r'), int) or not P.get('m') or not all(isinstance(x, int) and 0 <= x < len(M) for x in P['m']):
        errs.append(f'lyricPhrases[{i}] 需要 r(该行谱里第几行歌词，从0起) 和 m(小节下标列表)')
    for k in P.get('blank', []):
        if not re.match(r'^\d+\.\d+$', str(k)): errs.append(f'lyricPhrases[{i}] 的 blank 应写成 "小节下标.歌词行号"，如 "8.0"')
for i, R in enumerate(song.get('jianpuRows', [])):
    if not (0 <= R.get('s', -1) < len(geo['systems'])) or not all(k in R for k in ('y', 'h')):
        errs.append(f'jianpuRows[{i}] 需要 s(行号)、y、h，且 s 在行数范围内')
for w in warns: print('提示:', w)
if errs:
    for e in errs: print('错误:', e)
    sys.exit(1)

# ---------- 切谱面条 ----------
X0, X1 = geo['crop']
SYS = []
for s in geo['systems']:
    c = im.crop((X0, s['y0'], X1, s['y1']))
    q = c.quantize(A.colors, method=Image.MEDIANCUT, dither=Image.NONE)
    buf = io.BytesIO(); q.save(buf, 'PNG', optimize=True)
    SYS.append({'h': c.height, 'top': max(0, s['t'] - 10 - s['y0']),
                'src': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()})
MEAS = [{'s': g['s'], 'l': round(g['l'] - X0, 1), 'r': round(g['r'] - X0, 1), 'x1': round(g['x1'] - X0, 1), 'd': round(g['d'], 2)} for g in G]
for m in M: m.pop('n', None)
# 起拍小节：检测到的首个记号其实在休止之后，把起点往左推回去，光标才对得上
pk = song.get('pickupRest', 0)
if pk and MEAS and not G[0].get('_pk'): MEAS[0]['x1'] = round(MEAS[0]['x1'] - pk * 2 * MEAS[0]['d'], 1)

# 谱面文字标签：原图坐标 -> 所在谱面条内的坐标
for L in song.get('labels', []):
    L['x'] -= X0; L['y'] -= geo['systems'][L['s']]['y0']
# 歌词行：只记位置，供用户在页面上自填译文
for R in song.get('lyricRows', []):
    R['y'] -= geo['systems'][R['s']]['y0']
# 简谱行：只记位置，页面打开时由浏览器自己读谱识别旋律
for R in song.get('jianpuRows', []):
    s = geo['systems'][R['s']]
    R['h'] = min(R['h'], s['y1'] - R['y']); R['y'] -= s['y0']

t = open(A.template, encoding='utf-8').read()
for key, val in (('/*SYS*/', json.dumps(SYS)), ('/*MEAS*/', json.dumps(MEAS)), ('/*CW*/', str(X1 - X0)),
                 ('/*SONG*/', json.dumps(song, ensure_ascii=False).replace('</', '<\\/'))):
    assert t.count(key) == 1, key
    t = t.replace(key, val)
open(A.html, 'w', encoding='utf-8').write(t)
print(f'已生成 {A.html}（{len(t) // 1024} KB，{len(SYS)} 行谱，{len(M)} 小节）')
print('第 6 步完成。下一步: python scripts/check.py', A.html)
