#!/usr/bin/env python3
"""Add another instance of an integration to the deployed MCP registry.

`novak add` calls this. Each integration kind has a template: what to ask,
what entry to write, and which secrets that entry needs. A second Outline, a
third Tududi, a bank for another person: the same command, a different name.

It edits registry/mcp-servers.yaml by appending text, so every comment in that
file survives, then validates the result with the reconciler and puts the old
file back if the registry no longer loads. It never reads or prints a secret:
it reports which variable names still need a value, and `novak` asks for them.

  instances.py add [--kind K] [--name N] [--set field=value ...] [--yes]
  instances.py kinds
  instances.py secret-vars       names that hold credentials, from the registry
"""
import argparse
import datetime
import getpass
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

NOVAK_HOME = Path(os.environ.get("NOVAK_HOME", Path.home() / ".novak"))
REGISTRY = NOVAK_HOME / "registry" / "mcp-servers.yaml"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SECRETISH = re.compile(r"_(KEY|TOKEN|SECRET|PASSWORD)$")


class Abort(Exception):
    pass


def var(prefix: str, instance: str, suffix: str) -> str:
    return f"{prefix}_{instance.upper().replace('-', '_')}_{suffix}"


def ask(answers, field, question, default=None, yes=False, choices=None):
    """Answer from --set, else prompt (stderr, so stdout stays machine-readable)."""
    if field in answers:
        value = answers[field]
    elif yes and default is not None:
        value = default
    else:
        hint = f" [{default}]" if default not in (None, "") else ""
        print(f"{question}{hint}: ", end="", file=sys.stderr, flush=True)
        value = sys.stdin.readline().strip() or (default or "")
    if choices and value not in choices:
        raise Abort(f"{field} must be one of {', '.join(choices)} (got {value!r})")
    if value == "" and default is None:
        raise Abort(f"{field} is required")
    return value


def yn(answers, field, question, default=False, yes=False):
    raw = ask(answers, field, question + " (y/n)", "y" if default else "n", yes)
    return raw.lower() in ("y", "yes", "true", "1")


# --- registry access -----------------------------------------------------------
def load_entries(path=None):
    data = yaml.safe_load(Path(path or REGISTRY).read_text()) or {}
    return data.get("servers") or []


def used_ports(entries):
    return {e["port"] for e in entries if isinstance(e.get("port"), int)}


def hindsight_base(entries):
    """Scheme and host of an existing Hindsight entry, so a new bank matches."""
    for e in entries:
        m = re.match(r"^(https?://[^/]+)/mcp/", e.get("url") or "")
        if m and "EDIT-ME" not in m.group(1):
            return m.group(1)
    return "http://hindsight:8888"


def entry_for(entries, name):
    return next((e for e in entries if e.get("name") == name), None)


# --- templates -----------------------------------------------------------------
def risk_block(level, why, who, today):
    if level == "standard":
        return {"level": "standard"}
    return {"level": level, "why": why, "accepted_by": who, "accepted_on": today}


def t_hindsight(a, entries, who, today, yes):
    bank = ask(a, "bank", "Bank name (one per person or shared space, e.g. ushy)", yes=yes)
    voice = yn(a, "voice_safe", "Safe for voice satellites (a shared bank anyone in the room may reach)?", False, yes)
    base = ask(a, "base", "Hindsight address clients use", hindsight_base(entries), yes)
    why = ["Holds memories; a wrong bank id in a client points someone at another "
           "person's history."]
    if not voice:
        why.append("Personal memories. Registering this in a shared client would "
                   "expose them to everyone using it.")
    return dict(
        name=f"hindsight-{bank}", secrets=[], config={},
        entry={"name": f"hindsight-{bank}", "kind": "external",
               "url": f"{base.rstrip('/')}/mcp/{bank}/", "auth": "HINDSIGHT_API_KEY",
               "enabled": True,
               "clients": ["home-assistant"] if voice else ["open-webui"],
               "source": {"url": "https://github.com/vectorize-io/hindsight", "license": "MIT"},
               "risk": risk_block("elevated", why, who, today)},
        notes=[f"Same tenant API key as every bank (HINDSIGHT_API_KEY); the bank is in the URL.",
               f"If the console should map a person to this bank, their sign-in name must be '{bank}'."])


