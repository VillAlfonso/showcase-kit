#!/usr/bin/env python3
"""probe.py -- gather mechanical facts about a codebase to seed a showcase.json.

Usage:  python probe.py [path] [--out showcase/probe.json]

Pure standard library. Prints JSON to stdout and writes it to --out.
Never prints file contents or secrets -- only counts, names and paths.
"""
import argparse, datetime, json, os, re, subprocess, sys
from collections import Counter
from pathlib import Path

IGNORE = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist",
          "build", ".next", "out", ".cache", "target", "vendor", ".idea",
          ".vscode", "coverage", ".pytest_cache", "site", ".turbo", ".parcel-cache"}
EXT_LANG = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
            ".ts": "TypeScript", ".tsx": "TypeScript", ".rb": "Ruby", ".go": "Go",
            ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".php": "PHP", ".c": "C",
            ".h": "C", ".cpp": "C++", ".cc": "C++", ".cs": "C#", ".swift": "Swift",
            ".css": "CSS", ".scss": "SCSS", ".html": "HTML", ".vue": "Vue",
            ".svelte": "Svelte", ".sh": "Shell", ".sql": "SQL", ".md": "Markdown",
            ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML"}
CODE = {"Python", "JavaScript", "TypeScript", "Ruby", "Go", "Rust", "Java", "Kotlin",
        "PHP", "C", "C++", "C#", "Swift", "Vue", "Svelte", "CSS", "SCSS", "HTML",
        "Shell", "SQL"}
SCAN_EXT = {".py", ".js", ".jsx", ".mjs", ".ts", ".tsx"}


def sh(args, cwd):
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                              timeout=25).stdout.strip()
    except Exception:
        return ""


def git_facts(root):
    if not (root / ".git").exists():
        return {}
    g = lambda *a: sh(["git", *a], root)
    remote = g("config", "--get", "remote.origin.url")
    remote = re.sub(r"^git@([^:]+):", r"https://\1/", remote)
    if remote.endswith(".git"):
        remote = remote[:-4]
    count = g("rev-list", "--count", "HEAD")
    first = ""
    if count:
        log = sh(["git", "log", "--reverse", "--format=%ad", "--date=short"], root)
        first = log.split("\n")[0] if log else ""
    return {"remote": remote or None,
            "commits": int(count) if count.isdigit() else None,
            "first_commit": first or None,
            "last_commit": g("log", "-1", "--format=%ad", "--date=short") or None,
            "branch": g("rev-parse", "--abbrev-ref", "HEAD") or None}


def list_files(root):
    tracked = sh(["git", "ls-files"], root)
    if tracked:
        return [root / l for l in tracked.split("\n") if l.strip()]
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in IGNORE and not d.startswith(".")]
        for f in fn:
            out.append(Path(dp) / f)
    return out


def count_lines(p):
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for _ in fh)
    except Exception:
        return 0


def languages(files):
    lines, nfiles = Counter(), Counter()
    for f in files:
        lang = EXT_LANG.get(f.suffix.lower())
        if lang:
            lines[lang] += count_lines(f)
            nfiles[lang] += 1
    code_total = sum(v for k, v in lines.items() if k in CODE) or 1
    top = [{"language": k, "lines": v, "files": nfiles[k], "pct": round(100 * v / code_total, 1)}
           for k, v in lines.most_common() if k in CODE]
    return {"by_language": top,
            "code_lines": sum(v for k, v in lines.items() if k in CODE),
            "total_files": len(files)}


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}


def manifests(root):
    out = {}
    if (root / "package.json").exists():
        d = read_json(root / "package.json")
        out["package.json"] = {"name": d.get("name"), "description": d.get("description"),
                               "scripts": list((d.get("scripts") or {}).keys()),
                               "deps": list((d.get("dependencies") or {}).keys())[:30],
                               "homepage": d.get("homepage")}
    if (root / "pyproject.toml").exists():
        t = (root / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
        nm = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)', t)
        ds = re.search(r'(?m)^\s*description\s*=\s*["\']([^"\']+)', t)
        out["pyproject.toml"] = {"name": nm.group(1) if nm else None,
                                 "description": ds.group(1) if ds else None}
    for f in ["requirements.txt", "Cargo.toml", "go.mod", "Gemfile", "pom.xml",
              "composer.json", "Dockerfile", "docker-compose.yml", "Makefile", "manage.py"]:
        if (root / f).exists():
            out.setdefault("files", []).append(f)
    return out


