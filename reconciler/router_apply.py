#!/usr/bin/env python3
"""
Applies registry/engines.yaml to router/config.yaml.

Same shape as reconciler/reconcile.py, applied to a different file: this is
the reconciler decision #21's own router/config.yaml comment named as the
gap left open — "A reconciler step that generates this from omlx.yaml would
close that gap; not built here" — except it turned out to be the wrong
comment. The real coupling isn't router/config.yaml-to-omlx.yaml
specifically; it's router/config.yaml-to-WHICHEVER-ENGINES-a-deployment-
actually-runs, once more than one engine is real (decision #28).

Deliberately dumb, same invariants as reconcile.py:
  * No shell, no interpolation of registry values into anything executed.
  * Fail closed: any validation error aborts the whole run.
  * Secrets are never read here. base_url_var/api_key_var carry variable
    NAMES; router/config.yaml keeps its own os.environ/VARNAME references
    for LiteLLM to resolve at its own startup, same as before this existed.

This does not restart the router — LiteLLM reads config.yaml at container
start, not on a hot reload, so a written change needs `novak restart
router` to take effect. Left as a separate, visible step rather than done
here, matching how `novak omlx apply` makes its own restart explicit rather
than silent.

Usage:
    ./router_apply.py [--dry-run]

Requires PyYAML:  pip3 install --user pyyaml
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required:  pip3 install --user pyyaml")

REPO_DIR = Path(__file__).resolve().parent.parent
NOVAK_HOME = Path(os.environ.get("NOVAK_HOME", Path.home() / ".novak"))

_deployed = NOVAK_HOME / "registry" / "engines.yaml"
REGISTRY = _deployed if _deployed.exists() else REPO_DIR / "registry" / "engines.yaml"

# NOVAK_HOME, never REPO_DIR — this is per-deployment output (which engine
# serves which model differs by household), not a repo file, so it must
# never land in the checkout or get committed. Same treatment
# docker-compose.mcp.yml already gets from reconcile.py, for the same
# reason. docker-compose.yml's router service mounts this exact path with
# a relative bind (`./router-config.yaml`), which resolves against
# `--project-directory` ($NOVAK_HOME) the same way `./registry` does.
OUTPUT = NOVAK_HOME / "router-config.yaml"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}[a-z0-9]$")
ENV_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")

# Static across every deployment: the persona-injection hook decision #23
# built, registered the one way confirmed to actually fire against LiteLLM's
# current build (async_pre_call_hook, not the documented-but-inert
# CustomPromptManagement API — see router/persona_hook.py's own docstring).
# Nothing about which engines exist changes this, so it isn't part of the
# registry — a callbacks line that varied per deployment would be a second
# thing to keep in sync for no reason.
LITELLM_SETTINGS_BLOCK = {"callbacks": "persona_hook.persona_injector"}


class ValidationError(Exception):
    pass


def validate_engine(entry: dict, seen_roles: set[str]) -> dict:
    def req(key: str):
        if key not in entry:
            raise ValidationError(f"missing required key {key!r}")
        return entry[key]

    name = req("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValidationError(f"invalid engine name {name!r} (expected ^[a-z0-9][a-z0-9-]*[a-z0-9]$)")

    base_url_var = req("base_url_var")
    if not isinstance(base_url_var, str) or not ENV_RE.match(base_url_var):
        raise ValidationError(f"[{name}] base_url_var must be an UPPER_SNAKE variable name, got {base_url_var!r}")

    api_key_var = entry.get("api_key_var")
    if api_key_var is not None and (not isinstance(api_key_var, str) or not ENV_RE.match(api_key_var)):
        raise ValidationError(f"[{name}] api_key_var must be an UPPER_SNAKE variable name or null, got {api_key_var!r}")

    models = req("models")
    if not isinstance(models, list) or not models:
        raise ValidationError(f"[{name}] models must be a non-empty list")

    resolved = []
    for m in models:
        if not isinstance(m, dict):
            raise ValidationError(f"[{name}] each model entry must be a mapping")
        role = m.get("role")
        if not isinstance(role, str) or not ROLE_RE.match(role):
            raise ValidationError(f"[{name}] invalid role {role!r} (expected ^[a-z][a-z0-9-]*$)")
        model = m.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValidationError(f"[{name}] role {role!r}: model must be a non-empty string")
        if role in seen_roles:
            raise ValidationError(
                f"role {role!r} is claimed by more than one engine — that's ambiguous "
                f"routing, not load-balancing. Every role must belong to exactly one engine."
            )
        seen_roles.add(role)
        resolved.append({"role": role, "model": model})

    return {"name": name, "base_url_var": base_url_var, "api_key_var": api_key_var, "models": resolved}


def render(engines: list[dict]) -> dict:
    # os.environ/VARNAME, not a ${VAR} port substitution built inline: this
    # is the only substitution LiteLLM's config.yaml documents, and it's for
    # a WHOLE field value, not shell-style interpolation inside a larger
    # string. That means base_url_var has to hold the complete reachable URL
    # (docker-compose.yml or .env builds it, e.g. with its own
    # ${OMLX_PORT:-8000} pattern) — LiteLLM itself never sees the port as a
    # separate, configurable piece.
    model_list = []
    for e in engines:
        api_key = f"os.environ/{e['api_key_var']}" if e["api_key_var"] else "none"
        for m in e["models"]:
            model_list.append({
                "model_name": m["role"],
                "litellm_params": {
                    "model": f"openai/{m['model']}",
                    "api_base": f"os.environ/{e['base_url_var']}",
                    "api_key": api_key,
                },
            })
    return {"model_list": model_list, "litellm_settings": LITELLM_SETTINGS_BLOCK}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="validate and render, but do not write")
    args = ap.parse_args()

    if not REGISTRY.exists():
        sys.exit(f"registry not found: {REGISTRY}")

    doc = yaml.safe_load(REGISTRY.read_text()) or {}
    entries = doc.get("engines")
    if not isinstance(entries, list) or not entries:
        sys.exit("registry: top-level 'engines' must be a non-empty list")

    seen_roles: set[str] = set()
    engines = []
    try:
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValidationError(f"entry must be a mapping, got {type(entry).__name__}")
            engines.append(validate_engine(entry, seen_roles))
    except ValidationError as e:
        sys.exit(f"registry validation failed: {e}")

    header = (
        "# GENERATED by reconciler/router_apply.py — do not edit by hand.\n"
        "# Source of truth: registry/engines.yaml\n"
        "#\n"
        "# KNOWN COUPLING, same as before this generator existed:\n"
        "# litellm_params.model below must match each engine's OWN model id\n"
        "# exactly (oMLX's \"<repo-basename>:<profile>\", an Ollama tag, etc.).\n"
        "# Never validated against the engine itself — a wrong id here\n"
        "# surfaces as that engine 404ing at request time, not here.\n"
    )
    rendered = yaml.safe_dump(render(engines), sort_keys=False)

    for e in engines:
        roles = ", ".join(m["role"] for m in e["models"])
        print(f"engine: {e['name']} ({e['base_url_var']}) -> {roles}")

    if args.dry_run:
        print(f"\n--- would write {OUTPUT} ---\n{header}{rendered}")
        return 0

    OUTPUT.write_text(header + rendered)
    print(f"wrote {OUTPUT}")
    print("Router config changed on disk. Run 'novak restart router' to apply it —")
    print("LiteLLM reads this at container start, not on a hot reload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