def t_outline(a, entries, who, today, yes):
    inst = ask(a, "instance", "Instance name (e.g. work)", yes=yes)
    url = ask(a, "url", "MCP URL (e.g. https://wiki.example.com/mcp)", yes=yes)
    token = var("OUTLINE", inst, "API_KEY")
    return dict(
        name=f"outline-{inst}", secrets=[token], config={},
        entry={"name": f"outline-{inst}", "kind": "external", "url": url, "auth": token,
               "enabled": True, "clients": ["open-webui"],
               "source": {"url": "https://github.com/outline/outline",
                          "license": "BSL 1.1 (check before any commercial use)"},
               "risk": {"level": "standard"}}, notes=[])


def t_tududi(a, entries, who, today, yes):
    inst = ask(a, "instance", "Instance name (e.g. partner)", yes=yes)
    url = ask(a, "url", "MCP URL (e.g. https://tududi.example.com/api/mcp)", yes=yes)
    token = var("TUDUDI", inst, "API_TOKEN")
    why = ["59 tools across tasks, projects, notes, goals, habits and people: a very "
           "broad surface for one integration.",
           "Can create, modify and delete across all of them. VERIFY whether Tududi "
           "has a trash before trusting deletes to be recoverable."]
    return dict(
        name=f"tududi-{inst}", secrets=[token], config={},
        entry={"name": f"tududi-{inst}", "kind": "external", "url": url, "auth": token,
               "enabled": True, "clients": ["open-webui"],
               "source": {"url": "https://github.com/chrisvel/tududi", "license": "VERIFY"},
               "risk": risk_block("elevated", why, who, today)},
        notes=["One token is one Tududi account: each person needs their own instance entry."])


def t_vikunja(a, entries, who, today, yes):
    inst = ask(a, "instance", "Instance name (e.g. partner)", yes=yes)
    url = ask(a, "url", "Vikunja URL (e.g. https://tasks.example.com)", yes=yes)
    model = entry_for(entries, "vikunja") or {}
    image = model.get("image", "node:22-alpine")
    command = model.get("command") or (
        'npx -y supergateway --stdio "npx -y @aimbitgmbh/vikunja-mcp" '
        "--outputTransport streamableHttp --port 8000")
    port = max(used_ports(entries) | {8001}) + 1
    url_var, token_var = var("VIKUNJA", inst, "URL"), var("VIKUNJA", inst, "API_TOKEN")
    why = ["Vikunja has no trash or undo: a delete is permanent."]
    return dict(
        name=f"vikunja-{inst}", secrets=[token_var], config={url_var: url},
        entry={"name": f"vikunja-{inst}", "image": image,
               "command": " ".join(str(command).split()), "port": port,
               "env": [f"VIKUNJA_URL={url_var}", f"VIKUNJA_API_TOKEN={token_var}"],
               "enabled": True, "clients": ["open-webui"],
               "source": {"url": "https://github.com/aimbitgmbh/vikunja-mcp", "license": "VERIFY"},
               "risk": risk_block("elevated", why, who, today)},
        notes=[f"Published on port {port}."])


