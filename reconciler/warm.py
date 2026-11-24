#!/usr/bin/env python3
"""Load the models people use into the GPU before anyone asks (decision #81).

After a restart nothing is loaded, so the first voice or chat request waits for a model to come off disk
(7 seconds for the 4B, 30 to 40 for a 14B on the reference host). This sends each model an empty request,
which loads it and keeps it for the server's usual keep-alive, and skips any that are already loaded.

The models are the engine's `ha-voice` and `chat` roles from registry/engines.yaml, which are the pair that
fit together in video memory. `OLLAMA_WARM_MODELS` (space or comma separated Ollama tags) overrides that, and
an empty-but-set value turns warming off. Only Ollama engines are warmed.

  warm.py            load them now (what `novak warm` runs)
  warm.py --list     print the model tags, one per line
  warm.py --write    write $NOVAK_HOME/warm-models.txt, which the `warmup` container reads at boot
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROLES = ("ha-voice", "chat")


def home(env) -> Path:
    return Path(env.get("NOVAK_HOME") or Path.home() / ".novak")


def load_engines(env) -> list:
    import yaml
    for p in (home(env) / "registry" / "engines.yaml", Path(__file__).resolve().parent.parent / "registry" / "engines.yaml"):
        if p.is_file():
            return (yaml.safe_load(p.read_text()) or {}).get("engines") or []
    return []


def models_to_warm(env, engines=None) -> list[str]:
    if "OLLAMA_WARM_MODELS" in env:
        return list(dict.fromkeys(env["OLLAMA_WARM_MODELS"].replace(",", " ").split()))
    out = []
    for e in engines if engines is not None else load_engines(env):
        if "ollama" not in str(e.get("name", "")).lower():
            continue
        by_role = {m.get("role"): m.get("model") for m in e.get("models") or []}
        out += [by_role[r] for r in ROLES if by_role.get(r)]
    return list(dict.fromkeys(out))


def base_url(env) -> str:
    bind = env.get("OLLAMA_BIND") or "127.0.0.1"
    return f"http://{'127.0.0.1' if bind == '0.0.0.0' else bind}:{env.get('OLLAMA_PORT') or '11434'}"


def _call(url, body=None, timeout=300, opener=urllib.request.urlopen):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with opener(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def warm(url, models, out=print, opener=urllib.request.urlopen, clock=time.time) -> int:
    if not models:
        out("nothing to warm")
        return 0
    try:
        resident = {m.get("name") for m in _call(f"{url}/api/ps", opener=opener).get("models") or []}
    except Exception as exc:
        out(f"cannot reach Ollama at {url}: {exc}")
        return 1
    failed = 0
    for m in models:
        if m in resident:
            out(f"  {m}: already loaded")
            continue
        t0 = clock()
        try:
            _call(f"{url}/api/generate", {"model": m, "prompt": ""}, opener=opener)
            out(f"  {m}: loaded in {clock() - t0:.0f} s")
        except Exception as exc:
            failed += 1
            out(f"  {m}: FAILED ({exc})")
    return 1 if failed else 0


def main(argv=None, env=os.environ, out=print, opener=urllib.request.urlopen) -> int:
    ap = argparse.ArgumentParser(description="Load the resident models before anyone asks")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true")
    g.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    models = models_to_warm(env)
    if args.list:
        for m in models:
            out(m)
        return 0
    if args.write:
        target = home(env) / "warm-models.txt"
        target.write_text("".join(m + "\n" for m in models))
        return 0
    return warm(base_url(env), models, out, opener)


if __name__ == "__main__":
    sys.exit(main())
