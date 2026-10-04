# Guitar Play-along Simulator (Agent Skill)

**Turn a photo of a guitar tab into a web page you can practise along with.**
Give an AI agent one image of a guitar score (six-line tablature + numbered notation / jianpu), and this skill walks it through producing a single self-contained HTML file: your original sheet on screen, a cursor moving in time, the accompaniment and the melody sounding together.

[简体中文说明](README.zh-CN.md)

![Control bar of a generated simulator](docs/controls.png)

## What the generated page does

- Shows the **original sheet image**, re-flowed into as many columns as needed so that **everything fits on one landscape screen** with no scrolling (single column on phones); a cursor follows the beat and the current bar is highlighted
- Plays the **guitar accompaniment** from the tab (plucked-string synthesis, no samples)
- **Reads the numbered notation (jianpu) by itself, in the browser**, and plays the melody; bars whose beats do not add up are outlined in red and can be corrected in place
- **Tempo** slider, **metronome**, optional **count-in**, **capo** selector (none to fret 5)
- **Loop** any section or any range of bars; click any bar to jump there
- **Nine interface languages**: 简体中文, 繁體中文, English, 日本語, 한국어, Español, Français, Deutsch, Português
- **Lyric translation slots**: users type or paste their own translation and it is laid over the lyric lines; it can be saved, downloaded, reloaded or cleared
- Light and dark themes; no network needed once generated

## Five principles the skill gives the agent

1. Re-layout is allowed when it makes the sheet easier to use
2. Fit everything on one screen of an ordinary landscape monitor whenever possible
3. Stay faithful to the user's content; apart from layout, change nothing without the user's permission, and say so **before** starting if some part cannot be done
4. Do not make legal determinations (copyright or otherwise) about the user's material on your own; if the agent has limits of its own, it states them as its own limits
5. Keep asking whether every way of making the goal easy for people has been tried

## How it works

The sheet is never redrawn. The whole job is a fixed sequence of five commands; each one prints what to run next, so even a modest agent can follow it.

| Step | Command | What the agent does |
|---|---|---|
| 1–2 Convert and tidy | `prepare.py sheet.pdf --out work/` | nothing: PDF rendering, column detection, stacking and scaling are automatic |
| 3, 5 Locate | `detect.py --out work/` | read one section of the report ("needs a human look") |
| 4 Read | fill `work/song.txt`, then `make_song.py --out work/` | copy the chord names from numbered zoom images, confirm the picking pattern |
| 6 Build | `build.py --out work/ --html song.html` | nothing |
| 7 Check | `check.py song.html` | look at one screenshot, report the numbers |

- Bar lines, jianpu rows and lyric rows are located by the scripts; nobody measures coordinates
- Zoom images carry a red index above every bar, so chords are copied one index at a time
- `song.txt` is a short table, not JSON; mistakes are reported in plain words ("row 3 needs 8 chords, you wrote 7")
- When the page opens, a small recogniser inside it reads the jianpu digits, underlines and dots and turns them into the melody

## Requirements

An AI agent that can **run Python** (Pillow, numpy) and **read images**. Chat-only models without code execution cannot use this skill.

## Install

**Claude (web / desktop)** – download the ZIP from Releases, then upload it under *Customize → Skills* (code execution must be enabled).

**Claude Code** – copy the skill folder into your personal skills directory:

```bash
git clone https://github.com/jinjin20220405/guitar-playalong-simulator.git
cp -r guitar-playalong-simulator/guitar-playalong-simulator ~/.claude/skills/
```

**Other agents** – put the `guitar-playalong-simulator/` folder where the agent can read it and say: "Read SKILL.md first, then follow it."

## Use

Upload your tab image and ask, for example:

> Make a play-along simulator from this guitar tab.

The agent asks one or two questions, runs the scripts, and hands back an HTML file. Sound quality and note accuracy should be checked by ear against your sheet; low-resolution images may lead to a few misread notes.

## Scope and limits

- Built for scores that combine **six-line tab with numbered notation (jianpu)**. Pure staff notation is not supported
- Tested on three inputs so far (a high-resolution two-column image, a low-resolution single-column image, a scanned PDF). Layout and bar counts came out right on all three; the in-page melody reader got about 9 bars in 10 on the sharp image and 7–8 in 10 on the others. Expect to correct some bars by hand, more on low-resolution scans
- Very faint bar lines may be missed; the report flags the suspicious bar and says exactly what to add
- Ties are re-articulated and grace notes are skipped
- Step 4 still needs an agent that can read chord names from an image

## About the material you use

This repository ships no songs; the only example is a four-bar public-domain melody used as a format sample. Which sheet you turn into a simulator is your decision. The skill tells the agent not to rule on legal questions about your material by itself, and to tell you up front about anything it will not do.

## Repository layout

```
guitar-playalong-simulator/     the skill itself
├── SKILL.md                    the seven-step procedure (written in Chinese)
├── scripts/prepare.py          steps 1–2: PDF/image → single-column, scaled
├── scripts/detect.py           steps 3, 5: staves, bar lines, rows, numbered zooms
├── scripts/make_song.py        step 4: song.txt → song.json
├── scripts/build.py            step 6: one self-contained HTML file
├── scripts/check.py            step 7: automatic checks (needs playwright)
├── assets/template.html        page template: UI, layout, synthesis, melody reader, i18n
├── references/song-schema.md   formats of song.txt / song.json / geometry.json
└── examples/demo.song.json     format sample (public-domain melody)
```

## License

MIT. See [LICENSE](LICENSE).

---

Keywords: guitar tab player, tablature to web app, play-along, practice tool, jianpu, numbered musical notation, 吉他谱, 六线谱, 简谱, 跟弹, Claude skill, agent skill, Web Audio, Karplus-Strong.
