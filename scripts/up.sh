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
# shellcheck source=lib/vars.sh
source "$REPO_DIR/scripts/lib/vars.sh"

for var in "${SECRET_VARS[@]}"; do
  if val=$(security find-generic-password -s "novak/${var}" -w 2>/dev/null); then
    export "${var}=${val}"
    echo "🔑 ${var}: loaded from Keychain"
  fi
done

# Two different kinds of unconfigured value, reported separately because the
# fix differs: EDIT-ME means "put a real value in .env", set-in-keychain means
# "the Keychain lookup above found nothing".
envval() { grep -E "^${1}=" "$NOVAK_HOME/.env" 2>/dev/null | head -1 | cut -d= -f2- ; }

# Console vars matter only when the console service is present.
if grep -qE '^\s*console:' "$REPO_DIR/docker-compose.yml"; then
  REQUIRED_EDITS+=("${CONSOLE_EDITS[@]}")
fi

unedited=()
for var in "${REQUIRED_EDITS[@]}"; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) unedited+=("$var") ;; esac
done
if [ ${#unedited[@]} -gt 0 ]; then
  echo "" >&2
  echo "✋ These need real values in $NOVAK_HOME/.env:" >&2
  printf '     %s\n' "${unedited[@]}" >&2
  echo "" >&2
  echo "   HOST_NAME is how other machines reach this one (a Tailscale name works" >&2
  echo "   well). See the comments in that file — it says which lines to edit and" >&2
  echo "   which to leave alone." >&2
  echo "" >&2
  exit 1
fi

# Secrets: these must have resolved from the Keychain. A value still reading
# set-in-keychain means the lookup found nothing — usually because it was added
# under a different account, since the login keychain is per-user.
REQUIRED_SECRETS=("${CORE_SECRETS[@]}")
grep -qE '^\s*console:' "$REPO_DIR/docker-compose.yml" && REQUIRED_SECRETS+=("${CONSOLE_SECRETS[@]}")

missing=()
for var in "${REQUIRED_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) missing+=("$var") ;; esac
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "" >&2
  echo "✋ These secrets were not found in the Keychain:" >&2
  for var in "${missing[@]}"; do
    echo "     security add-generic-password -s \"novak/${var}\" -a $(whoami) -w" >&2
  done
  echo "" >&2
  echo "   Run those as $(whoami) — the login keychain is per-user, so items" >&2
  echo "   added under another account are invisible here." >&2
  echo "" >&2
  exit 1
fi

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
