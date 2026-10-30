# guitar-playalong-simulator 技能文件夹

把吉他谱转成可以离线打开的网页跟弹播放器。给 AI 看的说明在 `SKILL.md`，识谱规则在 `references/transcription.md`，数据格式在 `references/format.md`。

## 常用命令

只需要 python3（标准库），不用安装别的东西。在本文件夹里：

```bash
python3 scripts/gsh.py check examples/selftest.score.json
```

```bash
python3 scripts/gsh.py build examples/selftest.score.json
```

附原谱图片时加 `-i 图片路径`（多页就写多个 `-i`）。原图太大时先缩小（macOS）：

```bash
python3 scripts/gsh.py shrink 原谱.png -o 原谱_4000.png
```

检查吉他旋律和简谱是否一致（能发现读错的品位）：

```bash
python3 scripts/gsh.py pitchcheck 曲名.score.json --part g2
```

自动测试：

```bash
python3 tests/test_gsh.py
```

## 播放器操作

- 播放／暂停：按钮或空格键。“停止”回到起点；“从头播放”从起点重新开始。左右方向键跳到上一小节或下一小节。
- 速度：0.5～1.5 倍，只改快慢，不改音高。
- 选段：选起止位置（两端都包含），按“启用选段”；再按“循环”就反复练这一段。
- 段落按钮：数据里写了 `sections` 的，顶部会出现段落按钮，点一下就选中这一段并循环；“全曲”取消选段。
- 重复的小节按“第 n 小节（第 p 遍）”区分，选段不会混淆。点谱面上任一小节，从那里开始播放。
- “原谱”页：按小节坐标把原谱逐行切开，宽屏自动分栏、一屏放完；当前小节标黄，竖线随拍子移动。“一屏显示”关掉后改为单栏放大，播放时自动滚动。
- 变调夹：可另选品位，伴奏和旋律一起移调，旁边显示实际发音的调。
- 每个声部可以单独静音、独奏、调音量。
- 界面语言：右上角选择，共九种。
- “歌词译文”页：按句输入或整段粘贴译文，显示在谱面歌词下方，播放时顶部显示当前一句。
- 速度、音量、静音、节拍器、预备拍、变调夹、语言会记在本机浏览器里，下次打开自动恢复。
- “导出”页可以把内嵌的工程数据存成 JSON，供修订后重新生成。
