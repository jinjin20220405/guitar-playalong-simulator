#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare.py  第 1、2 步：把使用者给的曲谱（图片或 PDF，可多页、可多栏）整理成标准输入。

用法:
    python prepare.py 谱.png --out work/
    python prepare.py 谱.pdf --out work/
    python prepare.py 第1页.png 第2页.png --out work/

它做的事（全部自动，不改动谱面内容，只改排列和尺寸）:
    1. PDF 逐页渲染成图片（需要系统里有 pdftoppm，或装了 PyMuPDF）
    2. 在每页上找出所有六线谱，按左右位置分栏
    3. 按阅读顺序（先页、再栏从左到右）把各栏上下拼成一张单栏长图
    4. 统一缩放：det.png 供检测用（谱线间距约 9 像素），disp.png 供显示和页面识谱用（尽量 2 倍于 det）

输出 (work/ 下):
    det.png, disp.png, prep.json（记录缩放比例，后面的脚本会自动读取）

依赖: Pillow, numpy
"""
import argparse, json, os, subprocess, sys, glob, tempfile
from PIL import Image
import numpy as np

Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
ap.add_argument('inputs', nargs='+')
ap.add_argument('--out', default='work')
ap.add_argument('--dpi', type=int, default=0, help='PDF 渲染分辨率；不填则按 PDF 内嵌图片的分辨率自动选（最低 300）')
A = ap.parse_args()
os.makedirs(A.out, exist_ok=True)

def load_pages(path):
    if path.lower().endswith('.pdf'):
        tmp = tempfile.mkdtemp(); dpi = A.dpi
        if not dpi:                              # 扫描版 PDF：按内嵌图片的实际分辨率渲染，低了会丢细节
            dpi = 300
            try:
                rows = subprocess.run(['pdfimages', '-list', path], capture_output=True, text=True).stdout.splitlines()[2:]
                ppi = [int(float(r.split()[12])) for r in rows if len(r.split()) > 13 and r.split()[2] == 'image']
                if ppi: dpi = max(300, min(600, max(ppi)))
            except Exception: pass
        A.dpi = dpi
        try:
            subprocess.run(['pdftoppm', '-r', str(A.dpi), '-png', path, os.path.join(tmp, 'p')], check=True)
            files = sorted(glob.glob(os.path.join(tmp, 'p*.png')))
            return [Image.open(f).convert('L') for f in files]
        except Exception:
            try:
                import fitz
                doc = fitz.open(path); out = []
                for pg in doc:
                    pm = pg.get_pixmap(dpi=A.dpi); out.append(Image.frombytes('RGB', [pm.width, pm.height], pm.samples).convert('L'))
                return out
            except Exception:
                sys.exit('错误: 无法渲染 PDF。请安装 poppler-utils（pdftoppm）或 PyMuPDF，或请使用者把 PDF 导出为图片。')
    return [Image.open(path).convert('L')]

def find_staffs(a):
    """返回 [(x0, x1, top, bottom, spacing)]：页面上每个六线谱的范围"""
    H, W = a.shape; dark = a < 235
    segs = []                                   # 每行里的长横线段（谱线常被 x 记号、数字打断，先把小缺口补上再量长度）
    minlen = W * 0.18; gapfill = max(8, int(W * 0.012))
    for y in range(H):
        row = dark[y]
        if row.sum() < minlen * 0.5: continue
        idx = np.flatnonzero(np.diff(np.concatenate(([0], row.view(np.int8), [0]))))
        runs = list(zip(idx[::2], idx[1::2])); merged = []
        for s, e in runs:
            if merged and s - merged[-1][1] <= gapfill: merged[-1][1] = e
            else: merged.append([s, e])
        for s, e in merged:
            if e - s >= minlen: segs.append((y, int(s), int(e)))
    lines = []                                  # 合并相邻行 -> 线
    for y, s, e in segs:
        for L in lines:
            if y - L['y1'] <= 1 and abs(s - L['s']) < W * 0.03 and abs(e - L['e']) < W * 0.03:
                L['y1'] = y; L['s'] = min(L['s'], s); L['e'] = max(L['e'], e); break
        else: lines.append({'y0': y, 'y1': y, 's': s, 'e': e})
    lines = [L for L in lines if L['y1'] - L['y0'] + 1 <= max(3, H * 0.0025)]   # 太粗的是文字行，不是谱线
    staffs = []
    groups = []                                 # 左右两端都接近的线归为一组（同一栏里末行谱可能较短，所以按两端分组）
    for L in sorted(lines, key=lambda L: (L['s'], L['e'])):
        for g in groups:
            if abs(g[0]['s'] - L['s']) <= W * 0.012 and abs(g[0]['e'] - L['e']) <= W * 0.012: g.append(L); break
        else: groups.append([L])
    for g in groups:
        g.sort(key=lambda L: L['y0']); i = 0
        while i + 5 < len(g):
            ys = [g[i + k]['y0'] for k in range(6)]; d = np.diff(ys)
            if d.max() - d.min() <= max(3, d.mean() * 0.25) and d.mean() < H * 0.03:
                staffs.append((min(L['s'] for L in g[i:i + 6]), max(L['e'] for L in g[i:i + 6]), ys[0], g[i + 5]['y1'], float(d.mean()))); i += 6
            else: i += 1
    return staffs

cols_img, spacings = [], []
for path in A.inputs:
    for pi, page in enumerate(load_pages(path)):
        a = np.array(page); H, W = a.shape
        st = find_staffs(a)
        if not st: print(f'提示: {path} 第 {pi + 1} 页没有找到六线谱，已跳过'); continue
        spacings += [s[4] for s in st]
        st.sort(key=lambda s: s[0]); columns = []
        for s in st:                              # 左边界接近的归为同一栏
            for c in columns:
                if abs(c[0][0] - s[0]) < W * 0.1: c.append(s); break
            else: columns.append([s])
        columns.sort(key=lambda c: c[0][0])
        bounds = [(min(s[0] for s in c), max(s[1] for s in c)) for c in columns]
        for ci, (x0, x1) in enumerate(bounds):
            left = 0 if ci == 0 else (bounds[ci - 1][1] + x0) // 2
            right = W if ci == len(bounds) - 1 else (x1 + bounds[ci + 1][0]) // 2
            m = int((x1 - x0) * 0.02) + 8
            xa, xb = max(left, x0 - m), min(right, x1 + m)
            c = page.crop((xa, 0, xb, H)); ca = np.array(c)
            rows = np.flatnonzero((ca < 200).any(1))
            pad = 12
            cols_img.append(c.crop((0, max(0, rows.min() - pad), c.width, min(H, rows.max() + pad))))
        print(f'{os.path.basename(path)} 第 {pi + 1} 页: {len(st)} 个六线谱，{len(columns)} 栏')
if not cols_img: sys.exit('错误: 所有页面都没有找到六线谱。本技能只支持带六线谱的吉他谱。')

Wm = max(c.width for c in cols_img); gap = 30
stack = Image.new('L', (Wm, sum(c.height for c in cols_img) + gap * (len(cols_img) - 1)), 255); y = 0
for c in cols_img: stack.paste(c, (0, y)); y += c.height + gap
sp = float(np.median(spacings))
det_scale = min(1.0, 9.2 / sp)
disp_scale = min(1.0, det_scale * 2)
def save(scale, name):
    im = stack if scale == 1.0 else stack.resize((round(stack.width * scale), round(stack.height * scale)), Image.LANCZOS)
    im.save(os.path.join(A.out, name)); return im.size
ds = save(det_scale, 'det.png'); ps = save(disp_scale, 'disp.png')
json.dump({'det_scale': det_scale, 'disp_scale': disp_scale, 'K': disp_scale / det_scale, 'columns': len(cols_img), 'staff_spacing_src': sp},
          open(os.path.join(A.out, 'prep.json'), 'w'), indent=1)
print(f'原图谱线间距 {sp:.1f}px；det.png {ds}，disp.png {ps}，显示/检测比例 K={disp_scale / det_scale:.2f}')
if sp < 8.5: print('提示: 原图分辨率偏低，页面识谱的准确率会下降，交付时要告诉使用者')
print('第 1、2 步完成。下一步: python scripts/detect.py --out', A.out)
