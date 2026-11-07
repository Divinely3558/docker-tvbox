#!/usr/bin/env python3
"""Sweep every csp_ jar site in a TVBox config through the dex->JVM runner.

Usage: python3 spider-runtime/sweep.py <config.json> [--method homeContent] [--limit N] [--timeout S]
Prints one row per site: class | ok | payload summary | first error line.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

RUNTIME = Path(__file__).resolve().parent


def ext_to_str(ext):
    if ext is None:
        return ""
    if isinstance(ext, str):
        return ext
    if isinstance(ext, list):
        parts = []
        for e in ext:
            if isinstance(e, dict):
                parts.append(e.get("api") or e.get("url") or json.dumps(e, ensure_ascii=False))
            else:
                parts.append(str(e))
        return "|".join(parts) if len(parts) > 1 else json.dumps(ext[0], ensure_ascii=False)
    return json.dumps(ext, ensure_ascii=False)


def defaults(method):
    return {"homeContent": [True], "categoryContent": ["1", "1", True, {}],
            "detailContent": [["1"]], "searchContent": ["天下", False],
            "homeVideoContent": [], "liveContent": []}.get(method, [])


def summarize(resp):
    if not resp.get("ok"):
        return None, (resp.get("error") or "").split("\\n")[0][:120]
    r = resp.get("result")
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except Exception:
            return f"str:{len(r)}", None
    if isinstance(r, dict):
        if "class" in r:
            return f"cat:{len(r.get('class') or [])} list:{len(r.get('list') or [])} filt:{len(r.get('filters') or {})}", None
        if "list" in r:
            items = r["list"] or []
            names = "/".join(str(i.get("vod_name") or i.get("name") or "?") for i in items[:3])
            return f"list:{len(items)} {names[:60]}", None
        if "url" in r:
            return f"play:{str(r.get('url'))[:70]}", None
        return f"dict:{list(r)[:5]}", None
    if isinstance(r, list):
        return f"arr:{len(r)}", None
    return f"{r!r}"[:70], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--method", default="homeContent")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--jar", default=str(Path.home() / "tools/spike/work/spider.jar"))
    ap.add_argument("--args", help="JSON array of method arguments; overrides --method defaults")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    reqs = []
    for s in cfg.get("sites", []):
        if s.get("type") != 3:
            continue
        api = s.get("api") or ""
        if not api.startswith("csp_"):
            continue
        payload = {"api": api, "ext": ext_to_str(s.get("ext")), "method": args.method,
                   "args": json.loads(args.args) if args.args else defaults(args.method)}
        payload["fresh"] = True
        reqs.append(payload)
    if args.limit:
        reqs = reqs[:args.limit]

    proc = subprocess.Popen(["bash", str(RUNTIME / "run.sh")], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            env={**os.environ, "JAR": args.jar})
    payload_in = "".join(json.dumps({**r, "id": i}, ensure_ascii=False) + "\n" for i, r in enumerate(reqs))

    def feed():
        proc.stdin.write(payload_in)
        proc.stdin.flush()
        proc.stdin.close()

    threading.Thread(target=feed, daemon=True).start()

    ok = fail = 0
    done = {}
    deadline = args.timeout * len(reqs)
    t0 = time.time()
    while len(done) < len(reqs) and time.time() - t0 < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            resp = json.loads(line)
        except Exception:
            continue
        if resp.get("ready"):
            continue
        i = resp.get("id")
        if i is None or i in done:
            continue
        done[i] = resp
        r = reqs[i]
        note, err = summarize(resp)
        if err is None:
            ok += 1
            print(f"  OK   {r['api']:<22} {note}", flush=True)
        else:
            fail += 1
            print(f"  FAIL {r['api']:<22} {err}", flush=True)
    proc.kill()
    missing = len(reqs) - len(done)
    print(f"\n{args.method}: {ok} ok / {fail} fail" + (f" / {missing} timeout" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
