#!/usr/bin/env bash
# Start (or update) the stack. Secrets come from scripts/lib/secrets.sh —
# macOS Keychain items named "novak/<VAR>" on Darwin, real values directly
# in .env on Linux (no OS keychain to use headlessly there). Add one with
# `novak secret set <VAR>` on either platform; see that file for the
# underlying mechanism and why the two platforms differ.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_DIR
# shellcheck source=lib/ui.sh
source "$REPO_DIR/scripts/lib/ui.sh"
# shellcheck source=lib/rev.sh
source "$REPO_DIR/scripts/lib/rev.sh"

PLATFORM="$(uname -s)"

# Runtime lives outside the checkout. The repo holds definitions; NOVAK_HOME
# holds this deployment's config, data and generated files — so `git pull`
# never fights a running stack, and the checkout stays clean.
if [ -z "${NOVAK_HOME:-}" ]; then
  if [ "$PLATFORM" = "Darwin" ]; then
    NOVAK_HOME="$HOME/.novak"
  elif [ -f /boot/config/novak/novak_home ]; then
    NOVAK_HOME="$(cat /boot/config/novak/novak_home)"
  else
    ui_err "NOVAK_HOME is not set, and no /boot/config/novak/novak_home marker"
    ui_hint "exists to default it from. Run scripts/bootstrap-unraid.sh once,"
    ui_hint "or export NOVAK_HOME explicitly."
    exit 1
  fi
fi

# Seed on first run. Existing files are never overwritten: your config and your
# registry belong to you once created.
mkdir -p "$NOVAK_HOME/registry" "$NOVAK_HOME/wakeword/models"
if [ ! -f "$NOVAK_HOME/.env" ]; then
  cp "$REPO_DIR/.env.example" "$NOVAK_HOME/.env"
  ui_seeded "$NOVAK_HOME/.env" "(from .env.example: fill it in before this will start)"
fi
if [ ! -f "$NOVAK_HOME/registry/mcp-servers.yaml" ]; then
  cp "$REPO_DIR/registry/mcp-servers.yaml" "$NOVAK_HOME/registry/mcp-servers.yaml"
  ui_seeded "$NOVAK_HOME/registry/mcp-servers.yaml" "(edit it there, not in the repo)"
fi

for f in people.yaml gateway.yaml openwebui.yaml; do
  if [ ! -f "$NOVAK_HOME/registry/$f" ]; then
    cp "$REPO_DIR/registry/$f" "$NOVAK_HOME/registry/$f"
    ui_seeded "$NOVAK_HOME/registry/$f" "(edit it there, not in the repo)"
  fi
done
if [ ! -f "$NOVAK_HOME/registry/ingest.yaml" ]; then
  cp "$REPO_DIR/registry/ingest.yaml" "$NOVAK_HOME/registry/ingest.yaml"
  ui_seeded "$NOVAK_HOME/registry/ingest.yaml" "(edit it there, not in the repo)"
fi

cd "$NOVAK_HOME"
ENV_FILE="$NOVAK_HOME/.env"

# Every secret the stack needs. Anything listed here that is missing from both
# the secret store and .env will fall back to the .env.example placeholder,
# which is why the check below exists — a console running with
# AUTH_SECRET=changeme is worse than one that refuses to start.
# shellcheck source=lib/vars.sh
source "$REPO_DIR/scripts/lib/vars.sh"
# shellcheck source=lib/secrets.sh
source "$REPO_DIR/scripts/lib/secrets.sh"

loaded_secrets=()
for var in "${SECRET_VARS[@]}"; do
  if val="$(secret_get "$var")" && [ -n "$val" ]; then
    export "${var}=${val}"
    loaded_secrets+=("$var")
  fi
done
ui_section "🔐" "Secrets"
if [ "$PLATFORM" = "Darwin" ]; then _secret_src="the Keychain"; else _secret_src="$ENV_FILE"; fi
ui_ok "${#loaded_secrets[@]} loaded from ${_secret_src}"
if [ "${NOVAK_VERBOSE:-}" = "1" ]; then
  for var in "${loaded_secrets[@]}"; do ui_dim "🔑 ${var}"; done
else
  ui_dim "${loaded_secrets[*]}"
fi