def t_super_productivity(a, entries, who, today, yes):
    inst = ask(a, "instance", "Instance name (e.g. home)", "home", yes)
    url = ask(a, "url", "URL of the Super Productivity MCP endpoint you run", yes=yes)
    entry = {"name": f"super-productivity-{inst}", "kind": "external", "url": url,
             "enabled": True, "clients": ["open-webui"],
             "source": {"url": "https://super-productivity.com", "license": "VERIFY"},
             "risk": {"level": "standard"}}
    secrets = []
    if yn(a, "needs_token", "Does that endpoint need a bearer token?", False, yes):
        token = var("SUPER_PRODUCTIVITY", inst, "TOKEN")
        entry["auth"], secrets = token, [token]
    return dict(
        name=entry["name"], secrets=secrets, config={}, entry=entry,
        notes=["Super Productivity has no official MCP server. The community ones "
               "(a plugin bridge or the desktop app's local REST API) need the desktop "
               "app running, so point this at wherever you run one. VERIFY it works "
               "headless before relying on it."])


def t_mcp(a, entries, who, today, yes):
    name = ask(a, "name_full", "Entry name (a-z, 0-9, hyphen)", yes=yes)
    url = ask(a, "url", "MCP URL", yes=yes)
    level = ask(a, "risk", "Risk level", "standard", yes, ("standard", "elevated"))
    secrets, entry = [], {"name": name, "kind": "external", "url": url, "enabled": True,
                          "clients": ["open-webui"]}
    if yn(a, "needs_token", "Needs a bearer token?", True, yes):
        token = ask(a, "token_var", "Variable holding the token (UPPER_SNAKE, e.g. MYSERVICE_API_TOKEN)", yes=yes)
        if not re.match(r"^[A-Z][A-Z0-9_]*$", token):
            raise Abort(f"token variable {token!r} must be UPPER_SNAKE")
        entry["auth"], secrets = token, [token]
    why = ["Raised by hand when added with `novak add`; write down why."]
    entry["risk"] = risk_block(level, why, who, today)
    return dict(name=name, secrets=secrets, config={}, entry=entry, notes=[])


TEMPLATES = {
    "hindsight": ("A Hindsight memory bank (one per person)", t_hindsight),
    "outline": ("Another Outline wiki", t_outline),
    "tududi": ("Another Tududi task list", t_tududi),
    "vikunja": ("Another Vikunja (runs its own container)", t_vikunja),
    "super-productivity": ("A Super Productivity MCP endpoint", t_super_productivity),
    "mcp": ("Any other MCP server by URL", t_mcp),
}


# --- writing -------------------------------------------------------------------
def render(entry: dict, who: str, today: str) -> str:
    body = yaml.safe_dump([entry], sort_keys=False, width=100, default_flow_style=False)
    body = "".join("  " + line if line.strip() else line for line in body.splitlines(True))
    return f"\n  # added by `novak add` on {today}\n{body}"


def set_env_values(values: dict, env_file: Path):
    """Non-secret configuration (a URL) goes straight into .env."""
    if not values:
        return
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    for key, val in values.items():
        row = f"{key}={val}"
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = row
                break
        else:
            lines.append(row)
    env_file.write_text("\n".join(lines) + "\n")


def validate(path: Path) -> str:
    """Run the real reconciler in dry-run mode against this registry."""
    here = Path(__file__).resolve().parent
    proc = subprocess.run([sys.executable, str(here / "reconcile.py"), "--dry-run"],
                          capture_output=True, text=True,
                          env={**os.environ, "NOVAK_HOME": str(NOVAK_HOME)})
    return "" if proc.returncode == 0 else (proc.stderr or proc.stdout).strip()


