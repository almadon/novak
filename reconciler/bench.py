#!/usr/bin/env python3
"""Measure what a person feels in Open WebUI: how long until the first word, and how fast the rest comes (decision #81).

`novak bench` calls this. It sends a realistic request (the persona and tool rules as a system prompt, then a
short question) through the router, the same path Open WebUI uses, and reports for each role and prompt size
the time to first token, the speed after that, and, when run on the host that has the GPU, how busy the GPU and
CPU were and how much video memory was used. Run it before and after a change to Ollama's settings or a model.

It does not unload anything unless you ask (`--cold`), so on a live system it only adds the load of the
requests themselves.

  bench.py [--roles chat,code,task] [--sizes 0,1,3] [--max-tokens 140] [--cold]
  --sizes: how many blocks of filler to add to the prompt (0 is about 2,000 tokens, each block about 1,000 more)
  --cold:  unload the roles' models first, so the first line includes loading them from disk
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROMPT_FILES = ("novak-chat.md", "novak-tools.md", "novak-house.md")
QUESTION = "In two or three sentences, what can you help me with in my house today?"
FILLER = "Reference notes: the kitchen has a bar light, a relay and a counter strip. " * 60
DRM = "/sys/class/drm/card0/device/"


def system_prompt(blocks: int) -> str:
    base = "\n\n".join((REPO / "prompts" / f).read_text() for f in PROMPT_FILES if (REPO / "prompts" / f).is_file())
    return base + ("\n\n" + FILLER * blocks if blocks else "")


def gpu_sample():
    try:
        return (int(Path(DRM + "gpu_busy_percent").read_text()),
                int(Path(DRM + "mem_info_vram_used").read_text()) / 2 ** 30)
    except (OSError, ValueError):
        return None, None


def cpu_times():
    v = list(map(int, Path("/proc/stat").read_text().splitlines()[0].split()[1:]))
    return v[3] + v[4], sum(v)


class Sampler(threading.Thread):
    """Watches GPU busy, video memory and CPU every half second while a request runs. Quiet where it cannot."""

    def __init__(self, interval=0.5):
        super().__init__(daemon=True)
        self.interval, self.halt, self.gpu, self.cpu, self.vram = interval, False, [], [], []

    def run(self):
        try:
            i0, t0 = cpu_times()
        except OSError:
            i0 = t0 = None
        while not self.halt:
            time.sleep(self.interval)
            busy, vram = gpu_sample()
            if busy is not None:
                self.gpu.append(busy)
                self.vram.append(vram)
            if t0 is not None:
                i1, t1 = cpu_times()
                if t1 > t0:
                    self.cpu.append(100 * (1 - (i1 - i0) / (t1 - t0)))
                i0, t0 = i1, t1


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def ask(url, key, model, blocks, max_tokens, opener=urllib.request.urlopen, sampler=Sampler, clock=time.time):
    """One streamed request. Returns a dict of measurements, or {'error': text}."""
    body = {"model": model, "stream": True, "stream_options": {"include_usage": True}, "max_tokens": max_tokens,
            "temperature": 0.2, "messages": [{"role": "system", "content": system_prompt(blocks)},
                                             {"role": "user", "content": QUESTION}]}
    req = urllib.request.Request(f"{url}/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    s = sampler()
    s.start()
    t0, first, pieces, usage = clock(), None, 0, {}
    try:
        with opener(req, timeout=900) as r:
            for raw in r:
                line = raw.decode().strip()
                if not line.startswith("data:") or line.endswith("[DONE]"):
                    continue
                d = json.loads(line[5:])
                usage = d.get("usage") or usage
                ch = d.get("choices") or []
                if ch and (ch[0].get("delta") or {}).get("content"):
                    first = first or clock()
                    pieces += 1
    except Exception as exc:
        s.halt = True
        return {"error": str(exc)[:120]}
    t1 = clock()
    s.halt = True
    time.sleep(s.interval + 0.1)
    n = usage.get("completion_tokens") or pieces
    gen = max(t1 - (first or t0), 1e-6)
    return {"prompt": usage.get("prompt_tokens", 0), "ttft": (first or t1) - t0, "tokens": n, "rate": n / gen,
            "total": t1 - t0, "gpu": mean(s.gpu), "gpu_max": max(s.gpu) if s.gpu else None,
            "cpu": mean(s.cpu), "vram": max(s.vram) if s.vram else None}


def line(label, r) -> str:
    if "error" in r:
        return f"{label:20} ERROR {r['error']}"
    extra = ""
    if r["gpu"] is not None:
        extra = f"  gpu {r['gpu']:3.0f}% (max {r['gpu_max']:3.0f}%)  vram {r['vram']:4.1f} GB"
    if r["cpu"] is not None:
        extra += f"  cpu {r['cpu']:3.0f}%"
    return (f"{label:20} prompt {r['prompt']:5}  first token {r['ttft']:5.1f} s  {r['tokens']:4} tokens "
            f"at {r['rate']:5.1f}/s  total {r['total']:5.1f} s{extra}")


def unload(ollama_url, model, opener=urllib.request.urlopen):
    req = urllib.request.Request(f"{ollama_url}/api/generate", json.dumps({"model": model, "keep_alive": 0}).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with opener(req, timeout=60) as r:
            r.read()
    except Exception:
        pass


def main(argv=None, env=os.environ, out=print, opener=urllib.request.urlopen, sampler=Sampler) -> int:
    ap = argparse.ArgumentParser(description="Time to first token and speed through the router, per role and prompt size")
    ap.add_argument("--roles", default="chat,code,task")
    ap.add_argument("--sizes", default="0,1,3", help="blocks of filler to add (0 is about 2,000 tokens)")
    ap.add_argument("--max-tokens", type=int, default=140)
    ap.add_argument("--cold", action="store_true", help="unload each role's model first (disturbs anyone using it)")
    ap.add_argument("--url", help="router base URL (default from ROUTER_BIND and ROUTER_PORT)")
    args = ap.parse_args(argv)
    key = env.get("ROUTER_API_KEY", "")
    if not key:
        print("ROUTER_API_KEY is not set (novak bench reads it from the secret store)", file=sys.stderr)
        return 2
    host = env.get("ROUTER_BIND") or env.get("HOST_NAME") or "127.0.0.1"
    url = (args.url or f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{env.get('ROUTER_PORT') or '13402'}/v1").rstrip("/")
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    sizes = [int(x) for x in args.sizes.split(",") if x.strip()]
    failures = 0
    out(f"Benchmark through {url}")
    for role in roles:
        if args.cold:
            from warm import base_url, load_engines
            for e in load_engines(env):
                for m in e.get("models") or []:
                    if m.get("role") == role:
                        unload(base_url(env), m["model"], opener)
        for i, blocks in enumerate(sizes):
            label = f"{role}{' (cold)' if args.cold and i == 0 else ''} +{blocks}"
            r = ask(url, key, role, blocks, args.max_tokens, opener, sampler)
            failures += "error" in r
            out(line(label, r))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