# Two different kinds of unconfigured value, reported separately because the
# fix differs: EDIT-ME means "put a real value in .env", set-in-keychain means
# "the Keychain lookup above found nothing".
# || true matters: under set -e, a variable declared in vars.sh but not yet
# a line in an existing deployment's .env (exactly what happens the first
# time a new optional-profile variable is added, before that .env has been
# regenerated) makes grep return no match, which is exit 1, which kills the
# whole script here rather than just leaving that one profile unconfigured.
# Found by adding PORTAL_EDITS/PORTAL_SECRETS to a deployment whose .env
# predated them; scripts/novak's own envval() already had this guard.
envval() { grep -E "^${1}=" "$NOVAK_HOME/.env" 2>/dev/null | head -1 | cut -d= -f2- || true ; }

# The console is optional (docs/deploy-checklist.md phase 9 calls it genuinely
# skippable), so its configuration must not gate anything else. Rather than
# demand its values, decide here whether it is configured; if not, it is left
# out and everything else starts. Same rule the reconciler applies to an
# unconfigured MCP server.
console_missing=()
for var in "${CONSOLE_EDITS[@]}"; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) console_missing+=("$var") ;; esac
done
for var in "${CONSOLE_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) console_missing+=("$var") ;; esac
done

portal_missing=()
for var in "${PORTAL_EDITS[@]}"; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) portal_missing+=("$var") ;; esac
done
for var in "${PORTAL_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) portal_missing+=("$var") ;; esac
done

router_missing=()
for var in ${ROUTER_EDITS[@]+"${ROUTER_EDITS[@]}"}; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) router_missing+=("$var") ;; esac
done
for var in "${ROUTER_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) router_missing+=("$var") ;; esac
done

ingest_missing=()
for var in ${INGEST_EDITS[@]+"${INGEST_EDITS[@]}"}; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) ingest_missing+=("$var") ;; esac
done
for var in "${INGEST_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) ingest_missing+=("$var") ;; esac
done

unedited=()
for var in "${REQUIRED_EDITS[@]}"; do
  v="$(envval "$var")"
  case "$v" in ""|EDIT-ME|changeme) unedited+=("$var") ;; esac
