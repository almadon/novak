#!/usr/bin/env bash
# Start (or update) the stack. Secrets are read from macOS Keychain items
# named "novak/<VAR>" when present; otherwise values from .env apply.
# Add a secret with:
#   security add-generic-password -s "novak/OUTLINE_API_KEY" -a novak -w
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
SECRET_VARS=(
  OMLX_API_KEY
  OUTLINE_API_KEY
  VIKUNJA_API_TOKEN
  CONSOLE_AUTH_SECRET
  OIDC_CLIENT_SECRET
  MEM0_POSTGRES_PASSWORD
  MEM0_JWT_SECRET
  MEM0_API_KEY
  MEMORY_TOKEN_MAP
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
  MEM0_POSTGRES_PASSWORD
  MEM0_JWT_SECRET
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
PY=$(command -v python3 || true)
if [ -z "$PY" ]; then
  echo "✋ python3 not found — needed by reconciler/reconcile.py" >&2
  exit 1
fi
if ! "$PY" -c 'import yaml' 2>/dev/null; then
  echo "✋ PyYAML missing — run: pip3 install --user pyyaml" >&2
  exit 1
fi
NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/reconcile.py"

docker compose \
  --project-directory "$NOVAK_HOME" \
  --env-file "$NOVAK_HOME/.env" \
  -f "$REPO_DIR/docker-compose.yml" \
  -f "$NOVAK_HOME/docker-compose.mcp.yml" \
  ps
