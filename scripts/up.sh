#!/usr/bin/env bash
# Start (or update) the stack. Secrets are read from macOS Keychain items
# named "novak/<VAR>" when present; otherwise values from .env apply.
# Add a secret with:
#   security add-generic-password -s "novak/OUTLINE_API_KEY" -a novak -w
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

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
  val="${!var:-$(grep -E "^${var}=" .env 2>/dev/null | cut -d= -f2- || true)}"
  if [ -z "${val}" ] || [ "${val}" = "changeme" ]; then
    placeholders+=("${var}")
  fi
done
if [ ${#placeholders[@]} -gt 0 ]; then
  echo "✋ Refusing to start — these are unset or still 'changeme':" >&2
  printf '   %s\n' "${placeholders[@]}" >&2
  echo "   Add them to Keychain (see docs/security.md) or .env, then re-run." >&2
  exit 1
fi

# --build so local changes to console/ and memory-mcp/ actually take effect;
# without it compose reuses a stale image after an edit.
docker compose up -d --build --remove-orphans
docker compose ps

# NOTE: the MCP registry reconciler (console/reconciler/reconcile.py) is NOT
# run here yet. The registry currently duplicates the outline/vikunja service
# blocks in docker-compose.yml, so running both would collide on ports
# 8001/8002. Once those blocks are removed from compose, add the reconciler
# call here. See console/README.md.
