#!/usr/bin/env python3
"""capture.py -- record human-looking walkthrough videos of a running web app.

    python capture.py --url http://127.0.0.1:8000/ --tour tour.json --out media/

One-time setup:  pip install playwright  &&  python -m playwright install chromium
If ffmpeg is on PATH, each clip is auto-trimmed (the page-load dead time is cut)
and converted to .mp4; otherwise the raw .webm is kept.

A VISIBLE CURSOR is injected into the page (tour "cursor": true, default) so
viewers see the mouse glide to each control and press it -- recordings read as a
human demo, not a slideshow.

tour.json:
{
  "viewport": {"width": 1440, "height": 900},
  "settle_ms": 1200,          // wait after navigations
  "cursor": true,             // show the injected cursor
  "scroll_el": ".views",      // the app's scroll container ("" = window)
  "clips": [
    {"name": "01-home", "steps": [
      {"goto": "#/home"},                       // navigate (recording trims to here)
      {"move": "button.cta"},                   // glide the cursor onto an element
      {"click": ".hub-card:has-text('X') .go"}, // glide + press (any Playwright selector)
      {"type": {"selector": "#idea", "text": "hello", "delay": 45}},
      {"scroll": 500},                          // smooth-scroll the container (px, +/-)
      {"scroll": {"px": 400, "el": ".modal-card"}},
      {"play": "video"}, {"pause": "video"},    // drive a <video> element
      {"press": "Escape"},
      {"eval": "document.title"},               // JS escape hatch
      {"wait": 1500},
      {"shot": true}                            // .png (first shot = clip poster)
    ]}
  ]
}
Nothing here is app-specific; the tour file carries all app knowledge.
"""
import argparse, json, math, random, shutil, subprocess, sys, time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright not installed. Run: pip install playwright && python -m playwright install chromium")

CURSOR_JS = """
(() => {
  if (window.__pwCur) return; window.__pwCur = true;
  const mk = () => {
    if (document.getElementById('__pwCurEl')) return;
    const c = document.createElement('div'); c.id = '__pwCurEl';
    Object.assign(c.style, {position:'fixed', left:'-40px', top:'-40px', width:'22px', height:'22px',
      border:'2.5px solid rgba(255,255,255,.95)', borderRadius:'50%', background:'rgba(110,130,255,.30)',
      boxShadow:'0 0 0 1.5px rgba(0,0,0,.55), 0 2px 10px rgba(0,0,0,.45)', zIndex:2147483647,
      pointerEvents:'none', transform:'translate(-50%,-50%)',
      transition:'width .12s, height .12s, background .12s'});
    (document.body || document.documentElement).appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX+'px'; c.style.top = e.clientY+'px'; }, true);
    addEventListener('mousedown', () => { c.style.width='32px'; c.style.height='32px'; c.style.background='rgba(255,190,80,.6)'; }, true);
    addEventListener('mouseup',   () => { c.style.width='22px'; c.style.height='22px'; c.style.background='rgba(110,130,255,.30)'; }, true);
  };
  document.readyState === 'loading' ? addEventListener('DOMContentLoaded', mk) : mk();
})();
"""


def ffmpeg():
    return shutil.which("ffmpeg")


class Driver:
    """Human-feel pointer: eased moves from a tracked position, pressed clicks."""

    def __init__(self, page):
        self.page, self.x, self.y = page, 60.0, 60.0

    def _target(self, sel):
        loc = self.page.locator(sel).first
        loc.wait_for(state="visible", timeout=8000)
        loc.scroll_into_view_if_needed(timeout=5000)
        self.page.wait_for_timeout(220)
        b = loc.bounding_box()
        if not b:
            raise RuntimeError(f"no bbox for {sel}")
        return b["x"] + b["width"] / 2 + random.uniform(-3, 3), b["y"] + b["height"] / 2 + random.uniform(-2, 2)

    def move(self, sel):
        tx, ty = self._target(sel)
        dist = math.hypot(tx - self.x, ty - self.y)
        segs = max(3, min(7, int(dist / 140)))
        for i in range(1, segs + 1):
            t = i / segs
            e = 1 - (1 - t) ** 3                      # ease-out
            self.page.mouse.move(self.x + (tx - self.x) * e, self.y + (ty - self.y) * e, steps=9)
            self.page.wait_for_timeout(34)
        self.x, self.y = tx, ty

    def click(self, sel):
        self.move(sel)
        self.page.wait_for_timeout(210)
        self.page.mouse.down(); self.page.wait_for_timeout(95); self.page.mouse.up()
        self.page.wait_for_timeout(320)

    def type(self, sel, text, delay=45):
        self.click(sel)
        self.page.keyboard.type(text, delay=delay)


