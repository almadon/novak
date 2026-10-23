# Shared variable inventory. Sourced by scripts/up.sh and scripts/novak so the
# two can never disagree about what is a secret and what must be edited.
#
# SECRET_VARS      resolved from the macOS Keychain (novak/<VAR>); the value in
#                  .env is a placeholder that is never used.
# REQUIRED_EDITS   must hold a real value in .env before the stack will start.
#                  Keep this list minimal: it may only contain variables the
#                  whole stack cannot function without. A variable used by a
#                  single MCP server or extension does NOT belong here — those
#                  degrade individually in the reconciler, which skips a server
#                  whose variables are unset and logs why. One unconfigured
#                  integration must never stop the other services from starting.
# CONSOLE_VARS     only required when the optional console is in use.

SECRET_VARS=(
  OMLX_API_KEY
  ROUTER_API_KEY
  HINDSIGHT_API_KEY
  OUTLINE_EVERYTHING_API_KEY
  VIKUNJA_API_TOKEN
  BRAVE_API_KEY
  OPEN_TERMINAL_API_KEY
  CONSOLE_AUTH_SECRET
  OIDC_CLIENT_SECRET
  OWUI_OIDC_CLIENT_SECRET
  WEBUI_SECRET_KEY
  HA_DRIFT_TOKEN
  TINYAUTH_OIDC_CLIENT_SECRET
  INGEST_TOKEN
  INGEST_HA_TOKEN
  INGEST_GATEWAY_KEY
  OWUI_ADMIN_API_KEY
  OWUI_GATEWAY_KEY
  GATEWAY_HA_TOKEN
)

# HOST_NAME alone: every service builds its URLs from it. VIKUNJA_URL used to
# be here, which meant a task tracker nothing in docker-compose.yml depends on
# could block Whisper, Piper and the console from starting.
REQUIRED_EDITS=(HOST_NAME)
CONSOLE_EDITS=(OIDC_ISSUER OIDC_CLIENT_ID)
CONSOLE_SECRETS=(CONSOLE_AUTH_SECRET OIDC_CLIENT_SECRET)
# TinyAuth wants each OIDC endpoint spelled out, not a discovery document —
# it does not do discovery the way Open WebUI and the console's own OIDC
# libraries do. All three plus the client id come from Pocket ID's
# /.well-known/openid-configuration; see docs/proxy.md.
PORTAL_EDITS=(PORTAL_APPURL TINYAUTH_OIDC_CLIENT_ID TINYAUTH_OIDC_AUTH_URL
  TINYAUTH_OIDC_TOKEN_URL TINYAUTH_OIDC_USERINFO_URL)
PORTAL_SECRETS=(TINYAUTH_OIDC_CLIENT_SECRET)
# The router (decision #21) needs its own key (decision #59): LiteLLM refuses to
# start without one, and clients present it. An oMLX engine still needs
# OMLX_API_KEY, which the router passes through. ROUTER_EDITS is empty on
# purpose, not omitted: OMLX_PORT and
# ROUTER_PORT both have safe defaults, so nothing about this integration
# needs a human to type a value in before it can start, only the one
# secret to exist — but up.sh's gating loop expects the array to exist
# under set -u, same as every other optional profile.
ROUTER_EDITS=()
ROUTER_SECRETS=(ROUTER_API_KEY)
# Ingest (decision #57) is an optional extension: INGEST_ENABLED=true turns it
# on, and INGEST_TOKEN (the bearer token adapters send) must exist. The Home
# Assistant token is only for the approval notification, so it degrades on its
# own and is not required here.
INGEST_EDITS=()
INGEST_SECRETS=(INGEST_TOKEN)

# Secrets without which the stack must not start at all.
CORE_SECRETS=(HINDSIGHT_API_KEY)

