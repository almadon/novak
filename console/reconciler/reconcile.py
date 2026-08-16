#!/usr/bin/env python3
"""
Applies registry/mcp-servers.yaml to the running stack.

This is the only component with control over containers, and it is deliberately
dumb: it reads a file, validates it strictly, renders a compose override, and
runs `docker compose`. It has no network listener and never sees an HTTP
request, so a compromise of the web console cannot reach it directly — the
worst an attacker with console access can do is write a registry file that
still has to survive the validation below.

Invariants worth preserving if you edit this:
  * No shell. Every subprocess call uses list form, never shell=True.
  * No interpolation of registry values into strings that get executed.
  * Fail closed: any validation error aborts the whole run; a partially
    applied registry is worse than a stale one.
  * Secrets are never read here. `env` carries variable NAMES; the values are
    resolved by docker compose from the host environment at up-time.

Usage:
    ./reconcile.py [--dry-run]

Requires PyYAML:  pip3 install --user pyyaml
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required:  pip3 install --user pyyaml")

CONSOLE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = CONSOLE_DIR.parent
REGISTRY = CONSOLE_DIR / "registry" / "mcp-servers.yaml"
OUTPUT = REPO_DIR / "docker-compose.mcp.yml"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$")
ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9._/:@-]+$")


class ValidationError(Exception):
    pass


def validate(entry: dict, seen_names: set[str], seen_ports: set[int]) -> dict:
    def req(key: str):
        if key not in entry:
            raise ValidationError(f"missing required key {key!r}")
        return entry[key]

    name = req("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValidationError(f"invalid name {name!r} (expected ^[a-z0-9][a-z0-9-]*[a-z0-9]$)")
    if name in seen_names:
        raise ValidationError(f"duplicate name {name!r}")

    image = req("image")
    if not isinstance(image, str) or not IMAGE_RE.match(image):
        raise ValidationError(f"[{name}] invalid image {image!r}")

    port = req("port")
    if not isinstance(port, int) or isinstance(port, bool) or not (1024 <= port <= 65535):
        raise ValidationError(f"[{name}] port must be an int in 1024-65535, got {port!r}")
    if port in seen_ports:
        raise ValidationError(f"[{name}] duplicate port {port}")

    enabled = req("enabled")
    if not isinstance(enabled, bool):
        raise ValidationError(f"[{name}] enabled must be true/false, got {enabled!r}")

    command = entry.get("command")
    if command is not None:
        if not isinstance(command, str):
            raise ValidationError(f"[{name}] command must be a string")
        # YAML folded scalars (`>`) leave a trailing newline; compose treats the
        # string verbatim, so normalise whitespace here.
        command = " ".join(command.split()) or None

    env = entry.get("env", [])
    if not isinstance(env, list) or not all(isinstance(e, str) and ENV_RE.match(e) for e in env):
        raise ValidationError(f"[{name}] env must be a list of UPPER_SNAKE variable names")

    seen_names.add(name)
    seen_ports.add(port)
    return {
        "name": name, "image": image, "port": port,
        "enabled": enabled, "command": command, "env": env,
    }


def render(servers: list[dict]) -> dict:
    services = {}
    for s in servers:
        if not s["enabled"]:
            continue
        svc = {
            "image": s["image"],
            "restart": "unless-stopped",
            "ports": [f"{s['port']}:8000"],
        }
        if s["command"]:
            svc["command"] = s["command"]
        if s["env"]:
            # Values resolved by compose from the host env at up-time; the
            # reconciler never reads them.
            svc["environment"] = {k: f"${{{k}}}" for k in s["env"]}
        services[f"{s['name']}-mcp"] = svc
    return {"name": "novak", "services": services}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and render, but do not apply")
    args = ap.parse_args()

    if not REGISTRY.exists():
        sys.exit(f"registry not found: {REGISTRY}")

    doc = yaml.safe_load(REGISTRY.read_text()) or {}
    entries = doc.get("servers")
    if not isinstance(entries, list):
        sys.exit("registry: top-level 'servers' must be a list")

    seen_names: set[str] = set()
    seen_ports: set[int] = set()
    servers = []
    try:
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValidationError(f"entry must be a mapping, got {type(entry).__name__}")
            servers.append(validate(entry, seen_names, seen_ports))
    except ValidationError as e:
        sys.exit(f"registry validation failed: {e}")

    rendered = yaml.safe_dump(render(servers), sort_keys=False)
    header = (
        "# GENERATED by console/reconciler/reconcile.py — do not edit.\n"
        "# Source of truth: console/registry/mcp-servers.yaml\n"
    )

    enabled = [s["name"] for s in servers if s["enabled"]]
    disabled = [s["name"] for s in servers if not s["enabled"]]
    print(f"enabled:  {', '.join(enabled) or '(none)'}")
    print(f"disabled: {', '.join(disabled) or '(none)'}")

    if args.dry_run:
        print(f"\n--- would write {OUTPUT} ---\n{header}{rendered}")
        return 0

    OUTPUT.write_text(header + rendered)
    print(f"wrote {OUTPUT}")

    subprocess.run(
        ["docker", "compose",
         "-f", str(REPO_DIR / "docker-compose.yml"),
         "-f", str(OUTPUT),
         "up", "-d", "--remove-orphans"],
        cwd=REPO_DIR, check=True, env=os.environ,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