def cmd_add(args) -> int:
    answers = dict(kv.split("=", 1) for kv in args.set or [])
    if not REGISTRY.exists():
        print(f"No registry at {REGISTRY}: run 'novak up' once to seed it.", file=sys.stderr)
        return 1
    kind = args.kind
    if not kind:
        print("What are you adding?", file=sys.stderr)
        for k, (label, _) in TEMPLATES.items():
            print(f"  {k:20} {label}", file=sys.stderr)
        kind = ask(answers, "kind", "Kind", yes=False, choices=tuple(TEMPLATES))
    if kind not in TEMPLATES:
        print(f"unknown kind {kind!r}; known: {', '.join(TEMPLATES)}", file=sys.stderr)
        return 1
    if args.name:                       # --name is the instance (or bank) name
        answers.setdefault("instance", args.name)
        answers.setdefault("bank", args.name)
        answers.setdefault("name_full", args.name)
    who = args.accepted_by or os.environ.get("USER") or getpass.getuser()
    today = datetime.date.today().isoformat()
    entries = load_entries()
    plan = TEMPLATES[kind][1](answers, entries, who, today, args.yes)
    name = plan["name"]
    if not NAME_RE.match(name):
        raise Abort(f"'{name}' is not a valid entry name (a-z, 0-9 and hyphens)")
    if entry_for(entries, name):
        raise Abort(f"'{name}' already exists in the registry; pick another name")
    if plan["entry"]["risk"]["level"] != "standard":
        print(f"\n{name} is '{plan['entry']['risk']['level']}' risk. Reasons:", file=sys.stderr)
        for w in plan["entry"]["risk"]["why"]:
            print(f"  - {w}", file=sys.stderr)
        if not (args.yes or yn(answers, "accept", f"Record that {who} accepts this?", False)):
            raise Abort("not accepted; nothing written")
    text = render(plan["entry"], who, today)
    if args.dry_run:
        print(text, file=sys.stderr)
        print("dry run: nothing written", file=sys.stderr)
        return 0
    backup = REGISTRY.with_name(f"{REGISTRY.name}.bak-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(REGISTRY, backup)
    with REGISTRY.open("a") as f:
        f.write(text)
    problem = validate(REGISTRY)
    if problem:
        shutil.copy2(backup, REGISTRY)
        print(f"The registry did not validate with that entry, so it was put back:\n{problem}",
              file=sys.stderr)
        return 1
    set_env_values(plan["config"], NOVAK_HOME / ".env")
    print(f"Added {name} to {REGISTRY} (backup: {backup.name}).", file=sys.stderr)
    for note in plan["notes"]:
        print(f"  note: {note}", file=sys.stderr)
    # The one machine-readable line: variables that still need a secret value.
    print("SECRETS: " + " ".join(plan["secrets"]))
    return 0


def secret_vars(path=None) -> list[str]:
    """Credential variables the registry refers to: `auth:` names and the source
    side of container env items, kept to names that look like credentials."""
    names = []
    for e in load_entries(path):
        cands = [e["auth"]] if e.get("auth") else []
        cands += [i.partition("=")[2] or i for i in e.get("env") or []]
        names += [c for c in cands if SECRETISH.search(c)]
    return sorted(set(names))


def describe(var_name: str, path=None) -> str:
    """Which registry entries use a credential variable, in plain words."""
    users = []
    for e in load_entries(path):
        if e.get("auth") == var_name:
            users.append(f"{e['name']} (MCP endpoint)")
        elif any((i.partition("=")[2] or i) == var_name for i in e.get("env") or []):
            users.append(f"{e['name']} (container)")
    return "used by " + ", ".join(users) if users else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("--kind")
    add.add_argument("--name", help="the instance (or Hindsight bank) name")
    add.add_argument("--set", action="append", metavar="field=value")
    add.add_argument("--accepted-by")
    add.add_argument("--yes", action="store_true", help="take defaults, accept risk prompts")
    add.add_argument("--dry-run", action="store_true")
    sub.add_parser("kinds")
    sub.add_parser("secret-vars")
    d = sub.add_parser("describe")
    d.add_argument("var")
    args = ap.parse_args()
    try:
        if args.cmd == "kinds":
            for k, (label, _) in TEMPLATES.items():
                print(f"{k:20} {label}")
            return 0
        if args.cmd == "describe":
            print(describe(args.var))
            return 0
        if args.cmd == "secret-vars":
            print("\n".join(secret_vars()))
            return 0
        return cmd_add(args)
    except Abort as exc:
        print(f"✋ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
