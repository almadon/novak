#!/usr/bin/env python3
"""Write the credentials the gateway needs, and only those, to gateway.env.

The gateway holds each person's backend credentials so no client has to. It
should hold exactly the ones its directory refers to, not every secret in
.env, so up.sh runs this after secrets are loaded into the environment and
compose passes the resulting file to that one container. The file is mode 600.
Names come from the registry's `auth:` fields for entries listed under people
or household, plus the gateway's own settings.
"""
import os
import sys
from pathlib import Path

import yaml

NOVAK_HOME = Path(os.environ.get("NOVAK_HOME", Path.home() / ".novak"))
PLACEHOLDERS = {"", "set-in-keychain", "EDIT-ME", "changeme"}
OWN = ["GATEWAY_HA_TOKEN"]


def needed_names(registry_dir: Path) -> list[str]:
    def load(f):
        p = registry_dir / f
        return (yaml.safe_load(p.read_text()) or {}) if p.exists() else {}
    people = load("people.yaml")
    wanted = set((people.get("household") or {}).get("entries") or [])
    for person in (people.get("people") or {}).values():
        wanted |= set((person or {}).get("entries") or [])
    names = {e["auth"] for e in load("mcp-servers.yaml").get("servers") or []
             if e.get("name") in wanted and e.get("auth")}
    return sorted(names | set(OWN))


def main() -> int:
    names = needed_names(NOVAK_HOME / "registry")
    lines, missing = [], []
    for n in names:
        v = os.environ.get(n, "")
        if v in PLACEHOLDERS:
            missing.append(n)
        else:
            lines.append(f"{n}={v}")
    target = NOVAK_HOME / "gateway.env"
    target.write_text("\n".join(lines) + ("\n" if lines else ""))
    target.chmod(0o600)
    if missing:
        print("gateway: no value yet for " + ", ".join(missing)
              + " (those entries will report 'credential not set')", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
