# showcase-kit

A drop-in kit that turns **any codebase into a portfolio entry**, and merges all
your entries into one self-contained **portfolio site** — a landing page whose
buttons open per-project detail pages. Claude does the understanding; the small
scripts do the mechanical work.

## What's inside
```
showcase-kit/
  .claude/skills/showcase/SKILL.md   the skill Claude follows (study repo → showcase.json)
  probe.py                           deterministic facts: languages, LOC, git, deps, routes
  capture.py                         screen recordings + screenshots of a running app (tour-driven)
  build_site.py                      merges every showcase.json → site/index.html
  templates/portfolio.html           the site (dark/light, responsive, one file)
  schema/showcase.schema.json        the data shape a project entry conforms to
  portfolio.json.example             your owner info (name, bio, links, accent)
  examples/aaaflow/showcase.json     a real worked example
```

## Use it — per project
1. **Make the skill available.** Copy `.claude/skills/showcase` into the repo's
   `.claude/skills/`, or into `~/.claude/skills/` (user level) to have it in
   **every** repo automatically.
2. In the repo, tell Claude: **"showcase this project."** It runs `probe.py`,
   studies the code, captures screenshots of the running app (via the playwright
   MCP), and writes `showcase/showcase.json` + `showcase/media/`.
3. Copy that project's `showcase/` folder into your portfolio folder — one
   subfolder per project.

## Record the app (optional — for screen recordings)
`capture.py` drives a real browser through a JSON "tour" and saves an `.mp4`
recording per clip plus a `.png` per shot. Point it at any running local app:
```
python capture.py --url http://localhost:3000/ --tour tour.json --out examples/<slug>/media/
```
One-time: `pip install playwright && python -m playwright install chromium`.
The tour format is documented at the top of `capture.py`. Trim/convert clips with
ffmpeg if a recording opens on a blank/loading frame (mp4 plays everywhere; the
hero clip shows its poster with a play button rather than autoplaying).

## Build the portfolio site
```
python build_site.py --projects <portfolio-folder> --out site
# ...or one self-contained HTML file:  add  --inline
```
Open `site/index.html`, or deploy the whole `site/` folder to GitHub Pages /
Netlify / Vercel. Put your name, bio, links and accent colour in a
`portfolio.json` next to your projects (see `portfolio.json.example`).

## Notes
- **No custom MCP needed.** Screenshots use the **playwright MCP**; without it,
  the skill falls back to static analysis + manual screenshots.
- Python 3.8+ , standard library only. No install step.
- The kit is self-contained and independent of any project it documents.
