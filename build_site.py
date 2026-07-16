#!/usr/bin/env python3
"""build_site.py -- merge showcase.json files into one self-contained portfolio site.

Usage:
  python build_site.py --projects <dir> --out site [--config portfolio.json] [--inline]

Scans <dir> for project entries (each a showcase.json), copies their media, and
renders templates/portfolio.html into <out>/index.html. With --inline, images are
embedded as data URIs so the result is a single portable HTML file.

Standard library only.
"""
import argparse, base64, json, mimetypes, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE / "templates" / "portfolio.html"


def slugify(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(s or "").strip().lower()).strip("-")
    return s or "project"


def find_showcases(projects):
    p = Path(projects)
    if p.is_file() and p.suffix == ".json":
        return [p]
    cands = set()
    if (p / "showcase.json").exists():
        cands.add(p / "showcase.json")
    for pattern in ("*/showcase.json", "*/showcase/showcase.json",
                    "showcase/showcase.json", "*.showcase.json"):
        cands.update(p.glob(pattern))
    return sorted(cands)


def data_uri(path):
    mime, _ = mimetypes.guess_type(str(path))
    b = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime or 'application/octet-stream'};base64,{b}"


def main():
    ap = argparse.ArgumentParser(description="Build a portfolio site from showcase.json files.")
    ap.add_argument("--projects", default=".", help="dir to scan (or a single .json)")
    ap.add_argument("--out", default="site", help="output dir")
    ap.add_argument("--config", default=None, help="portfolio.json with owner info")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    ap.add_argument("--inline", action="store_true", help="embed media as data URIs")
    ap.add_argument("--title", default=None)
    a = ap.parse_args()

    showcases = find_showcases(a.projects)
    if not showcases:
        print(f"! no showcase.json found under {a.projects}", file=sys.stderr)
        sys.exit(1)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    media_root = out / "media"

    owner = {}
    cfg = Path(a.config) if a.config else Path(a.projects) / "portfolio.json"
    if cfg.exists():
        try:
            owner = json.loads(cfg.read_text(encoding="utf-8")).get("owner", {})
        except Exception as e:
            print(f"! bad config {cfg}: {e}", file=sys.stderr)

    projects = []
    for sc in showcases:
        try:
            data = json.loads(sc.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"! skip {sc}: {e}", file=sys.stderr)
            continue
        data["slug"] = data.get("slug") or slugify(data.get("name") or sc.parent.name)
        base = sc.parent
        for m in data.get("media", []) or []:
            for key in ("src", "poster"):        # copy/inline both the media and its poster
                val = m.get(key)
                if not val:
                    continue
                srcpath = base / val
                if not srcpath.exists():
                    alt = base / "media" / Path(val).name
                    srcpath = alt if alt.exists() else srcpath
                if not srcpath.exists():
                    print(f"  . {data['slug']}: media not found: {val}", file=sys.stderr)
                    m[key] = ""
                    continue
                if a.inline:
                    m[key] = data_uri(srcpath)
                else:
                    dest_dir = media_root / data["slug"]
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(srcpath, dest_dir / srcpath.name)
                    m[key] = f"media/{data['slug']}/{srcpath.name}"
        projects.append(data)

    payload = {"owner": owner, "projects": projects}
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = a.title or (owner.get("name", "Portfolio") + " - Projects")
    tpl = Path(a.template).read_text(encoding="utf-8")
    html = tpl.replace("{{TITLE}}", title).replace("{{DATA}}", blob)
    (out / "index.html").write_text(html, encoding="utf-8")

    print(f"OK built {len(projects)} project(s) -> {out / 'index.html'}")
    for p in projects:
        print(f"   . {p['slug']}: {p.get('name')}")
    if not a.inline and media_root.exists():
        print(f"   media -> {media_root}")
    print("Open index.html, or deploy the folder (GitHub Pages / Netlify / Vercel).")


if __name__ == "__main__":
    main()
