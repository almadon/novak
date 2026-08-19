#!/usr/bin/env bash
# Per-user setup for the account that RUNS the stack. Needs no sudo.
#
# Anything requiring administrator rights lives in bootstrap-admin.sh and is
# run once by an admin. This script only does what an unprivileged service
# account can, and checks that the admin half has happened rather than failing
# obscurely halfway through.
#
# Idempotent — safe to re-run.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

step() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m !  %s\033[0m\n' "$*"; }

step "Checking the admin setup has been done"
MISSING=()
[ -d /Applications/OrbStack.app ] || MISSING+=("OrbStack")
{ [ -d /Applications/oMLX.app ] || command -v omlx >/dev/null 2>&1; } || MISSING+=("oMLX")
pmset -g | grep -q "autorestart.*1" || warn "autorestart is not set — the Mac won't power back on after an outage"

if [ ${#MISSING[@]} -gt 0 ]; then
  cat >&2 <<MSG

✋ Missing: ${MISSING[*]}

   These install system-wide and need administrator rights, which this
   account deliberately does not have. Ask an admin to run, from their own
   account:

       ~/novak/scripts/bootstrap-admin.sh --service-user $(whoami)

   Then re-run this script. (If they don't have a checkout, any copy of this
   repo will do — it only installs system-wide software.)

MSG
  exit 1
fi
echo "OrbStack and oMLX are installed"

step "Starting OrbStack and oMLX"
# `open -a NAME` fails when Launch Services hasn't registered the app for this
# account, which is common the first time a new user logs in. The explicit
# bundle path works regardless.
for app in OrbStack oMLX; do
  if [ -d "/Applications/$app.app" ]; then
    open "/Applications/$app.app" || warn "could not launch $app — start it manually once"
  fi
done

step "Python dependency for the reconciler"
# Handled by up.sh, which builds a virtualenv under NOVAK_HOME. Not a --user
# install: those are per-account and Homebrew python refuses them outright, so
# "I installed it already" and "the script cannot see it" were both true.
if command -v python3 >/dev/null 2>&1; then
  echo "python3 present — up.sh will create its own virtualenv for PyYAML"
else
  warn "python3 not found. Install Xcode command line tools: xcode-select --install"
fi

step "Git hooks + commit template"
if [ -d .git ]; then
  git config core.hooksPath .githooks
  git config commit.template .gitmessage
  echo "commit-msg hook active (see docs/commit-style.md)"
else
  warn "Not a git checkout — skipping hook setup."
fi

step "Login items"
warn "Manual, and it must be done from THIS account:"
warn "  System Settings → General → Login Items — add OrbStack and oMLX."
# A fresh macOS account has no ~/Library/LaunchAgents, so the documented `cp`
# fails on a new service account — exactly where this script is meant to run.
# Creating it is idempotent and costs nothing; macOS would create it itself the
# first time anything registers an agent.
mkdir -p "$HOME/Library/LaunchAgents"

warn "Then install the LaunchAgent so the stack starts once Docker is ready:"
warn "  cp scripts/one.a64.novak.stack.plist ~/Library/LaunchAgents/"
warn "  launchctl load ~/Library/LaunchAgents/one.a64.novak.stack.plist"
warn "Load it AFTER your secrets are set — up.sh exits non-zero while one is"
warn "missing, and KeepAlive retries every 60s into /tmp/novak-stack.err."

step "Environment"
NOVAK_HOME="${NOVAK_HOME:-$HOME/.novak}"
if [ -f "$NOVAK_HOME/.env" ]; then
  echo "using existing config at $NOVAK_HOME/.env"
else
  warn "Config will be seeded at $NOVAK_HOME/.env on first start."
  warn "Fill it in, and add Keychain items FROM THIS ACCOUNT — the login"
  warn "keychain is per-user, so secrets added elsewhere won't be visible here."
fi

step "Docker stack"
# launch-stack.sh, not up.sh: `open` returns as soon as OrbStack launches, but
# its VM takes tens of seconds to start listening on the docker socket. Going
# straight to up.sh raced that and failed with an EOF from the socket.
./scripts/launch-stack.sh

step "Done"
echo "Next: work through docs/deploy-checklist.md (models, oMLX settings, HA wiring)."
echo "For unattended restarts after a reboot or power cut, see"
echo "docs/headless-operation.md."
