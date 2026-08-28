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
  HINDSIGHT_API_KEY
  OUTLINE_EVERYTHING_API_KEY
  TUDUDI_API_TOKEN
  VIKUNJA_API_TOKEN
  BRAVE_API_KEY
  OPEN_TERMINAL_API_KEY
  CONSOLE_AUTH_SECRET
  OIDC_CLIENT_SECRET
  OWUI_OIDC_CLIENT_SECRET
  WEBUI_SECRET_KEY
  HA_MCP_TOKEN
  TINYAUTH_OIDC_CLIENT_SECRET
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
# The router (decision #21) needs only what oMLX itself already needs —
# OMLX_API_KEY is already SECRET_VARS/EXTERNAL_SECRETS, not duplicated
# here. ROUTER_EDITS is empty on purpose, not omitted: OMLX_PORT and
# ROUTER_PORT both have safe defaults, so nothing about this integration
# needs a human to type a value in before it can start, only the one
# secret to exist — but up.sh's gating loop expects the array to exist
# under set -u, same as every other optional profile.
ROUTER_EDITS=()
ROUTER_SECRETS=(OMLX_API_KEY)

# Secrets without which the stack must not start at all.
CORE_SECRETS=(HINDSIGHT_API_KEY)

# Who else needs to know a secret's value decides how it can be set.
#
# EXTERNAL_SECRETS  owned by another system — oMLX's own config, Pocket ID,
#                   Outline, Vikunja, Tududi. The value must MATCH what that
#                   system already has, so generating one is not a shortcut,
#                   it is a silent outage: the service simply starts refusing
#                   us. `novak secret set --generate` refuses these outright.
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
  HA_MCP_TOKEN
  OUTLINE_EVERYTHING_API_KEY
  TUDUDI_API_TOKEN
  VIKUNJA_API_TOKEN
  BRAVE_API_KEY
  TINYAUTH_OIDC_CLIENT_SECRET
)
# OPEN_TERMINAL_API_KEY is the same shape as HINDSIGHT_API_KEY: we generate
# it, the container reads it, and a human then has to paste the same value
# into Open WebUI's Admin -> Settings -> Integrations -> Open Terminal —
# there's no registry-driven wiring for it, see registry/mcp-servers.yaml.
SHARED_SECRETS=(HINDSIGHT_API_KEY OPEN_TERMINAL_API_KEY)

PLACEHOLDERS='^(EDIT-ME|set-in-keychain|changeme)$'
