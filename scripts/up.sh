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
# || true matters: under set -e, a variable declared in vars.sh but not yet
# a line in an existing deployment's .env (exactly what happens the first
# time a new optional-profile variable is added, before that .env has been
# regenerated) makes grep return no match, which is exit 1, which kills the
# whole script here rather than just leaving that one profile unconfigured.
# Found by adding PORTAL_EDITS/PORTAL_SECRETS to a deployment whose .env
# predated them; scripts/novak's own envval() already had this guard.
envval() { grep -E "^${1}=" "$NOVAK_HOME/.env" 2>/dev/null | head -1 | cut -d= -f2- || true ; }

# The console is optional (docs/deploy-checklist.md phase 9 calls it genuinely
# skippable), so its configuration must not gate anything else. Rather than
# demand its values, decide here whether it is configured; if not, it is left
# out and everything else starts. Same rule the reconciler applies to an
# unconfigured MCP server.
console_missing=()
for var in "${CONSOLE_EDITS[@]}"; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) console_missing+=("$var") ;; esac
done
for var in "${CONSOLE_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) console_missing+=("$var") ;; esac
done

portal_missing=()
for var in "${PORTAL_EDITS[@]}"; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) portal_missing+=("$var") ;; esac
done
for var in "${PORTAL_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) portal_missing+=("$var") ;; esac
done

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
# Compose reads COMPOSE_PROFILES from the environment, and the reconciler is
# what runs `docker compose up`, so this is all it takes to include or omit
# either optional profile — no reconciler change, and nothing here needs to
# know about them beyond this check. Additive (comma-joined) since both can
# be active at once.
profiles=()
if [ ${#console_missing[@]} -eq 0 ]; then
  profiles+=(console)
else
  echo "skipped:  console — not configured: ${console_missing[*]}" >&2
  echo "          everything else starts; set those and re-run to add it." >&2
fi
if [ ${#portal_missing[@]} -eq 0 ]; then
  profiles+=(portal)
else
  echo "skipped:  portal — not configured: ${portal_missing[*]}" >&2
  echo "          everything else starts; set those and re-run to add it." >&2
fi
if [ ${#profiles[@]} -gt 0 ]; then
  export COMPOSE_PROFILES
  COMPOSE_PROFILES="$(IFS=,; echo "${profiles[*]}")"
fi

NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/reconcile.py"

# oMLX profiles. Deliberately non-fatal: oMLX is a host app this script does not
# manage, and at boot the LaunchAgent may well reach here before it is up.
# Failing the whole stack because an inference server is not ready yet would be
# the same mistake as the console gate. It is a no-op when nothing differs, so
# running it every time costs nothing and never restarts oMLX needlessly.
if [ -f "$REPO_DIR/reconciler/omlx_apply.py" ]; then
  if ! NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/omlx_apply.py"; then
    echo "note:     oMLX profiles not applied — run 'novak omlx apply' once it is up." >&2
  fi
fi

docker compose \
  --project-directory "$NOVAK_HOME" \
  --env-file "$NOVAK_HOME/.env" \
  -f "$REPO_DIR/docker-compose.yml" \
  -f "$NOVAK_HOME/docker-compose.mcp.yml" \
  ps
