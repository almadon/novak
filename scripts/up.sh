#!/usr/bin/env bash
# Start (or update) the stack. Secrets are read from macOS Keychain items
# named "mini-ai/<VAR>" when present; otherwise values from .env apply.
# Add a secret with:
#   security add-generic-password -s "mini-ai/OUTLINE_API_KEY" -a mini-ai -w
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

SECRET_VARS=(OMLX_API_KEY OUTLINE_API_KEY VIKUNJA_API_TOKEN)

for var in "${SECRET_VARS[@]}"; do
  if val=$(security find-generic-password -s "mini-ai/${var}" -w 2>/dev/null); then
    export "${var}=${val}"
    echo "🔑 ${var}: loaded from Keychain"
  fi
done

docker compose up -d --remove-orphans
docker compose ps
