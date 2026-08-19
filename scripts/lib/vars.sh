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
  CONSOLE_AUTH_SECRET
  OIDC_CLIENT_SECRET
)

# HOST_NAME alone: every service builds its URLs from it. VIKUNJA_URL used to
# be here, which meant a task tracker nothing in docker-compose.yml depends on
# could block Whisper, Piper and the console from starting.
REQUIRED_EDITS=(HOST_NAME)
CONSOLE_EDITS=(OIDC_ISSUER OIDC_CLIENT_ID)
CONSOLE_SECRETS=(CONSOLE_AUTH_SECRET OIDC_CLIENT_SECRET)

# Secrets without which the stack must not start at all.
CORE_SECRETS=(HINDSIGHT_API_KEY)

PLACEHOLDERS='^(EDIT-ME|set-in-keychain|changeme)$'
