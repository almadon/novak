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
# `open -a OrbStack` fails when the app isn't registered with Launch Services
# (fresh install, or installed somewhere other than /Applications), which is
# what "Unable to find application named 'OrbStack'" means. Try the explicit
# bundle path first, since that works regardless of registration.
if [ -d /Applications/OrbStack.app ]; then
  open /Applications/OrbStack.app
elif ! open -a OrbStack 2>/dev/null; then
  warn "OrbStack installed but could not be launched — start it manually once,"
  warn "then re-run. Docker commands will fail until it has run at least once."
fi

step "oMLX"
# oMLX is not in homebrew-core — it needs its own tap. (An earlier version of
# this script guessed `brew install --cask omlx`, which does not exist.)
if [ ! -d /Applications/oMLX.app ] && ! command -v omlx >/dev/null 2>&1; then
  brew tap jundot/omlx https://github.com/jundot/omlx
  if ! brew install jundot/omlx/omlx; then
    warn "brew install failed — download the .dmg from https://github.com/jundot/omlx"
    warn "and install manually, then re-run this script."
    exit 1
  fi
else
  echo "already installed"
fi
if [ -d /Applications/oMLX.app ]; then
  open /Applications/oMLX.app
elif ! open -a oMLX 2>/dev/null; then
  warn "oMLX installed but could not be launched — start it manually once."
fi

step "24/7 power settings (needs sudo)"
sudo "$REPO_DIR/scripts/power.sh"

step "Login items"
warn "Manual: System Settings → General → Login Items — add OrbStack and oMLX."
warn "Manual: System Settings → Users & Groups — enable auto-login for this user"
warn "        (required for services to come back after a power failure)."

step "Git hooks + commit template"
# Hooks live in .git/hooks, which isn't tracked; pointing core.hooksPath at a
# tracked directory is what makes the commit convention shareable.
if [ -d .git ]; then
  git config core.hooksPath .githooks
  git config commit.template .gitmessage
  echo "commit-msg hook active (see docs/commit-style.md)"
else
  warn "Not a git checkout — skipping hook setup."
fi

step "Environment"
if [ ! -f .env ]; then
  cp .env.example .env
  warn "Created .env from template — edit it (or add Keychain items, see docs/security.md)"
fi

step "Docker stack"
./scripts/up.sh

step "Done"
echo "Next: work through docs/deploy-checklist.md (models, oMLX settings, HA wiring)."
