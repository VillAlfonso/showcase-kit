#!/usr/bin/env python3
"""capsule.py -- a byte-exact TIME CAPSULE manifest for an entire project tree.

    python capsule.py C:/MyProject --out C:/MyProject-capsule

Walks every file, records path + size + mtime + SHA-256, and writes:
  manifest.jsonl.gz   one JSON line per file (the fingerprint of the whole tree)
  summary.json        totals per category, so you can see where the bytes live

Why this exists: you cannot compress high-entropy data (model weights, video,
PNGs) below its information content -- no archiver will ever turn 200 GB of
weights into a small file. What CAN be small is the *identity* of the tree.
This manifest is that identity. Restore strategy later:
  1. re-clone code from git, re-download models from their sources,
     restore your irreplaceable data from backup;
  2. run  capsule.py --verify manifest.jsonl.gz  against the rebuilt tree:
     every file that matches its hash is PROVEN bit-for-bit identical to today.

Categories are heuristics (edit CLASSIFY for your project): they don't change
what's recorded, only how the summary groups it.
"""
import argparse, gzip, hashlib, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CLASSIFY = [   # first match wins; patterns tested against the relative path (posix, lowercase)
    ("vcs",           lambda p: "/.git/" in p or p.startswith(".git/")),
    ("venv",          lambda p: "/.venv/" in p or p.startswith(".venv/") or "/site-packages/" in p),
    ("model_weights", lambda p: p.endswith((".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".onnx", ".bin"))
                                or "/models/" in p or "trainers/weights" in p),
    ("app_bundle",    lambda p: p.startswith(("comfyui_windows_portable/", "ace-step", "ltx-video"))),
    ("media_output",  lambda p: p.endswith((".mp4", ".webm", ".wav", ".mp3", ".flac", ".mov"))),
    ("images",        lambda p: p.endswith((".png", ".jpg", ".jpeg", ".webp"))),
    ("cache",         lambda p: "__pycache__" in p or "/cache/" in p or p.endswith((".pyc", ".log"))),
    ("code_and_data", lambda p: True),
]


def sha256(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def classify(rel):
    p = rel.replace("\\", "/").lower()
    for name, test in CLASSIFY:
        if test(p):
            return name
    return "other"


def walk(root):
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            yield Path(dp) / f


def build(root, out, do_hash, workers):
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    files = list(walk(root))
    total = len(files)
    print(f"indexed {total} files in {time.time()-t0:.0f}s; hashing={do_hash}", flush=True)

    cats, done, bytes_done = {}, 0, 0

    def entry(p):
        try:
            st = p.stat()
            rel = str(p.relative_to(root))
            e = {"p": rel, "s": st.st_size, "m": int(st.st_mtime)}
            if do_hash:
                e["h"] = sha256(p)
            e["c"] = classify(rel)
            return e
        except (OSError, PermissionError) as ex:
            return {"p": str(p), "err": str(ex)}

    mpath = out / "manifest.jsonl.gz"
    with gzip.open(mpath, "wt", encoding="utf-8") as gz, ThreadPoolExecutor(max_workers=workers) as ex:
        for e in ex.map(entry, files, chunksize=64):
            gz.write(json.dumps(e, ensure_ascii=False) + "\n")
            done += 1
            if "s" in e:
                c = cats.setdefault(e.get("c", "other"), [0, 0])
                c[0] += 1
                c[1] += e["s"]
                bytes_done += e["s"]
            if done % 5000 == 0:
                print(f"  {done}/{total} files, {bytes_done/2**30:.1f} GiB, {time.time()-t0:.0f}s", flush=True)

    summary = {
        "root": str(root), "files": total, "bytes": bytes_done,
        "gib": round(bytes_done / 2**30, 2), "hashed": do_hash,
        "seconds": round(time.time() - t0, 1),
        "categories": {k: {"files": v[0], "gib": round(v[1] / 2**30, 2)} for k, v in
                       sorted(cats.items(), key=lambda kv: -kv[1][1])},
        "manifest": str(mpath),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print("DONE", flush=True)


def verify(root, manifest):
    ok = bad = missing = 0
    with gzip.open(manifest, "rt", encoding="utf-8") as gz:
        for line in gz:
            e = json.loads(line)
            if "h" not in e:
                continue
            p = root / e["p"]
            if not p.exists():
                missing += 1
                print(f"MISSING {e['p']}")
            elif sha256(p) == e["h"]:
                ok += 1
            else:
                bad += 1
                print(f"CHANGED {e['p']}")
    print(f"verify: {ok} identical, {bad} changed, {missing} missing")


def main():
    ap = argparse.ArgumentParser(description="Byte-exact manifest (time capsule) of a project tree.")
    ap.add_argument("path")
    ap.add_argument("--out", default=None, help="output dir (default <path>-capsule beside it)")
    ap.add_argument("--no-hash", action="store_true", help="sizes/paths only (fast inventory)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--verify", default=None, help="manifest.jsonl.gz to verify PATH against")
    a = ap.parse_args()
    root = Path(a.path).resolve()
    if a.verify:
        verify(root, Path(a.verify))
        return
    out = Path(a.out) if a.out else root.parent / (root.name + "-capsule")
    build(root, out, not a.no_hash, a.workers)


if __name__ == "__main__":
    main()
