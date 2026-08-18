#!/usr/bin/env bash
# Host setup that needs administrator rights. Run ONCE, as an admin user.
#
# Everything here is either system-wide or requires sudo, which is exactly why
# it is not in bootstrap.sh: the stack runs as an unprivileged `novak` account
# that can neither sudo nor write to /opt/homebrew. Splitting these means the
# service account never needs rights it shouldn't have.
#
#   sudo-capable admin:  ./scripts/bootstrap-admin.sh [--service-user novak]
#   then, as novak:      ./scripts/bootstrap.sh
#
# Idempotent — safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER=""

while [ $# -gt 0 ]; do
  case "$1" in
    --service-user) SERVICE_USER="${2:-}"; shift 2 ;;
    -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then
  echo "✋ Run this as your admin user, not with sudo — Homebrew refuses to" >&2
  echo "   install as root, and the script asks for sudo only where needed." >&2
  exit 1
fi

step "Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  echo "already installed"
fi

step "24/7 power settings (needs sudo)"
# Early and unconditional: depends on nothing, and a failure further down once
# left this machine sleeping after a minute with no autorestart — the settings
# a headless box needs most.
sudo "$REPO_DIR/scripts/power.sh"

step "OrbStack (Docker runtime)"
# Installs into /Applications, so every account on this Mac can run it. That is
# what lets the service user use Docker without being able to install anything.
if ! brew list --cask orbstack >/dev/null 2>&1 && [ ! -d /Applications/OrbStack.app ]; then
  brew install --cask orbstack
else
  echo "already installed"
fi

step "oMLX"
# Not in homebrew-core — needs its own tap.
if [ ! -d /Applications/oMLX.app ] && ! command -v omlx >/dev/null 2>&1; then
  brew tap jundot/omlx https://github.com/jundot/omlx
  if ! brew install jundot/omlx/omlx; then
    warn "brew install failed — download the .dmg from https://github.com/jundot/omlx"
    warn "and install it manually, then re-run."
    exit 1
  fi
else
  echo "already installed"
fi

if [ -n "$SERVICE_USER" ]; then
  step "FileVault unlock token for '$SERVICE_USER'"
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    warn "No such user '$SERVICE_USER' — create it first"
    warn "(System Settings → Users & Groups → Add User, type Standard), then re-run."
  elif ! fdesetup status | grep -q "FileVault is On"; then
    echo "FileVault is off — no unlock token needed."
  elif sudo fdesetup list 2>/dev/null | grep -q "^${SERVICE_USER},"; then
    echo "already enabled"
  else
    # Without this the account cannot unlock at the pre-boot screen, and remote
    # unlock via the KVM silently isn't an option — a failure you'd discover
    # during an outage. See docs/headless-operation.md.
    warn "Adding '$SERVICE_USER' to FileVault. You'll be asked for an already-enabled"
    warn "user's password, then that user's password."
    sudo fdesetup add -usertoadd "$SERVICE_USER"
    sudo fdesetup list
  fi
fi

step "Done — admin portion"
cat <<NOTE
Installed system-wide: OrbStack, oMLX. Power profile applied.

Next, as the service user${SERVICE_USER:+ ($SERVICE_USER)}:

  1. Log in to that account (its own desktop session — GUI apps need one)
  2. git clone https://github.com/almadon/novak.git ~/novak
  3. cd ~/novak && ./scripts/bootstrap.sh

That account does not need sudo, and shouldn't have it.
NOTE