done
if [ ${#unedited[@]} -gt 0 ]; then
  echo "" >&2
  ui_err "These need real values in $NOVAK_HOME/.env:"
  for var in "${unedited[@]}"; do ui_cmd "$var"; done
  echo "" >&2
  ui_hint "HOST_NAME is how other machines reach this one (a Tailscale name works"
  ui_hint "well). See the comments in that file — it says which lines to edit and"
  ui_hint "which to leave alone."
  echo "" >&2
  exit 1
fi

# Secrets: these must have resolved from the Keychain. A value still reading
# set-in-keychain means the lookup found nothing — usually because it was added
# under a different account, since the login keychain is per-user.
REQUIRED_SECRETS=("${CORE_SECRETS[@]}")

missing=()
for var in "${REQUIRED_SECRETS[@]}"; do
  v="${!var:-$(envval "$var")}"
  case "$v" in ""|set-in-keychain|changeme) missing+=("$var") ;; esac
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "" >&2
  if [ "$PLATFORM" = "Darwin" ]; then
    ui_err "These secrets were not found in the Keychain:"
    for var in "${missing[@]}"; do
      ui_cmd "security add-generic-password -s \"novak/${var}\" -a $(whoami) -w"
    done
    echo "" >&2
    ui_hint "Run those as $(whoami) — the login keychain is per-user, so items"
    ui_hint "added under another account are invisible here."
  else
    ui_err "These secrets are not set:"
    for var in "${missing[@]}"; do
      ui_cmd "novak secret set ${var}"
    done
  fi
  echo "" >&2
  exit 1
fi

# The reconciler needs PyYAML. Rather than depend on whichever python3 and
# pip3 happen to be first on PATH — they are often different interpreters, and
# `pip --user` is per-account and blocked outright on Homebrew python (PEP 668)
# — keep a small virtualenv in NOVAK_HOME. Self-healing, and immune to the
# system Python being upgraded or replaced underneath it.
VENV="$NOVAK_HOME/.venv"
PY="$VENV/bin/python3"

if [ ! -x "$PY" ] || ! "$PY" -c 'import yaml' 2>/dev/null; then
  SYS_PY=$(command -v python3 || true)
  if [ -z "$SYS_PY" ]; then
    if [ "$PLATFORM" = "Darwin" ]; then
      ui_err "python3 not found. Install Xcode command line tools:"
      ui_cmd "xcode-select --install"
    else
      ui_err "python3 not found. Unraid ships it at /usr/bin/python3 —"
      ui_hint "check PATH, or install a Python plugin via Community Applications."
    fi
    exit 1
  fi
  ui_section "🐍" "Python"
  ui_info "preparing $VENV (one-off)"
  if ! "$SYS_PY" -m venv "$VENV" 2>/dev/null; then
    ui_err "could not create a virtualenv with $SYS_PY"
    ui_hint "Try: $SYS_PY -m ensurepip --upgrade"
    exit 1
  fi
  if ! "$PY" -m pip install --quiet --upgrade pyyaml; then
    ui_err "could not install PyYAML into $VENV"
    ui_hint "If this machine is offline, install it manually:"
    ui_cmd "$PY -m pip install pyyaml"
    exit 1
  fi
  ui_ok "PyYAML ready"
fi
# Compose reads COMPOSE_PROFILES from the environment, and the reconciler is
# what runs `docker compose up`, so this is all it takes to include or omit
# any optional profile — no reconciler change, and nothing here needs to
# know about them beyond this check. Additive (comma-joined) since more
# than one can be active at once.
profiles=()
if [ ${#console_missing[@]} -eq 0 ]; then
  profiles+=(console)
else
  ui_skip_later "console" "not configured: ${console_missing[*]}"
fi
if [ ${#portal_missing[@]} -eq 0 ]; then
  profiles+=(portal)
else
  ui_skip_later "portal" "not configured: ${portal_missing[*]}"
fi
if [ ${#router_missing[@]} -eq 0 ]; then
  profiles+=(router)
else
  ui_skip_later "router" "not configured: ${router_missing[*]}"
fi
# Ollama is the Linux/GPU engine (docker-compose.yml's ollama service), so it
# is part of the stack whenever an engine in registry/engines.yaml actually
# points at this host's Ollama. It stays out when engines point elsewhere
# (oMLX on a Mac, or an Ollama on another machine), which is why it sits
# behind a profile at all. Nothing else started it on Unraid before this:
# Compose Manager did, through its own profiles file.
ollama_wanted="$("$PY" - "$NOVAK_HOME" <<'PYEOF'
import os, re, sys
import yaml
home = sys.argv[1]
env = {}
for line in open(os.path.join(home, ".env")):
    m = re.match(r"([A-Z0-9_]+)=(.*)", line.strip())
    if m:
        env[m.group(1)] = m.group(2)
path = os.path.join(home, "registry", "engines.yaml")
if not os.path.exists(path):
    sys.exit(0)
port = env.get("OLLAMA_PORT", "11434")
local = {"ollama", "host.docker.internal", "localhost", "127.0.0.1", env.get("HOST_NAME", "")}
for engine in (yaml.safe_load(open(path)) or {}).get("engines") or []:
    url = env.get(engine.get("base_url_var", ""), "")
    m = re.match(r"https?://([^:/]+)(?::(\d+))?", url)
    if m and m.group(1) in local and (m.group(1) == "ollama" or (m.group(2) or "80") == port):
        print("yes")
        break
PYEOF
)"
if [ "$ollama_wanted" = "yes" ]; then
  profiles+=(ollama)
fi
# Ingest is an extension, so it is opt-in (INGEST_ENABLED=true) as well as
# needing its token; unlike the profiles above, leaving it unset is not an
# unconfigured feature worth warning about.
if [ "$(envval INGEST_ENABLED)" = "true" ]; then
  if [ ${#ingest_missing[@]} -eq 0 ]; then
    profiles+=(ingest)
  else
    ui_skip_later "ingest" "not configured: ${ingest_missing[*]}"
  fi
fi
# The gateway is an extension too: opt-in with GATEWAY_ENABLED=true. It is given
# only the credentials its directory names, in a mode-600 file.
if [ "$(envval GATEWAY_ENABLED)" = "true" ]; then
  profiles+=(gateway)
  NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/gateway_env.py" || ui_warn "could not write gateway.env: the gateway will start without credentials"
fi
if [ ${#profiles[@]} -gt 0 ]; then
  export COMPOSE_PROFILES
  COMPOSE_PROFILES="$(IFS=,; echo "${profiles[*]}")"
fi

ui_section "🧩" "Optional services"
if [ ${#profiles[@]} -gt 0 ]; then ui_ok "$(ui_c 32 "on:") ${profiles[*]}"; else ui_info "none enabled"; fi
if [ ${#ui_skipped_names[@]} -gt 0 ]; then
  for i in "${!ui_skipped_names[@]}"; do ui_skip "${ui_skipped_names[$i]}" "${ui_skipped_why[$i]}"; done
  ui_hint "everything else starts; set those and re-run to add them."
fi

# Bind-mounted code (see lib/rev.sh): a pull that changes it must recreate its service.
export GATEWAY_CODE_REV INGEST_CODE_REV PERSONA_CODE_REV ROUTER_CODE_REV
GATEWAY_CODE_REV="$(code_rev gateway/novak_gateway gateway/Dockerfile)"
INGEST_CODE_REV="$(code_rev ingest/novak_ingest ingest/Dockerfile)"
PERSONA_CODE_REV="$(code_rev persona/server.py)"
ROUTER_CODE_REV="$(code_rev router)"

NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/reconcile.py"

# oMLX profiles. Deliberately non-fatal: oMLX is a host app this script does not
# manage, and at boot the LaunchAgent may well reach here before it is up.
# Failing the whole stack because an inference server is not ready yet would be
# the same mistake as the console gate. It is a no-op when nothing differs, so
# running it every time costs nothing and never restarts oMLX needlessly.
#
# Only when an engine actually points at oMLX: a deployment on Ollama (Spire)
# has no oMLX to reach, and reporting "cannot reach oMLX" on every run was noise.
omlx_wanted="$("$PY" - "$NOVAK_HOME" <<'PYEOF'
import os, re, sys
import yaml
home = sys.argv[1]
env = {}
for line in open(os.path.join(home, ".env")):
    m = re.match(r"([A-Z0-9_]+)=(.*)", line.strip())
    if m:
        env[m.group(1)] = m.group(2)
port = env.get("OMLX_PORT", "8000")
urls = [env.get("DEFAULT_ENGINE_BASE_URL", "")]
names = []
for path in (os.path.join(home, "registry", "engines.yaml"),):
    if os.path.exists(path):
        for e in (yaml.safe_load(open(path)) or {}).get("engines") or []:
            names.append(e.get("name", ""))
            urls.append(env.get(e.get("base_url_var", ""), ""))
for url in urls:
    m = re.match(r"https?://([^:/]+)(?::(\d+))?", url or "")
    if m and m.group(1) != "ollama" and (m.group(2) or "80") == port:
        print("yes"); break
else:
    if any("omlx" in n.lower() for n in names):
        print("yes")
PYEOF
)"
if [ "$omlx_wanted" = "yes" ] && [ -f "$REPO_DIR/reconciler/omlx_apply.py" ]; then
  ui_section "🧠" "oMLX"
  if ! NOVAK_HOME="$NOVAK_HOME" "$PY" "$REPO_DIR/reconciler/omlx_apply.py"; then
    ui_warn "oMLX profiles not applied: run 'novak omlx apply' once it is up."
  fi
fi

ui_section "📋" "Status"
_ps="$(docker compose \
  --project-directory "$NOVAK_HOME" \
  --env-file "$NOVAK_HOME/.env" \
  -f "$REPO_DIR/docker-compose.yml" \
  -f "$NOVAK_HOME/docker-compose.mcp.yml" \
  ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}')"
if ui_color; then
  # header bold; healthy/up green; anything unhealthy, restarting or exited red.
  printf '%s\n' "$_ps" | awk '
    NR == 1 { printf "\033[1m%s\033[0m\n", $0; next }
    /unhealthy|Exited|Restarting|Dead/ { printf "\033[31m✗ %s\033[0m\n", $0; next }
    /healthy|Up/ { printf "\033[32m✓\033[0m %s\n", $0; next }
    { printf "  %s\n", $0 }' | sed 's/^\(\x1b\[1m\)/  \1/'
else
  printf '%s\n' "$_ps"
fi
