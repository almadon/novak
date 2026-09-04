#!/usr/bin/env bash
# One-time host setup for running Novak's `novak` CLI on Unraid.
#
# Unlike macOS (bootstrap.sh + bootstrap-admin.sh, split because the service
# account has no sudo), Unraid has exactly one real admin account — root —
# so there's nothing to split here. Run this once, as root, after cloning
# the repo.
#
# What it does, and why each part exists:
#   1. Confirms this is actually Unraid, and that git/docker/python3 are
#      present — all three ship with a stock Unraid 7.x install (confirmed
#      directly on Spire), so a missing one usually means a genuinely
#      unusual setup worth stopping for, not something to route around.
#   2. Writes NOVAK_HOME to /boot/config/novak/novak_home. `novak` and
#      up.sh both need to know where this deployment's config/data/generated
#      files live, and $HOME (/root) is NOT a safe default the way it is on
#      macOS: Unraid's Compose Manager plugin always derives its own
#      projectDirectory from wherever docker-compose.yml itself lives
#      (confirmed by reading its Util.php directly) — so NOVAK_HOME has to
#      be that exact directory, and the only way to know it is to be told.
#   3. Symlinks scripts/novak onto PATH at /usr/local/bin/novak — root
#      always has write access here, unlike the macOS non-admin account
#      bootstrap.sh's own ~/.local/bin choice exists to route around.
#   4. Adds a line to /boot/config/go that recreates that symlink on every
#      boot. This one is NOT optional the way it would be on a normal Linux
#      box: Unraid's `/` and `/usr` are a RAM-based overlay rebuilt from the
#      flash image on every boot (confirmed directly — `mount` shows
#      `rootfs` and an `overlay` under /usr, and /boot is the only thing
#      that's real, persistent storage) — anything placed in
#      /usr/local/bin without this step vanishes at the next reboot.
#
# Idempotent — safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }
fail() { printf '\033[31m✋ %s\033[0m\n' "$*" >&2; exit 1; }

step "Checking this is Unraid, run as root"
[ "$(id -u)" = "0" ] || fail "Run this as root — Unraid has no sudo/admin split to route around."
[ -f /etc/unraid-version ] || warn "No /etc/unraid-version found — proceeding anyway, but this script assumes Unraid's layout (/boot as the persistent flash device, Compose Manager's plugin conventions)."

step "Checking git, docker, python3"
MISSING=()
command -v git    >/dev/null 2>&1 || MISSING+=("git")
command -v docker >/dev/null 2>&1 || MISSING+=("docker")
command -v python3 >/dev/null 2>&1 || MISSING+=("python3")
if [ ${#MISSING[@]} -gt 0 ]; then
  fail "Missing: ${MISSING[*]}. All three ship with a stock Unraid 7.x install — install via Community Applications if genuinely absent."
fi
echo "git, docker, python3 all present"

step "Where does this deployment's config/data live?"
# The Compose Manager PROJECT DIRECTORY — where docker-compose.yml is
# registered from, NOT the git checkout (REPO_DIR). If that project
# doesn't exist yet, create the directory now and register it with Compose
# Manager afterward (this script does not do that part — it's a one-time
# UI/CLI step better done deliberately than guessed at, see the printed
# next-steps below).
DEFAULT_HOME="/mnt/cache/appdata/stacks/Novak"
if [ -n "${NOVAK_HOME:-}" ]; then
  TARGET_HOME="$NOVAK_HOME"
elif [ -f /boot/config/novak/novak_home ]; then
  TARGET_HOME="$(cat /boot/config/novak/novak_home)"
  echo "Using existing marker: $TARGET_HOME"
else
  read -rp "NOVAK_HOME (Compose Manager project directory) [$DEFAULT_HOME]: " TARGET_HOME
  TARGET_HOME="${TARGET_HOME:-$DEFAULT_HOME}"
fi

mkdir -p "$TARGET_HOME"
mkdir -p /boot/config/novak
printf '%s' "$TARGET_HOME" > /boot/config/novak/novak_home
grn() { printf '\033[32m%s\033[0m\n' "$*"; }
grn "NOVAK_HOME set to $TARGET_HOME (persisted at /boot/config/novak/novak_home)"

if [ ! -e "$TARGET_HOME/docker-compose.yml" ]; then
  ln -sf "$REPO_DIR/docker-compose.yml" "$TARGET_HOME/docker-compose.yml"
  echo "Symlinked docker-compose.yml into $TARGET_HOME (Compose Manager's own"
  echo "projectDirectory always follows wherever this file lives)"
fi

step "Linking the novak CLI onto PATH"
ln -sf "$REPO_DIR/scripts/novak" /usr/local/bin/novak
grn "novak -> $(readlink -f /usr/local/bin/novak)"

step "Persisting that symlink across reboots"
GO_LINE="ln -sf \"$REPO_DIR/scripts/novak\" /usr/local/bin/novak # novak CLI (bootstrap-unraid.sh)"
if grep -qF "novak CLI (bootstrap-unraid.sh)" /boot/config/go 2>/dev/null; then
  # Idempotent: replace the existing line rather than duplicate it, in case
  # REPO_DIR moved since the last run.
  tmp="$(mktemp)"
  grep -vF "novak CLI (bootstrap-unraid.sh)" /boot/config/go > "$tmp"
  printf '%s\n' "$GO_LINE" >> "$tmp"
  mv "$tmp" /boot/config/go
  chmod +x /boot/config/go
  grn "Updated the existing /boot/config/go line"
else
  printf '%s\n' "$GO_LINE" >> /boot/config/go
  chmod +x /boot/config/go
  grn "Added to /boot/config/go — the symlink will survive a reboot"
fi

step "Done"
echo "  NOVAK_HOME  $TARGET_HOME"
echo "  novak CLI   /usr/local/bin/novak -> $REPO_DIR/scripts/novak"
echo
bold "Next steps (not automated — deliberate, one-time, worth doing by hand):"
echo "  1. novak up          — seeds $TARGET_HOME/.env from .env.example on first run"
echo "  2. Fill in $TARGET_HOME/.env (novak status shows what's still needed)"
echo "  3. novak secret set <VAR> for each secret novak status lists as missing"
echo "  4. Register $TARGET_HOME as a Compose Manager project (Docker tab ->"
echo "     Compose Manager -> Add New Stack -> Indirect Config File, pointed"
echo "     at $TARGET_HOME/docker-compose.yml) if it isn't registered already"
echo "  5. novak checklist   — phase-by-phase walk-through, with real checks"
