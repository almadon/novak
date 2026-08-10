#!/usr/bin/env bash
# One-shot host setup for the Mac mini. Idempotent — safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }

step "Homebrew"
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  echo "already installed"
fi

step "OrbStack (Docker runtime)"
if ! brew list --cask orbstack >/dev/null 2>&1 && [ ! -d /Applications/OrbStack.app ]; then
  brew install --cask orbstack
else
  echo "already installed"
fi
open -a OrbStack || true

step "oMLX"
if [ ! -d /Applications/oMLX.app ] && ! command -v omlx >/dev/null 2>&1; then
  # Cask name unverified off-host — fall back to manual install if it fails.
  if ! brew install --cask omlx 2>/dev/null && ! brew install omlx 2>/dev/null; then
    warn "brew install failed — download oMLX from https://omlx.ai and install manually,"
    warn "then re-run this script."
    exit 1
  fi
else
  echo "already installed"
fi
open -a oMLX 2>/dev/null || true

step "24/7 power settings (needs sudo)"
sudo "$REPO_DIR/scripts/power.sh"

step "Login items"
warn "Manual: System Settings → General → Login Items — add OrbStack and oMLX."
warn "Manual: System Settings → Users & Groups — enable auto-login for this user"
warn "        (required for services to come back after a power failure)."

step "Environment"
if [ ! -f .env ]; then
  cp .env.example .env
  warn "Created .env from template — edit it (or add Keychain items, see docs/security.md)"
fi

step "Docker stack"
./scripts/up.sh

step "Done"
echo "Next: work through docs/deploy-checklist.md (models, oMLX settings, HA wiring)."
