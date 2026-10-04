#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check.py  第 7 步：自动核对生成的网页。逐项打印"通过 / 不通过 / 提示"，最后给出要告诉使用者的数字。

用法:
    python check.py 曲名跟弹模拟器.html

需要 playwright（pip install playwright && playwright install chromium）。没有的话脚本会说明哪些项没查，
这时必须如实告诉使用者"页面未经实际运行测试"。
"""
import asyncio, os, re, sys, json

html = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else sys.exit('用法: python check.py 网页文件.html')
if not os.path.exists(html): sys.exit(f'错误: {html} 不存在')
src = open(html, encoding='utf-8').read()
ok = True
def line(tag, msg):
    global ok
    if tag == '不通过': ok = False
    print(f'[{tag}] {msg}')
for ph in ('/*SYS*/', '/*MEAS*/', '/*SONG*/'):
    if ph in src: line('不通过', f'网页里还留着占位符 {ph}，build.py 没有正常完成')
line('通过' if len(src) < 12 * 1024 * 1024 else '不通过', f'文件大小 {len(src) // 1024} KB')
try:
    from playwright.async_api import async_playwright
except Exception:
    print('[提示] 没有安装 playwright，以下各项没有检查：能否运行、是否一屏放完、页面识谱结果。交付时必须告诉使用者"页面未经实际运行测试"。')
    sys.exit(0)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required']); errs = []
        for w, h in ((1920, 950), (1366, 650)):
            pg = await b.new_page(viewport={'width': w, 'height': h}, locale='zh-CN')
            pg.on('pageerror', lambda e: errs.append(str(e)))
            await pg.goto('file://' + html); await pg.wait_for_timeout(1800)
            r = await pg.evaluate('''()=>{const s=[...document.querySelectorAll(".sys")].map(e=>e.getBoundingClientRect());
              return {n:SONG.length, seq:FULL.length, cols:document.querySelectorAll(".col").length, scroll:document.documentElement.scrollHeight>innerHeight+1,
                      inside:Math.max(...s.map(r=>r.bottom))<=innerHeight+1&&Math.max(...s.map(r=>r.right))<=innerWidth+1, sysW:Math.round(s[0].width),
                      read:SONG.filter(x=>x.jpNotes&&x.jpNotes.length).length, bad:SONG.filter(x=>x.jpBad).length, mel:SONG.some(x=>x.v.length), rows:(S.jianpuRows||[]).length}}''')
            line('通过' if (not r['scroll'] and r['inside']) else '不通过', f'{w}×{h} 屏幕：{r["cols"]} 栏，{"一屏放完，无滚动" if (not r["scroll"] and r["inside"]) else "有内容超出屏幕"}，每行谱宽 {r["sysW"]}px')
            if w == 1920:
                line('通过', f'小节数 {r["n"]}，演奏顺序共 {r["seq"]} 个小节')
                if r['rows']:
                    rate = r['read'] and (r['read'] - r['bad']) / max(1, r['n'])
                    line('通过' if r['mel'] else '不通过', f'页面识谱：读出 {r["read"]} 个小节，其中 {r["bad"]} 个拍数对不上（会标红框）')
                    if r['read'] and r['bad'] / r['read'] > 0.25: line('提示', f'拍数对不上的小节占 {r["bad"] * 100 // r["read"]}%，偏多（常见于分辨率低的谱）。交付时要告诉使用者：旋律需要用页面上的“旋律校对”改正较多小节，或请他提供更清晰的谱')
                    if r['read'] < r['n'] * 0.5: line('提示', '读出的小节不到一半，多半是简谱行位置不对：看 geometry.json 里各行的 jianpu，或谱上本来就没有简谱')
                else: line('提示', '没有简谱行位置，页面不会发旋律声')
                await pg.click('#pre'); await pg.click('#play'); await pg.wait_for_timeout(3000)
                st = await pg.evaluate('[ctx.state, live.length, $("where").textContent].join(" | ")')
                line('通过' if 'running' in st else '不通过', f'播放 3 秒：{st}')
                await pg.click('#play'); await pg.screenshot(path=os.path.splitext(html)[0] + '_check.png')
                print(f'[提示] 截图已存为 {os.path.splitext(html)[0]}_check.png，请打开看一眼：谱面是否完整、黄色光标是否压在某个小节上')
            await pg.close()
        line('通过' if not errs else '不通过', 'JS 错误：' + ('无' if not errs else '; '.join(errs[:3])))
        await b.close()
asyncio.run(main())
print('\n结论：' + ('自动检查全部通过。' if ok else '有不通过的项，先解决再交付。') + ' 声音只能由使用者试听；交付时把上面"页面识谱"那一行的数字原样告诉使用者。')
