# Guitar Play-along Simulator (Agent Skill)

**Turn a photo of a guitar tab into a web page you can practise along with.**
Give an AI agent one image of a guitar score (six-line tablature + numbered notation / jianpu), and this skill walks it through producing a single self-contained HTML file: your original sheet on screen, a cursor moving in time, the accompaniment and the melody sounding together.

[简体中文说明](README.zh-CN.md)

![Control bar of a generated simulator](docs/controls.png)

## What the generated page does

- Shows the **original sheet image**, two columns on one screen (single column on phones), with a cursor that follows the beat and the current bar highlighted
- Plays the **guitar accompaniment** note by note from the tab (plucked-string synthesis, no samples) and the **melody** from the numbered notation, each with its own mute button and volume
- **Tempo** slider, **metronome**, optional **count-in**
- **Loop** any section (intro, verse, chorus…) or any range of bars; click any bar to jump there
- **Capo** selector (none to fret 5) that transposes the sound and shows the sounding key
- **Nine interface languages**: 简体中文, 繁體中文, English, 日本語, 한국어, Español, Français, Deutsch, Português
- **Lyric translation slots**: users type or paste their own translation and it is laid over the lyric lines; it can be saved, downloaded, reloaded or cleared
- Light and dark themes; no network needed once generated

## How it works

The sheet is never redrawn. The skill only needs to know three things: where each bar sits on the image, what notes each bar contains, and how to line the two up in time.

1. `scripts/detect.py` finds the staves, barlines and note positions on the image and writes zoomed crops for reading
2. The agent transcribes chords, tab and melody into `song.json` (format and reading rules in `references/song-schema.md`)
3. `scripts/build.py` validates the data and merges image, geometry and data into one HTML file from `assets/template.html`

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

- Built for scores that combine **six-line tab with numbered notation (jianpu)**, as commonly published for Chinese pop and folk guitar. Pure staff notation is not supported
- Tested on one layout style so far; other engraving styles may need the detection parameters adjusted (see the top of `detect.py`)
- Grace notes are skipped; slides and hammer-ons sound as plain notes

## Copyright note

This repository contains **no songs**. The only example is a four-bar public-domain melody used as a format sample. Sheet music and lyrics usually belong to their authors: generate simulators from scores you are entitled to use, keep them for your own practice, and do not commit copyrighted sheets or generated pages to public repositories. By design the skill tells the agent **not to transcribe or translate lyrics**; translation slots are filled in by the user.

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
