#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke_test.py  用无头浏览器把生成的页面跑一遍：播放、循环、截图、收集 JS 错误。

用法:  python smoke_test.py 跟弹模拟器.html [输出目录]
依赖:  pip install playwright && playwright install chromium
说明:  只能验证"能跑、光标位置对"，声音好不好听要靠人试听。
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

html = os.path.abspath(sys.argv[1]); out = sys.argv[2] if len(sys.argv) > 2 else '.'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required'])
        pg = await b.new_page(viewport={'width': 1920, 'height': 960})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        await pg.goto('file://' + html)
        print('小节数/演奏顺序长度:', await pg.evaluate('SONG.length+" / "+FULL.length'))
        await pg.click('#pre')                       # 关掉预备拍，直接进
        await pg.click('#play'); await pg.wait_for_timeout(8000)
        print('播放 8 秒后:', await pg.evaluate('[$("where").textContent,$("chord").textContent,ctx.state].join(" | ")'))
        await pg.screenshot(path=os.path.join(out, 'shot_wide.png'))
        await pg.click('#play')
        chips = await pg.query_selector_all('#chips .chip')
        if len(chips) > 1:
            await chips[-1].click(); await pg.click('#play'); await pg.wait_for_timeout(3000)
            print('循环最后一段 3 秒后:', await pg.evaluate('$("where").textContent'))
            await pg.click('#play')
        await pg.set_viewport_size({'width': 420, 'height': 800}); await pg.wait_for_timeout(300)
        await pg.screenshot(path=os.path.join(out, 'shot_narrow.png'))
        print('JS 错误:', errs or '无')
        await b.close()
asyncio.run(main())
