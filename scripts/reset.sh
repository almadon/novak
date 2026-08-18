#!/usr/bin/env bash
# Tears the stack down so bootstrap.sh can be run again cleanly.
#
# Default is deliberately conservative: it removes what bootstrap.sh creates
# and nothing that would cost you work. Your config, secrets, models and data
# survive, because re-running bootstrap is a routine thing and should not be a
# decision with consequences.
#
#   ./scripts/reset.sh                 stop and remove containers
#   ./scripts/reset.sh --purge-data    ALSO delete volumes (memories, chats)
#   ./scripts/reset.sh --purge-config  ALSO delete NOVAK_HOME (.env, registry)
#
# Never touched by any flag: macOS Keychain secrets, oMLX models, Homebrew,
# OrbStack, and the git checkout. Those are either expensive to rebuild or not
# ours to remove — see the notes at the end for undoing them by hand.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NOVAK_HOME="${NOVAK_HOME:-$HOME/.novak}"

PURGE_DATA=0
PURGE_CONFIG=0
for arg in "$@"; do
  case "$arg" in
    --purge-data)   PURGE_DATA=1 ;;
    --purge-config) PURGE_CONFIG=1 ;;
    -h|--help)      awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }

confirm() {
  # Refuse destructive work in a non-interactive shell rather than guessing.
  if [ ! -t 0 ]; then
    echo "✋ $1 needs an interactive terminal to confirm. Aborting." >&2
    exit 1
  fi
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
}

COMPOSE=(docker compose --project-directory "$NOVAK_HOME" -f "$REPO_DIR/docker-compose.yml")
[ -f "$NOVAK_HOME/.env" ] && COMPOSE+=(--env-file "$NOVAK_HOME/.env")
[ -f "$NOVAK_HOME/docker-compose.mcp.yml" ] && COMPOSE+=(-f "$NOVAK_HOME/docker-compose.mcp.yml")

step "Containers"
if ! docker info >/dev/null 2>&1; then
  warn "Docker is not running — skipping. Start OrbStack and re-run if containers still exist."
else
  if [ "$PURGE_DATA" -eq 1 ]; then
    confirm "Delete ALL volumes? Memories, chat history and the Mem0 database are lost."
    "${COMPOSE[@]}" down --volumes --remove-orphans || warn "compose down reported an error; continuing"
    echo "containers and volumes removed"
  else
    "${COMPOSE[@]}" down --remove-orphans || warn "compose down reported an error; continuing"
    echo "containers removed; volumes kept (use --purge-data to delete them)"
  fi
fi

step "Generated files"
rm -f "$NOVAK_HOME/docker-compose.mcp.yml" && echo "removed generated compose override"

if [ "$PURGE_CONFIG" -eq 1 ]; then
  step "Configuration"
  confirm "Delete $NOVAK_HOME entirely? .env, the registry and any trained wake-word models go with it."
  rm -rf "$NOVAK_HOME"
  echo "removed $NOVAK_HOME"
else
  step "Configuration — kept"
  echo "$NOVAK_HOME is untouched (.env, registry, wakeword models)."
  echo "bootstrap.sh will reuse it rather than reseeding."
fi

step "Done"
cat <<NOTE
Re-run with:  ./scripts/bootstrap.sh

Left alone on purpose — remove by hand if you really want them gone:

  Keychain secrets   security delete-generic-password -s "novak/OMLX_API_KEY"
                     (repeat per novak/* item; see docs/security.md)
  oMLX + models      rm -rf ~/.omlx  and delete /Applications/oMLX.app
                     (models are large; re-downloading is slow)
  OrbStack           brew uninstall --cask orbstack
  Power profile      sudo pmset -c sleep 1 disksleep 10 autorestart 0
                     (only if reverting this machine to desktop behaviour)
NOTE