def grep(code_files, needle):
    for f in code_files[:5000]:
        try:
            if needle in f.read_text(encoding="utf-8", errors="ignore").lower():
                return True
        except Exception:
            pass
    return False


def detect_type(root, mani, code_files):
    deps = set((mani.get("package.json") or {}).get("deps") or [])
    if "next" in deps:
        return "web app (Next.js)"
    if {"react", "react-dom"} & deps:
        return "web app (React)"
    if "vue" in deps:
        return "web app (Vue)"
    if "svelte" in deps:
        return "web app (Svelte)"
    if {"express", "koa", "fastify"} & deps:
        return "backend / API (Node)"
    if (root / "manage.py").exists():
        return "web app (Django)"
    if grep(code_files, "fastapi"):
        return "backend / API (FastAPI)"
    if grep(code_files, "flask"):
        return "backend / API (Flask)"
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "library / tool (Python)"
    if deps:
        return "JavaScript project"
    return "unknown"


def run_commands(root, mani, code_files):
    cmds = []
    for s in (mani.get("package.json") or {}).get("scripts") or []:
        if s in ("dev", "start", "serve", "build", "preview"):
            cmds.append(f"npm run {s}")
    if (root / "Makefile").exists():
        cmds.append("make")
    if (root / "docker-compose.yml").exists():
        cmds.append("docker compose up")
    if grep(code_files, "uvicorn") or grep(code_files, "fastapi"):
        cmds.append("uvicorn <app>:app  (see README)")
    if (root / "manage.py").exists():
        cmds.append("python manage.py runserver")
    return list(dict.fromkeys(cmds))


ROUTE_PATS = [r'@(?:app|router)\.(?:get|post|put|delete|patch)\(\s*["\']([^"\']+)',
              r'app\.(?:get|post|put|delete|patch)\(\s*["\']([^"\']+)',
              r'<Route[^>]*path=["\']([^"\']+)']


def routes(code_files):
    found = set()
    for f in code_files[:4000]:
        if len(found) > 60:
            break
        try:
            t = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in ROUTE_PATS:
            for m in re.findall(pat, t):
                found.add(m)
    return sorted(found)[:60]


def readme(root):
    for name in ["README.md", "readme.md", "Readme.md", "README.rst", "README.txt"]:
        p = root / name
        if p.exists():
            title = ""
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("#"):
                    title = line.strip("# ").strip()
                    break
            return {"path": name, "title": title or None}
    return {}


def main():
    ap = argparse.ArgumentParser(description="Gather mechanical facts about a codebase.")
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--out", default="showcase/probe.json")
    a = ap.parse_args()
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    root = Path(a.path).resolve()
    files = list_files(root)
    code_files = [f for f in files if f.suffix.lower() in SCAN_EXT]
    mani = manifests(root)
    facts = {
        "name_guess": (mani.get("package.json") or {}).get("name")
                      or (mani.get("pyproject.toml") or {}).get("name") or root.name,
        "root": str(root),
        "git": git_facts(root),
        "languages": languages(files),
        "project_type": detect_type(root, mani, code_files),
        "run_commands": run_commands(root, mani, code_files),
        "routes": routes(code_files),
        "manifests": mani,
        "readme": readme(root),
        "probed_at": datetime.date.today().isoformat(),
    }
    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(facts, indent=2, ensure_ascii=False), encoding="utf-8")
    json.dump(facts, sys.stdout, indent=2, ensure_ascii=False)
    print()
    print(f"# wrote {outp}", file=sys.stderr)


if __name__ == "__main__":
    main()
