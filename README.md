# Guitar Play-along Simulator (Agent Skill) 2.0

**Turn a guitar score into a web page you can practise along with.**
Give an AI agent an image or PDF of a guitar score (six-line tablature + numbered notation / jianpu). This skill walks it through transcribing the score bar by bar into project data, then a script builds a single self-contained HTML file: the accompaniment and the melody sound together while a cursor follows the beat.

[简体中文说明](README.zh-CN.md)

![A generated player](docs/player.jpg)

## What changed in 2.0

Version 1.x showed the original image and let the page read the jianpu by itself. That was quick, but users had to fix the reading note by note in the page. 2.0 works differently:

- **Transcribe to data first, then build the page.** The agent reads the image bar by bar and writes tablature, chord shapes, jianpu and lyrics into `score.json`; the script validates it and builds the player. The data is the single source: fix mistakes in the data and rebuild.
- **Anything unreadable becomes a listed doubt**, never a guess. The page has a *Doubts & status* tab and shows a "draft" badge while key doubts are open.
- **Built-in self-checks**: note values per bar, chord shapes, guitar melody vs. jianpu (`pitchcheck`), and warnings for large melodic leaps that usually mean a misread octave dot.
- In-page melody editing is gone; the nine interface languages and lyric translation are kept.

## What the generated page does

- **Redrawn score** in the style of a printed guitar score (tablature, chord diagrams, strum arrows, jianpu, lyrics), for checking bar by bar against the original
- **Original tab**: the original is cut into rows by bar position and re-flowed into columns so it fits one landscape screen; the current bar is highlighted and a line moves with the beat
- Accompaniment and melody as separate parts (plucked-string synthesis, no samples), each with mute, solo and volume
- **Speed** 0.5–1.5× (pitch unchanged), **metronome**, **count-in**, **capo** 0–7 (transposes everything)
- **Range loop**, one-click **section loops**, click any bar to jump, Space to play or pause, left/right arrows to move a bar; repeats are expanded automatically
- **Nine interface languages**: 简体中文, 繁體中文, English, 日本語, 한국어, Español, Français, Deutsch, Português
- **Lyric translation**: users type a translation per line or paste it whole; it appears under the lyrics and the current line is shown at the top while playing; download, load from file, clear; when published as a Claude Artifact it can also be saved to the account
- Speed, volume, language and similar settings are remembered in the browser; light and dark themes; no network needed once generated

## Five principles the skill gives the agent

1. Re-layout is allowed when it makes the sheet easier to use
2. Fit everything on one screen of an ordinary landscape monitor whenever possible
3. Stay faithful to the user's content; apart from layout, change nothing without the user's permission, and say so **before** starting if some part cannot be done
4. Do not make legal determinations (copyright or otherwise) about the user's material on your own; if the agent has limits of its own, it states them as its own limits
5. Keep asking whether every way of making the goal easy for people has been tried

## Requirements

- The agent must be able to **run Python 3** (standard library only; no Pillow or numpy) and **see images**. Chat-only models without code execution cannot use it.
- The crop and shrink commands call macOS `sips`; on other systems use another tool instead.

## Install

**Claude web / desktop**: download the ZIP from Releases and upload it under *Customize → Skills* (code execution must be on). If 1.x is installed, remove it first.

**Claude Code**: copy the skill folder into your personal skills directory:

```bash
git clone https://github.com/jinjin20220405/guitar-playalong-simulator.git
```

```bash
cp -r guitar-playalong-simulator/guitar-playalong-simulator ~/.claude/skills/
```

**Other agents**: put the `guitar-playalong-simulator/` folder where the agent can read it and tell it: "Read SKILL.md first and follow it."

## Use

Upload a guitar score image and say, for example:

> Turn this guitar score into a play-along simulator.

The agent first says how it will work and what it cannot do. For a long score it transcribes a few bars for you to check, then the whole piece, and hands back one HTML file plus a list of doubts. Check bar by bar against the original and listen; tell it the bar number of anything wrong.

## Scope and limits

- For guitar scores with tablature + jianpu (tablature alone also works); staff notation only is not supported
- Reading is done by the agent looking at the image and is not guaranteed; check every bar, especially on low-resolution scans; octave dots and fret numbers are the most common misreadings
- Guitar techniques (slides, hammer-ons, pull-offs, bends) are recorded but not played; strums do not model force; accelerando, ritardando and fermatas are not played
- D.S., Coda and similar jumps must be written as a play order in the data
- The interface texts in the eight non-Chinese languages were translated by AI and have not been checked by native speakers; doubts, assumptions and other data are shown in the language they were written in

## Files

| Path | Purpose |
|---|---|
| `guitar-playalong-simulator/SKILL.md` | Instructions for the agent: principles, workflow, reporting |
| `guitar-playalong-simulator/references/` | Data format and reading rules |
| `guitar-playalong-simulator/scripts/gsh.py` | Validate, build, pitch cross-check, crop, shrink |
| `guitar-playalong-simulator/template/` | Player template and the nine-language text table |
| `guitar-playalong-simulator/examples/` | A self-made test score and the player built from it (open it in a browser) |
| `guitar-playalong-simulator/tests/` | Automated tests |

## About the scores you use

This repository contains no songs; the only example is a self-made test score. Which score you turn into a simulator is your decision. The skill tells the agent not to make legal determinations about your material on its own and to state up front anything it will not do.

## License

MIT, see [LICENSE](LICENSE).
