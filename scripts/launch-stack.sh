#!/usr/bin/env bash
# Brings the stack up once Docker is actually ready.
#
# Login Items launch OrbStack, but the Docker socket is not accepting
# connections the moment the app icon appears — running `docker compose` too
# early fails against a socket that is not listening yet. This waits.
#
# Invoked by the LaunchAgent (see docs/headless-operation.md). Safe to run by
# hand.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# OrbStack puts docker on the PATH via a shim that a non-interactive LaunchAgent
# shell may not have sourced.
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:$PATH"

TIMEOUT=${DOCKER_WAIT_SECONDS:-300}
echo "$(date '+%F %T')  waiting up to ${TIMEOUT}s for Docker..."

deadline=$(( $(date +%s) + TIMEOUT ))
until docker info >/dev/null 2>&1; do
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "$(date '+%F %T')  Docker never became ready — is OrbStack in Login Items?" >&2
    exit 1
  fi
  sleep 5
done

echo "$(date '+%F %T')  Docker ready; starting stack"
exec ./scripts/up.sh
