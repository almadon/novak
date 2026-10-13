import os
import sys
import time
from pathlib import Path

from . import directory
from .approvals import Approvals
from .audit import Audit
from .auth import OIDC
from .server import make_server
from .service import Gateway


def build():
    env = os.environ
    data, reg = Path(env.get("GATEWAY_DATA", "/data")), Path(env.get("GATEWAY_REGISTRY", "/registry"))
    data.mkdir(parents=True, exist_ok=True)
    public = env.get("GATEWAY_PUBLIC_URL", "http://localhost:13410")
    gw = Gateway(reg, Audit(str(data / "audit.db")), Approvals(str(data / "approvals.db")), public)
    oidc_cfg = gw.dir.settings.get("oidc") or {}
    issuer = env.get("GATEWAY_OIDC_ISSUER") or oidc_cfg.get("issuer", "")
    audience = env.get("GATEWAY_OIDC_AUDIENCE") or oidc_cfg.get("audience", f"{public}/mcp")
    oidc = OIDC(issuer, audience, gw.dir.settings.get("username_claim", "preferred_username")) if issuer else None
    return gw, oidc


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        gw, oidc = build()
        for p in directory.validate(gw.dir):
            print(f"warning: {p}", file=sys.stderr, flush=True)
        print(f"gateway: {len(gw.dir.people)} people, {len(gw.dir.entries)} entries, "
              f"oidc {'on' if oidc else 'off'}", file=sys.stderr, flush=True)
        make_server(gw, oidc).serve_forever()
    elif cmd == "check":     # validate the directory without starting anything
        reg = Path(sys.argv[2] if len(sys.argv) > 2 else os.environ.get("GATEWAY_REGISTRY", "/registry"))
        d = directory.load(reg)
        problems = directory.validate(d)
        print(f"{len(d.people)} people, {len(d.entries)} entries, household {d.household_entries}")
        for p in problems:
            print(f"problem: {p}")
        sys.exit(1 if problems else 0)
    elif cmd == "audit":     # recent accounting, optionally for one person
        who = sys.argv[2] if len(sys.argv) > 2 else None
        a = Audit(str(Path(os.environ.get("GATEWAY_DATA", "/data")) / "audit.db"))
        for r in reversed(a.recent(who, 40)):
            when = time.strftime("%m-%d %H:%M:%S", time.localtime(r["ts"]))
            print(f"{when} {r['person']:10} {r['via']:16} {r['entry'] or '-':22} {r['tool'] or '-':28} "
                  f"{r['kind'] or '-':11} {r['decision']:9} {r['outcome'] or ''}")
    else:
        sys.exit("usage: python -m novak_gateway serve | check [registry-dir] | audit [person]")


if __name__ == "__main__":
    main()
