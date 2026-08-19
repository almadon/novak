#!/usr/bin/env python3
"""
Applies registry/mcp-servers.yaml to the running stack.

This is the only component with control over containers, and it is deliberately
dumb: it reads a file, validates it strictly, renders a compose override, and
runs `docker compose`. It has no network listener and never sees an HTTP
request, so a compromise of the console cannot reach it directly — the worst an
attacker with console access can do is write a registry file that still has to
survive the validation below.

The console lives in its own repository and writes this registry over a bind
mount. That is the whole interface between them: a file on disk, validated
here, with git as the audit log. The console is deliberately not required —
editing the YAML by hand and running this script is a fully supported path.

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

REPO_DIR = Path(__file__).resolve().parent.parent

# Runtime state lives outside the git checkout so the repo is never written to
# and `git pull` never conflicts with a running deployment. NOVAK_HOME holds
# config (.env), per-deployment config (the registry), user data (wakeword
# models) and generated files.
NOVAK_HOME = Path(os.environ.get("NOVAK_HOME", Path.home() / ".novak"))

# Fall back to the repo's copy when there is no deployment — that is how CI
# validates the checked-in registry, and how --dry-run works before install.
_deployed = NOVAK_HOME / "registry" / "mcp-servers.yaml"
REGISTRY = _deployed if _deployed.exists() else REPO_DIR / "registry" / "mcp-servers.yaml"
OUTPUT = (NOVAK_HOME if _deployed.exists() else REPO_DIR) / "docker-compose.mcp.yml"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$")
ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
IMAGE_RE = re.compile(r"^[A-Za-z0-9._/:@-]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

RISK_LEVELS = ("standard", "elevated", "dangerous")


class ValidationError(Exception):
    pass


def validate_risk(name: str, entry: dict, enabled: bool) -> dict:
    """
    Enforces the danger-zone rule: anything more powerful than `standard` may
    only run if a person wrote down why, who accepted it, and when.

    Disabled entries are checked for shape but not for acceptance — you can
    describe something risky in the registry without having to justify it
    until you actually turn it on.
    """
    risk = entry.get("risk") or {"level": "standard"}
    if not isinstance(risk, dict):
        raise ValidationError(f"[{name}] risk must be a mapping")

    level = risk.get("level", "standard")
    if level not in RISK_LEVELS:
        raise ValidationError(f"[{name}] risk.level must be one of {RISK_LEVELS}, got {level!r}")

    if level == "standard" or not enabled:
        return {"level": level}

    why = risk.get("why")
    if not isinstance(why, list) or not why or not all(isinstance(w, str) and w.strip() for w in why):
        raise ValidationError(
            f"[{name}] risk.level is {level!r} and it is enabled, so risk.why must list "
            f"at least one reason explaining what it can do."
        )

    accepted_by = risk.get("accepted_by")
    if not isinstance(accepted_by, str) or not accepted_by.strip():
        raise ValidationError(
            f"[{name}] risk.level is {level!r} and it is enabled, so risk.accepted_by "
            f"must name the person who accepted it."
        )

    accepted_on = risk.get("accepted_on")
    accepted_on = accepted_on.isoformat() if hasattr(accepted_on, "isoformat") else accepted_on
    if not isinstance(accepted_on, str) or not DATE_RE.match(accepted_on):
        raise ValidationError(
            f"[{name}] risk.level is {level!r} and it is enabled, so risk.accepted_on "
            f"must be a date like 2026-08-16."
        )

    return {"level": level, "why": why, "accepted_by": accepted_by, "accepted_on": accepted_on}


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

    kind = entry.get("kind", "container")
    if kind not in ("container", "external"):
        raise ValidationError(f"[{name}] kind must be 'container' or 'external', got {kind!r}")

    enabled_raw = req("enabled")
    if not isinstance(enabled_raw, bool):
        raise ValidationError(f"[{name}] enabled must be true/false, got {enabled_raw!r}")

    if kind == "external":
        # Nothing is started; we only catalogue it. Still validate risk, so an
        # external endpoint with broad powers gets accepted on the record too.
        url = req("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            raise ValidationError(f"[{name}] external entries need an http(s) url, got {url!r}")
        for forbidden in ("image", "command", "port"):
            if forbidden in entry:
                raise ValidationError(
                    f"[{name}] kind is 'external' so {forbidden!r} makes no sense here"
                )
        auth = entry.get("auth")
        if auth is not None and (not isinstance(auth, str) or not ENV_RE.match(auth)):
            raise ValidationError(
                f"[{name}] auth must be an UPPER_SNAKE variable name, got {auth!r}"
            )

        seen_names.add(name)
        return {
            "name": name, "kind": kind, "url": url, "enabled": enabled_raw,
            "auth": auth,
            "risk": validate_risk(name, entry, enabled_raw),
            "source": entry.get("source"),
        }

    image = req("image")
    if not isinstance(image, str) or not IMAGE_RE.match(image):
        raise ValidationError(f"[{name}] invalid image {image!r}")

    port = req("port")
    if not isinstance(port, int) or isinstance(port, bool) or not (1024 <= port <= 65535):
        raise ValidationError(f"[{name}] port must be an int in 1024-65535, got {port!r}")
    if port in seen_ports:
        raise ValidationError(f"[{name}] duplicate port {port}")

    enabled = enabled_raw

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

    risk = validate_risk(name, entry, enabled)

    source = entry.get("source")
    if source is not None and not isinstance(source, dict):
        raise ValidationError(f"[{name}] source must be a mapping with url/license")

    seen_names.add(name)
    seen_ports.add(port)
    return {
        "name": name, "kind": "container", "image": image, "port": port,
        "enabled": enabled, "command": command, "env": env,
        "risk": risk, "source": source,
    }


def render(servers: list[dict]) -> dict:
    services = {}
    for s in servers:
        # External endpoints are catalogued, not run.
        if s["kind"] == "external" or not s["enabled"]:
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
        "# GENERATED by reconciler/reconcile.py — do not edit.\n"
        "# Source of truth: registry/mcp-servers.yaml\n"
    )

    enabled = [s for s in servers if s["enabled"]]
    disabled = [s for s in servers if not s["enabled"]]
    running = [s for s in enabled if s["kind"] == "container"]
    external = [s for s in enabled if s["kind"] == "external"]

    print(f"running:  {', '.join(s['name'] for s in running) or '(none)'}")
    print(f"disabled: {', '.join(s['name'] for s in disabled) or '(none)'}")
    for s in external:
        auth = f"  [token: {s['auth']}]" if s.get("auth") else ""
        print(f"external: {s['name']} -> {s['url']}{auth}")

    # Surface accepted risk on every run, so a `dangerous` server that was
    # accepted months ago doesn't quietly fade into the background.
    for s in enabled:
        level = s["risk"]["level"]
        if level != "standard":
            who, when = s["risk"]["accepted_by"], s["risk"]["accepted_on"]
            print(f"  ! {s['name']}: {level} — accepted by {who} on {when}")
            for reason in s["risk"]["why"]:
                print(f"      {reason}")

    if args.dry_run:
        print(f"\n--- would write {OUTPUT} ---\n{header}{rendered}")
        return 0

    OUTPUT.write_text(header + rendered)
    print(f"wrote {OUTPUT}")

    # --project-directory is what separates runtime from the checkout: every
    # relative bind in docker-compose.yml (./registry, ./wakeword/models)
    # resolves against it, so they land in NOVAK_HOME rather than the repo.
    project_dir = OUTPUT.parent
    cmd = ["docker", "compose", "--project-directory", str(project_dir)]
    env_file = project_dir / ".env"
    if env_file.exists():
        cmd += ["--env-file", str(env_file)]
    cmd += ["-f", str(REPO_DIR / "docker-compose.yml"), "-f", str(OUTPUT),
            "up", "-d", "--remove-orphans"]
    try:
        subprocess.run(cmd, check=True, env=os.environ)
    except FileNotFoundError:
        sys.exit(
            "docker not found on PATH.\n"
            "  If OrbStack is installed, its shim may not be on this shell's PATH:\n"
            "    export PATH=\"$HOME/.orbstack/bin:$PATH\""
        )
    except subprocess.CalledProcessError as e:
        # A traceback here is noise — the failure is almost always the daemon,
        # not this script.
        sys.exit(
            f"\ndocker compose failed (exit {e.returncode}).\n"
            "  Most often this means the Docker daemon isn't ready. Check:\n"
            "    docker info\n"
            "  If that errors with EOF or 'connect', OrbStack is still starting or\n"
            "  is waiting on a first-run dialog. Start it, wait for it to settle,\n"
            "  then use scripts/launch-stack.sh, which waits for the socket."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
