#!/usr/bin/env python3
"""showcase-kit MCP server -- lets any MCP client (Claude Code, Claude
Desktop, ...) drive the portfolio kit: probe a codebase for facts, read and
write showcase.json entries, and build the portfolio site.

Wire into Claude Code (.mcp.json):
    {"mcpServers": {"showcase": {"command": "python",
                                 "args": ["C:/Users/USER/showcase-kit/kit_mcp.py"]}}}

Protocol: MCP over stdio (newline-delimited JSON-RPC 2.0). Stdlib only.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
PROJECTS_DIR = HERE / "examples"
SITE_DIR = HERE / "site"


# ------------------------------------------------------------------ tools ----
def t_probe(args):
    path = args["path"]
    out = HERE / ".probe-cache.json"
    r = subprocess.run([sys.executable, str(HERE / "probe.py"), path, "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "probe failed")
    return out.read_text(encoding="utf-8")


def t_list(args):
    rows = []
    for sj in sorted(PROJECTS_DIR.glob("*/showcase.json")):
        try:
            d = json.loads(sj.read_text(encoding="utf-8"))
            rows.append({"slug": d.get("slug", sj.parent.name), "name": d.get("name"),
                         "tagline": d.get("tagline"), "media": len(d.get("media", [])),
                         "featured": bool(d.get("featured"))})
        except ValueError:
            rows.append({"slug": sj.parent.name, "error": "invalid JSON"})
    return json.dumps({"projects": rows, "projects_dir": str(PROJECTS_DIR),
                       "site_built": (SITE_DIR / "index.html").exists()}, indent=1)


def t_read(args):
    sj = PROJECTS_DIR / args["slug"] / "showcase.json"
    if not sj.is_file():
        raise RuntimeError(f"no project '{args['slug']}' (looked at {sj})")
    return sj.read_text(encoding="utf-8")


def t_write(args):
    parsed = json.loads(args["content"])               # validate before touching disk
    slug = args["slug"]
    sj = PROJECTS_DIR / slug / "showcase.json"
    sj.parent.mkdir(parents=True, exist_ok=True)
    sj.write_text(json.dumps(parsed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"saved {sj} ({len(parsed.get('media', []))} media entries)"


def t_build(args):
    cfg = HERE / "portfolio.json"
    argv = [sys.executable, str(HERE / "build_site.py"), "--projects", str(PROJECTS_DIR),
            "--out", str(SITE_DIR), "--config",
            str(cfg if cfg.exists() else HERE / "portfolio.json.example")]
    if args.get("inline"):
        argv.append("--inline")
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=900, cwd=str(HERE))
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        raise RuntimeError(out or "build failed")
    return out + f"\n\nsite -> {SITE_DIR / 'index.html'} (preview: python kit_web.py, then /site/)"


TOOLS = {
    "showcase_probe": {
        "description": ("Gather mechanical facts about any codebase: languages + LOC, project type, "
                        "git history, API routes, run commands, dependency manifests. Returns JSON. "
                        "This is step 1 of writing a portfolio entry."),
        "schema": {"type": "object", "properties": {"path": {"type": "string",
                   "description": "absolute path of the codebase to probe"}}, "required": ["path"]},
        "fn": t_probe},
    "showcase_list": {
        "description": "List every portfolio project entry (slug, name, tagline, media count) and whether the site is built.",
        "schema": {"type": "object", "properties": {}},
        "fn": t_list},
    "showcase_read": {
        "description": "Read a project's showcase.json (the full portfolio entry).",
        "schema": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
        "fn": t_read},
    "showcase_write": {
        "description": ("Create or overwrite a project's showcase.json. Content must be the COMPLETE "
                        "JSON entry (validated before writing). Media files referenced by it belong in "
                        "examples/<slug>/media/."),
        "schema": {"type": "object", "properties": {
            "slug": {"type": "string"}, "content": {"type": "string", "description": "the full showcase.json text"}},
            "required": ["slug", "content"]},
        "fn": t_write},
    "showcase_build": {
        "description": "Build the portfolio site from every entry (merges all showcase.json + copies media -> site/index.html). Set inline=true to embed media as data URIs (single huge file).",
        "schema": {"type": "object", "properties": {"inline": {"type": "boolean"}}},
        "fn": t_build},
}


# ------------------------------------------------------------------ rpc ------
def _send(obj):
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def serve():
    for raw in sys.stdin.buffer:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        mid, method = msg.get("id"), msg.get("method", "")
        params = msg.get("params") or {}
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "showcase-kit", "version": "2.0"}}})
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [
                {"name": k, "description": v["description"], "inputSchema": v["schema"]}
                for k, v in TOOLS.items()]}})
        elif method == "tools/call":
            tool = TOOLS.get(params.get("name", ""))
            if not tool:
                _send({"jsonrpc": "2.0", "id": mid,
                       "error": {"code": -32602, "message": f"unknown tool {params.get('name')}"}})
                continue
            try:
                text = tool["fn"](params.get("arguments") or {})
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": text}], "isError": False}})
            except Exception as ex:                    # noqa: BLE001
                _send({"jsonrpc": "2.0", "id": mid, "result": {
                    "content": [{"type": "text", "text": f"error: {ex}"}], "isError": True}})
        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid,
                   "error": {"code": -32601, "message": f"method not found: {method}"}})


if __name__ == "__main__":
    serve()
