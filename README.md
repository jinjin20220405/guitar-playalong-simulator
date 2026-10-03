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

The sheet is never redrawn. The skill needs three things: where each bar sits on the image, what each bar should sound like, and how to line the two up in time.

1. `scripts/detect.py` finds the staves, barlines and note positions on the image and writes zoomed crops for reading
2. The agent fills `song.json` with chords, the picking pattern of the accompaniment and the positions of the jianpu and lyric rows (format in `references/song-schema.md`)
3. `scripts/build.py` validates the data and merges image, geometry and data into one HTML file from `assets/template.html`
4. When the page opens, a small recogniser inside it reads the jianpu digits, underlines and dots from the image and turns them into the melody

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
- The in-page melody reader has been tested on one sheet so far. On that sheet about 9 bars in 10 passed the beat check; octave dots squeezed between underlines and lyrics are the weakest point. Expect to correct some bars by hand
- Ties are re-articulated and grace notes are skipped

## About the material you use

This repository ships no songs; the only example is a four-bar public-domain melody used as a format sample. Which sheet you turn into a simulator is your decision. The skill tells the agent not to rule on legal questions about your material by itself, and to tell you up front about anything it will not do.

## Repository layout

```
guitar-playalong-simulator/     the skill itself
├── SKILL.md                    workflow the agent follows (written in Chinese)
├── scripts/detect.py           layout detection
├── scripts/build.py            validation + HTML generation
├── scripts/smoke_test.py       optional headless-browser test
├── assets/template.html        page template: UI, synthesis, scheduling, i18n
├── references/song-schema.md   data format and score-reading rules
└── examples/demo.song.json     format sample (public-domain melody)
```

## License

MIT. See [LICENSE](LICENSE).

---

Keywords: guitar tab player, tablature to web app, play-along, practice tool, jianpu, numbered musical notation, 吉他谱, 六线谱, 简谱, 跟弹, Claude skill, agent skill, Web Audio, Karplus-Strong.
