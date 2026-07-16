#!/usr/bin/env python3
"""showcase-kit web UI -- operate the kit from a browser.

    python kit_web.py            # http://127.0.0.1:8778

List / edit every project's showcase.json, probe any codebase for facts,
build the portfolio site with a live log, and preview it at /site/.
Stdlib only, zero deps.
"""
import argparse, json, mimetypes, subprocess, sys, threading, time, webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).parent
PROJECTS_DIR = HERE / "examples"
SITE_DIR = HERE / "site"
JOB = {"state": "idle", "kind": None, "log": deque(maxlen=2000), "result": None}


def run_job(kind, argv, cwd=HERE):
    if JOB["state"] == "running":
        raise RuntimeError(f"a {JOB['kind']} job is still running")
    JOB.update(state="running", kind=kind, result=None)
    JOB["log"].clear()
    JOB["log"].append("$ " + " ".join(map(str, argv)))

    def _run():
        try:
            p = subprocess.Popen(argv, cwd=str(cwd), stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True,
                                 encoding="utf-8", errors="replace", bufsize=1)
            for line in p.stdout:
                JOB["log"].append(line.rstrip())
            p.wait()
            JOB["result"] = {"code": p.returncode}
            JOB["state"] = "done" if p.returncode == 0 else "error"
        except Exception as ex:                        # noqa: BLE001
            JOB["log"].append(f"ERROR: {ex}")
            JOB["state"] = "error"

    threading.Thread(target=_run, daemon=True).start()


def list_projects():
    out = []
    for sj in sorted(PROJECTS_DIR.glob("*/showcase.json")):
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
            media_dir = sj.parent / "media"
            out.append({"slug": d.get("slug", sj.parent.name), "name": d.get("name", sj.parent.name),
                        "tagline": d.get("tagline", ""), "year": d.get("year"),
                        "featured": bool(d.get("featured")),
                        "media": len(d.get("media", [])),
                        "media_files": len(list(media_dir.glob("*"))) if media_dir.exists() else 0})
        except ValueError as ex:
            out.append({"slug": sj.parent.name, "name": sj.parent.name,
                        "tagline": f"INVALID JSON: {ex}", "media": 0, "media_files": 0})
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _file(self, path: Path, ctype=None):
        if not path.is_file():
            return self._json({"err": "not found"}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            return self._file(HERE / "kit.html", "text/html; charset=utf-8")
        if p == "/api/projects":
            return self._json({"projects": list_projects(),
                               "site_built": (SITE_DIR / "index.html").exists()})
        if p.startswith("/api/project/"):
            slug = p.rsplit("/", 1)[1]
            sj = PROJECTS_DIR / slug / "showcase.json"
            if not sj.is_file():
                return self._json({"err": "no such project"}, 404)
            return self._json({"slug": slug, "content": sj.read_text(encoding="utf-8")})
        if p == "/api/job":
            return self._json({"state": JOB["state"], "kind": JOB["kind"],
                               "log": list(JOB["log"])[-250:], "result": JOB["result"]})
        if p.startswith("/site/"):
            rel = p[len("/site/"):] or "index.html"
            target = (SITE_DIR / rel).resolve()
            if SITE_DIR.resolve() not in target.parents and target != SITE_DIR.resolve():
                return self._json({"err": "forbidden"}, 403)
            return self._file(target if target.suffix else target / "index.html")
        return self._json({"err": "not found"}, 404)

    def do_POST(self):
        try:
            p = self.path.split("?")[0]
            req = self._body()
            if p.startswith("/api/project/"):          # save showcase.json
                slug = p.rsplit("/", 1)[1]
                try:
                    parsed = json.loads(req.get("content", ""))
                except ValueError as ex:
                    return self._json({"err": f"invalid JSON: {ex}"}, 400)
                sj = PROJECTS_DIR / slug / "showcase.json"
                sj.parent.mkdir(parents=True, exist_ok=True)
                sj.write_text(json.dumps(parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                return self._json({"ok": True, "slug": slug})
            if p == "/api/probe":
                path = req.get("path", "").strip()
                if not Path(path).is_dir():
                    return self._json({"err": f"not a directory: {path}"}, 400)
                out = HERE / ".probe-cache.json"
                run_job("probe", [sys.executable, str(HERE / "probe.py"), path, "--out", str(out)])
                return self._json({"ok": True})
            if p == "/api/build":
                argv = [sys.executable, str(HERE / "build_site.py"),
                        "--projects", str(PROJECTS_DIR), "--out", str(SITE_DIR)]
                cfg = HERE / "portfolio.json"
                cfg_ex = HERE / "portfolio.json.example"
                argv += ["--config", str(cfg if cfg.exists() else cfg_ex)]
                if req.get("inline"):
                    argv.append("--inline")
                run_job("build", argv)
                return self._json({"ok": True})
            return self._json({"err": "not found"}, 404)
        except RuntimeError as ex:
            return self._json({"err": str(ex)}, 409)
        except Exception as ex:                        # noqa: BLE001
            return self._json({"err": str(ex)}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8778)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    url = f"http://127.0.0.1:{a.port}"
    print(f"showcase-kit web ui -> {url}")
    if not a.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