def smooth_scroll(page, px, el):
    page.evaluate(
        """([px, sel]) => {
             const t = (sel && document.querySelector(sel)) || document.scrollingElement;
             t.scrollBy({top: px, behavior: 'smooth'});
           }""", [px, el])
    page.wait_for_timeout(min(2200, 650 + abs(int(px))))


def run(base, tour, out):
    out.mkdir(parents=True, exist_ok=True)
    vp = tour.get("viewport", {"width": 1440, "height": 900})
    settle = int(tour.get("settle_ms", 1200))
    scroll_el = tour.get("scroll_el", "")
    made = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--hide-scrollbars", "--autoplay-policy=no-user-gesture-required"])
        for clip in tour.get("clips", []):
            name = clip.get("name", "clip")
            print(f"clip {name} ...")
            ctx = browser.new_context(viewport=vp, record_video_dir=str(out),
                                      record_video_size=vp, device_scale_factor=1)
            if tour.get("cursor", True):
                ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            drv = Driver(page)
            t0, trim = time.monotonic(), 0.0
            shot_i = 0
            try:
                for st in clip.get("steps", []):
                    if "goto" in st:
                        tgt = st["goto"]
                        url = tgt if tgt.startswith("http") else base.rstrip("/") + "/" + tgt.lstrip("/")
                        page.goto(url, wait_until="load", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=6000)
                        except Exception:
                            pass                       # pages that poll never go idle
                        page.wait_for_timeout(settle)
                        if trim == 0.0:                # recording starts at first ready paint
                            trim = max(0.0, time.monotonic() - t0 - 0.25)
                            page.mouse.move(drv.x, drv.y)   # summon the cursor
                    if "hash" in st:
                        page.evaluate("h => { location.hash = h; }", st["hash"])
                        page.wait_for_timeout(settle)
                    if "move" in st:
                        drv.move(st["move"])
                    if "click" in st:
                        try:
                            drv.click(st["click"])
                        except Exception as e:
                            print(f"  ! click miss {st['click']}: {e}")
                    if "type" in st:
                        t = st["type"]
                        drv.type(t["selector"], t["text"], int(t.get("delay", 45)))
                    if "press" in st:
                        page.keyboard.press(st["press"]); page.wait_for_timeout(300)
                    if "scroll" in st:
                        s = st["scroll"]
                        px, el = (s, scroll_el) if isinstance(s, (int, float)) else (s.get("px", 400), s.get("el", scroll_el))
                        smooth_scroll(page, px, el)
                    if "play" in st:
                        page.evaluate("sel => { const v = document.querySelector(sel); if (v) { v.muted = true; v.play(); } }", st["play"])
                    if "pause" in st:
                        page.evaluate("sel => { const v = document.querySelector(sel); if (v) v.pause(); }", st["pause"])
                    if "eval" in st:
                        page.evaluate(st["eval"])
                        page.wait_for_timeout(300)
                    if "wait" in st:
                        page.wait_for_timeout(int(st["wait"]))
                    if st.get("shot"):
                        shot_i += 1
                        sn = st["shot"] if isinstance(st["shot"], str) else (name if shot_i == 1 else f"{name}-{shot_i}")
                        page.screenshot(path=str(out / f"{sn}.png"))
                        made.append(f"{sn}.png")
            except Exception as e:
                print(f"  ! clip {name} error: {e}")
            vid = page.video
            ctx.close()                                # finalizes the video file
            try:
                src = Path(vid.path())
                if ffmpeg():
                    dest = out / f"{name}.mp4"
                    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{trim:.2f}", "-i", str(src),
                                    "-an", "-c:v", "libx264", "-crf", "21", "-pix_fmt", "yuv420p",
                                    "-movflags", "+faststart", str(dest)], check=True)
                    src.unlink()
                else:
                    dest = out / f"{name}.webm"
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(src), str(dest))
                made.append(dest.name)
                print(f"  -> {dest.name} (trimmed {trim:.1f}s of load)")
            except Exception as e:
                print(f"  ! video save {name}: {e}")
        browser.close()
    return made


def main():
    ap = argparse.ArgumentParser(description="Record walkthrough videos of a running web app.")
    ap.add_argument("--url", required=True, help="base URL of the running app")
    ap.add_argument("--tour", required=True, help="tour JSON describing clips/steps")
    ap.add_argument("--out", default="media", help="output dir for videos + shots")
    a = ap.parse_args()
    tour = json.loads(Path(a.tour).read_text(encoding="utf-8"))
    made = run(a.url, tour, Path(a.out))
    print(f"\nOK {len(made)} file(s) -> {a.out}")


if __name__ == "__main__":
    main()