# Who else needs to know a secret's value decides how it can be set.
#
# EXTERNAL_SECRETS  owned by another system — oMLX's own config, Pocket ID,
#                   Outline, Vikunja, Tududi. The value must MATCH what that
#                   system already has, so generating one is not a shortcut,
#                   it is a silent outage: the service simply starts refusing
#                   us. `novak secret set --generate` refuses these outright.
#                   HA_DRIFT_TOKEN belongs here too, and deliberately does not
#                   reuse an MCP token (decision #44/#52): it's a long-lived
#                   access token from a dedicated, non-admin HA user, created
#                   for `novak drift --live`'s HA-side persona check
#                   (reconciler/ha_persona_drift.py) alone — see
#                   docs/home-assistant.md for exactly where to create it.
#                   HA tokens carry no scope of their own, so the read-only
#                   property comes entirely from the user account behind it,
#                   not from anything this repo can enforce.
#
# SHARED_SECRETS    we generate them, but a human has to paste them somewhere
#                   else afterwards — HINDSIGHT_API_KEY is the bearer token
#                   Open WebUI and Home Assistant register the MCP endpoint
#                   with. Generating is fine; never being able to read it back
#                   is not, hence `novak secret show`.
#
# Anything in SECRET_VARS that is in neither list is internal: we generate it,
# one container reads it, and nobody ever needs to see it. CONSOLE_AUTH_SECRET
# signs the console's JWTs and is exactly that. WEBUI_SECRET_KEY is the same
# shape for Open WebUI: left unset, it generates its own random key at every
# container startup, which invalidates every existing session (JWT) on every
# restart or recreate — pinning it here is what makes logins survive `novak
# up`/`novak restart open-webui`.
EXTERNAL_SECRETS=(
  OMLX_API_KEY
  OIDC_CLIENT_SECRET
  OWUI_OIDC_CLIENT_SECRET
  HA_DRIFT_TOKEN
  OUTLINE_EVERYTHING_API_KEY
  VIKUNJA_API_TOKEN
  BRAVE_API_KEY
  TINYAUTH_OIDC_CLIENT_SECRET
  INGEST_HA_TOKEN
  INGEST_GATEWAY_KEY
  OWUI_ADMIN_API_KEY
  OWUI_GATEWAY_KEY
  GATEWAY_HA_TOKEN
)
# OPEN_TERMINAL_API_KEY is the same shape as HINDSIGHT_API_KEY: we generate
# it, the container reads it, and a human then has to paste the same value
# into Open WebUI's Admin -> Settings -> Integrations -> Open Terminal —
# there's no registry-driven wiring for it, see registry/mcp-servers.yaml.
SHARED_SECRETS=(HINDSIGHT_API_KEY OPEN_TERMINAL_API_KEY INGEST_TOKEN ROUTER_API_KEY)

# Credentials added with `novak add` (a second Outline, another Tududi) live in
# the deployed registry, not in the lists above, so the CLI would not know they
# are secrets. Read their names from the registry. They belong to other
# systems, so they can be stored but never generated. Needs PyYAML (the
# deployment's venv has it); silently adds nothing if it cannot run.
if [ -n "${NOVAK_HOME:-}" ] && [ -f "${NOVAK_HOME}/registry/mcp-servers.yaml" ] && [ -n "${REPO_DIR:-}" ]; then
  _novak_py="$NOVAK_HOME/.venv/bin/python"
  [ -x "$_novak_py" ] || _novak_py="$(command -v python3 || true)"
  if [ -n "$_novak_py" ]; then
    while IFS= read -r _novak_v; do
      [ -n "$_novak_v" ] || continue
      case " ${SECRET_VARS[*]} " in *" $_novak_v "*) ;; *)
        SECRET_VARS+=("$_novak_v"); EXTERNAL_SECRETS+=("$_novak_v") ;;
      esac
    done < <(NOVAK_HOME="$NOVAK_HOME" "$_novak_py" "$REPO_DIR/reconciler/instances.py" secret-vars 2>/dev/null || true)
  fi
  unset _novak_py _novak_v
fi

# What each built-in secret belongs to, for `novak secret list`. Variables
# added by `novak add` are described from the registry instead.
secret_desc() {
  case "$1" in
    OMLX_API_KEY)               echo "oMLX inference engine key (Mac host only)" ;;
    ROUTER_API_KEY)             echo "Router: the one key Open WebUI, Hindsight, ingest and HA present to it" ;;
    HINDSIGHT_API_KEY)          echo "Hindsight: the one tenant key every bank, the console, Open WebUI and HA use" ;;
    BRAVE_API_KEY)              echo "Brave Search: key for the web-search tool" ;;
    OPEN_TERMINAL_API_KEY)      echo "Open Terminal (code sandbox): also pasted into Open WebUI" ;;
    CONSOLE_AUTH_SECRET)        echo "Konzol (console): signs its login session cookies. Internal, never typed anywhere" ;;
    OIDC_CLIENT_SECRET)         echo "Konzol (console): its client secret in Pocket ID. Copy from Pocket ID" ;;
    OWUI_OIDC_CLIENT_SECRET)    echo "Open WebUI: its client secret in Pocket ID. Copy from Pocket ID" ;;
    WEBUI_SECRET_KEY)           echo "Open WebUI: signs its session tokens. Internal, keeps logins across restarts" ;;
    TINYAUTH_OIDC_CLIENT_SECRET) echo "Portal (TinyAuth): its client secret in Pocket ID. Copy from Pocket ID" ;;
    HA_DRIFT_TOKEN)             echo "Home Assistant: read-only token for 'novak drift --live'" ;;
    INGEST_TOKEN)               echo "Ingest: bearer token recorders and adapters send" ;;
    OWUI_ADMIN_API_KEY)         echo "Open WebUI: an admin's API key, for 'novak owui' (Settings, Account, API keys)" ;;
    OWUI_GATEWAY_KEY)           echo "Open WebUI: the gateway client key it presents (novak gateway client open-webui)" ;;
    INGEST_GATEWAY_KEY)         echo "Ingest: trusted gateway client key (novak gateway client ingest)" ;;
    INGEST_HA_TOKEN)            echo "Ingest: Home Assistant token for approval notifications" ;;
    GATEWAY_HA_TOKEN)           echo "Gateway: Home Assistant token for removal-confirmation notifications" ;;
    *)                          return 1 ;;
  esac
}

PLACEHOLDERS='^(EDIT-ME|set-in-keychain|changeme)$'
