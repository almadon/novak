#!/usr/bin/env bash
# Start (or update) the stack. Secrets are read from macOS Keychain items
# named "novak/<VAR>" when present; otherwise values from .env apply.
# Add a secret with:
#   security add-generic-password -s "novak/OUTLINE_EVERYTHING_API_KEY" -a novak -w
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Runtime lives outside the checkout. The repo holds definitions; NOVAK_HOME
# holds this deployment's config, data and generated files — so `git pull`
# never fights a running stack, and the checkout stays clean.
NOVAK_HOME="${NOVAK_HOME:-$HOME/.novak}"

# Seed on first run. Existing files are never overwritten: your config and your
# registry belong to you once created.
mkdir -p "$NOVAK_HOME/registry" "$NOVAK_HOME/wakeword/models"
if [ ! -f "$NOVAK_HOME/.env" ]; then
  cp "$REPO_DIR/.env.example" "$NOVAK_HOME/.env"
  echo "📄 seeded $NOVAK_HOME/.env from .env.example — fill it in before this will start"
fi
if [ ! -f "$NOVAK_HOME/registry/mcp-servers.yaml" ]; then
  cp "$REPO_DIR/registry/mcp-servers.yaml" "$NOVAK_HOME/registry/mcp-servers.yaml"
  echo "📄 seeded $NOVAK_HOME/registry/mcp-servers.yaml — edit it there, not in the repo"
fi

cd "$NOVAK_HOME"

# Every secret the stack needs. Anything listed here that is missing from both
# Keychain and .env will fall back to the .env.example placeholder, which is
# why the check below exists — a console running with AUTH_SECRET=changeme is
# worse than one that refuses to start.
# Per-instance where a service can have several: OUTLINE_<INSTANCE>_API_KEY
# rather than one OUTLINE_API_KEY, so a second Outline is an added line, not a
# collision. Add new ones here AND as a `auth:` field on the registry entry.
SECRET_VARS=(
  OMLX_API_KEY
  OUTLINE_EVERYTHING_API_KEY
  TUDUDI_API_TOKEN
  VIKUNJA_API_TOKEN
  CONSOLE_AUTH_SECRET
  OIDC_CLIENT_SECRET
  HINDSIGHT_API_KEY
)

for var in "${SECRET_VARS[@]}"; do
  if val=$(security find-generic-password -s "novak/${var}" -w 2>/dev/null); then
    export "${var}=${val}"
    echo "🔑 ${var}: loaded from Keychain"
  fi
done

# Refuse to start with placeholder secrets. These are the ones where a
# default value is actively dangerous rather than merely broken.
MUST_NOT_BE_PLACEHOLDER=(
  CONSOLE_AUTH_SECRET
  HINDSIGHT_API_KEY
)
placeholders=()
for var in "${MUST_NOT_BE_PLACEHOLDER[@]}"; do
  # Value comes from Keychain (exported above) or .env, which compose reads.
  val="${!var:-$(grep -E "^${var}=" "$NOVAK_HOME/.env" 2>/dev/null | cut -d= -f2- || true)}"
  if [ -z "${val}" ] || [ "${val}" = "changeme" ]; then
    placeholders+=("${var}")
  fi
done
if [ ${#placeholders[@]} -gt 0 ]; then
  echo "✋ Refusing to start — these are unset or still 'changeme':" >&2
  printf '   %s\n' "${placeholders[@]}" >&2
  echo "   Add them to Keychain (see docs/security.md) or $NOVAK_HOME/.env," >&2
  echo "   then re-run." >&2
  exit 1
fi

# MCP servers live in registry/mcp-servers.yaml, not in docker-compose.yml.
# The reconciler validates that registry, refuses to proceed if an elevated or
# dangerous entry is enabled without a recorded acceptance, renders
# docker-compose.mcp.yml, and brings everything up together.
#
# It is a hard gate on purpose: a failed risk acceptance should stop the whole
# start, not quietly skip one service.
# The reconciler needs PyYAML. Rather than depend on whichever python3 and
# pip3 happen to be first on PATH — they are often different interpreters, and
# `pip --user` is per-account and blocked outright on Homebrew python (PEP 668)
# — keep a small virtualenv in NOVAK_HOME. Self-healing, and immune to the
# system Python being upgraded or replaced underneath it.
VENV="$NOVAK_HOME/.venv"
PY="$VENV/bin/python3"

if [ ! -x "$PY" ] || ! "$PY" -c 'import yaml' 2>/dev/null; then
  SYS_PY=$(command -v python3 || true)
  if [ -z "$SYS_PY" ]; then
    echo "✋ python3 not found. Install Xcode command line tools:" >&2
    echo "     xcode-select --install" >&2
    exit 1
  fi
  echo "🐍 preparing $VENV (one-off)"
  if ! "$SYS_PY" -m venv "$VENV" 2>/dev/null; then
    echo "✋ could not create a virtualenv with $SYS_PY" >&2
    echo "   Try: $SYS_PY -m ensurepip --upgrade" >&2
    exit 1
  fi
  if ! "$PY" -m pip install --quiet --upgrade pyyaml; then
    echo "✋ could not install PyYAML into $VENV" >&2
    echo "   If this machine is offline, install it manually:" >&2
    echo "     $PY -m pip install pyyaml" >&2
    exit 1
  fi
  echo "🐍 PyYAML ready"
fi
NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/reconcile.py"

docker compose \
  --project-directory "$NOVAK_HOME" \
  --env-file "$NOVAK_HOME/.env" \
  -f "$REPO_DIR/docker-compose.yml" \
  -f "$NOVAK_HOME/docker-compose.mcp.yml" \
  ps
