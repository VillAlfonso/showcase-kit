---
name: showcase
description: Turn the current codebase into a truthful portfolio entry — study the whole project, run probe.py for mechanical facts, capture the running app as screenshots via the playwright MCP, and write a schema-valid showcase.json that build_site.py renders into a portfolio site with a landing page and per-project detail pages. Invoke when the user says "showcase this project", "add this repo to my portfolio", "generate a portfolio entry/page", or drops showcase-kit into a repo.
---

# showcase — generate a portfolio entry from any codebase

Produce `showcase/showcase.json` (+ screenshots in `showcase/media/`) that is
TRUE to what the project actually is and does. The portfolio site is built later
from every project's showcase.json by `build_site.py`.

`<kit>` below = the showcase-kit folder (where this skill, probe.py and
build_site.py live).

## Pipeline — follow in order

### 1. Probe the mechanical facts first (deterministic)
```
python <kit>/probe.py .  --out showcase/probe.json
```
It records languages + lines of code, git stats (remote, commits, dates),
detected project type, run commands, routes, manifests and the README title.
Read it — these are FACTS you must not contradict or invent around.

### 2. Study the project — the "every nook and cranny" part
Read, don't guess: the README, the manifest (package.json / pyproject.toml /
Cargo.toml / …), the main entry point(s), the routes/handlers probe found,
config, and a representative sample of the core modules. Skim `git log` for the
arc of the work. From evidence, answer:
- What problem does it solve, in one sentence a non-expert understands?
- The 4–7 things that are genuinely notable or hard (no filler).
- The real tech stack — only what is actually used.
- Honest metrics (LOC, stages, scale) — from probe.json, never fabricated.

### 3. Capture what it looks like running (screenshots)
Determine how to run it from `probe.run_commands` / the README.
- **Web app:** start the dev server, then use the **playwright MCP** —
  `browser_navigate` to each key screen (use `probe.routes` to enumerate them),
  `browser_take_screenshot` into `showcase/media/`. Capture a core FLOW as an
  ordered set of shots (`01-landing.png`, `02-form.png`, `03-result.png`) — that
  ordered set IS the "recording of the flow." Prefer ~1280×800. Name each file
  by what it shows.
  For actual VIDEO recordings, use the kit's `capture.py` with a JSON tour:
  `python <kit>/capture.py --url <app-url> --tour tour.json --out showcase/media/`.
  It saves one `.mp4` per clip plus a `.png` poster; reference them as media
  entries `{ "type": "video", "src": "clip.mp4", "poster": "clip.png" }`.
- **CLI / tool:** run a representative command; capture the terminal output as a
  section (or a screenshot of a styled terminal).
- **Library:** pull 1–3 real usage examples from the README or tests.
- **Can't run it?** Leave media entries with empty `"src"` and a caption
  describing the intended shot — the site renders a labeled placeholder and the
  user captures later.
Mark exactly ONE shot `"role":"hero"` — it becomes the card thumbnail.

### 4. Write showcase/showcase.json
Conform to `<kit>/schema/showcase.schema.json`. Fill: slug, name, tagline,
summary, problem, role, status, year, featured, tech[], topics[], highlights[],
metrics[], links[] (repo from `probe.git.remote`; live demo if one exists),
media[] (the screenshots), sections[] (heading + markdown body — e.g. "How it
works", "Notable engineering"), repo{} (from probe).

### 5. Preview
```
python <kit>/build_site.py --projects <folder-of-projects> --out site
```
Open `site/index.html`. Add `--inline` for a single self-contained HTML file.

## Rules
- **TRUTH ONLY.** Every metric and feature must trace to code, probe.json or the
  README. When unsure, leave it out. An accurate, modest entry beats an
  oversold one.
- **NEVER capture or write secrets.** Skip `.env`, credentials, tokens, keys. If
  a screenshot would show a secret or real personal data, don't take it (or crop
  it). Don't screenshot real user data.
- Keep media light: PNG/JPEG, ≤ ~1600px wide. Never include node_modules or
  build output.
- Caption every shot (captions are the alt text).
- Write nothing outside `showcase/` in the target repo unless asked.

## Make it available in every repo
Copy `.claude/skills/showcase/` into a repo's `.claude/skills/`, or into
`~/.claude/skills/` (user level) so `/showcase` works everywhere.
