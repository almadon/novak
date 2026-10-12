import json
import sys
import threading
import time
from pathlib import Path

from . import idle
from .api import ingest_file, make_server, parse_when
from .config import Settings, load_yaml
from .mcp import MCPClient
from .store import Store
from .worker import Worker


def build_gate(s):
    cfg = s.cfg["idle"]
    probe = (idle.ollama_probe(s.ollama_url, s.keep_alive_s)
             if cfg["probe"] == "ollama" else idle.always_idle_probe())
    return idle.IdleGate(probe, cfg["quiet_s"], cfg["poll_s"])


def watch_inbox(s, store, stop):
    """Files dropped in /data/inbox are ingested once they stop changing.
    An optional <name>.json beside a file may carry {source, recorded_at}."""
    inbox = s.data / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        for f in sorted(inbox.iterdir()):
            if f.suffix in (".json", ".part") or not f.is_file() or time.time() - f.stat().st_mtime < 5:
                continue
            side = f.with_name(f.name + ".json")
            meta = json.loads(side.read_text()) if side.exists() else {}
            try:
                when = parse_when(str(meta["recorded_at"])) if "recorded_at" in meta else int(f.stat().st_mtime)
                ingest_file(s, store, f, meta.get("source", "inbox"), when, f.name)
                f.unlink()
                side.unlink(missing_ok=True)
            except Exception as exc:
                print(f"inbox: {f.name}: {exc}", file=sys.stderr)
        stop.wait(s.cfg["inbox_poll_s"])


def serve():
    s = Settings.from_env()
    if not s.token:
        sys.exit("INGEST_TOKEN is not set; refusing to serve without one.")
    s.data.mkdir(parents=True, exist_ok=True)
    store, stop = Store(str(s.data / "ingest.db")), threading.Event()
    worker = Worker(s, store, build_gate(s), stop.is_set,
                    log=lambda m: print(m, file=sys.stderr, flush=True))

    def loop():
        while not stop.is_set():
            if not worker.run_once():
                stop.wait(10)

    threading.Thread(target=loop, daemon=True).start()
    threading.Thread(target=watch_inbox, args=(s, store, stop), daemon=True).start()
    make_server(s, store).serve_forever()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        serve()
    elif cmd == "check":  # validate registry/ingest.yaml without starting anything
        path = sys.argv[2] if len(sys.argv) > 2 else "registry/ingest.yaml"
        cfg = load_yaml(path)
        print(f"ok: {len(cfg['sinks'])} sink(s), idle probe {cfg['idle']['probe']}")
    elif cmd == "idle":  # what the idle probe sees right now
        s = Settings.from_env()
        gate = build_gate(s)
        last = gate.last_foreign_use()
        print("idle" if gate.is_idle() else "busy",
              "| last model use:", "never" if last is None else f"{time.time() - last:.0f}s ago",
              f"| quiet window {gate.quiet_s:.0f}s")
    elif cmd == "mcp-tools":  # verify a sink's tool names against the live server
        import os
        url, token = sys.argv[2], os.environ.get(sys.argv[3]) if len(sys.argv) > 3 else None
        for t in MCPClient(url, token).list_tools():
            props = (t.get("inputSchema") or {}).get("properties") or {}
            need = set((t.get("inputSchema") or {}).get("required") or [])
            args = ", ".join(f"{k}{'*' if k in need else ''}" for k in props)
            print(f"{t['name']}({args})")
            print("    " + (t.get("description") or "").strip().split("\n")[0][:110])
    else:
        sys.exit("usage: python -m novak_ingest serve | check [file] | idle | mcp-tools URL [TOKEN_ENV]  (names, with * marking required arguments)")


if __name__ == "__main__":
    main()
