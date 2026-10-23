# Cross-platform secret storage. Sourced by scripts/novak and scripts/up.sh
# so both ever have exactly one idea of where a secret actually lives.
#
# Darwin (any Mac): the macOS login Keychain, item
# "novak/<VAR>". The value in .env for these is always the placeholder
# "set-in-keychain" — never read, never trusted.
#
# Linux (Spire and any other Unraid/Linux host): there is no OS keychain to
# use headlessly — Unraid never has a logged-in desktop session to unlock
# one, and asking for a per-secret system daemon (gnome-keyring, `pass`+GPG,
# systemd-creds) would be real new infrastructure for one CLI, on a platform
# whose own real deployment (Spire, decision #28/#33) already stores these
# as plain values directly in .env today. So on Linux a file IS the store:
# `secrets.env` next to .env (decision #69), mode 600, holding nothing but
# secrets, so .env can be printed, diffed and pasted without leaking one.
# secret_get reads secrets.env and falls back to a legacy line in .env;
# secret_set writes secrets.env and removes any copy left in .env, so a
# deployment migrates one secret at a time, and `novak secret migrate` does
# the rest at once. This is a REAL, LOWER security bar than
# Keychain — say so, don't pretend otherwise — traded for something that
# works unattended on a host with no per-user session at all. File
# permissions (600, root-owned — enforced by secret_set) are what stands in
# for Keychain's OS-level encryption; there is no second factor here.
#
# NOVAK_SECRETS_PLATFORM can force a value (used by tests); otherwise it's
# `uname -s`.
NOVAK_SECRETS_PLATFORM="${NOVAK_SECRETS_PLATFORM:-$(uname -s)}"

# Where Linux secrets live: SECRETS_FILE if set, else secrets.env beside $ENV_FILE.
secrets_file() { echo "${SECRETS_FILE:-$(dirname "$ENV_FILE")/secrets.env}"; }

secrets_backend_label() {
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    echo "macOS Keychain, account $(whoami)"
  else
    echo "$(secrets_file), plaintext (no OS keychain on Linux — see scripts/lib/secrets.sh)"
  fi
}

# $1 = VAR name. Prints the value, or nothing. Never errors.
secret_get() {
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    security find-generic-password -s "novak/${1}" -w 2>/dev/null || true
  else
    local sf v; sf="$(secrets_file)"
    v=""
    [ -f "$sf" ] && v="$(grep -E "^${1}=" "$sf" 2>/dev/null | head -1 | cut -d= -f2- || true)"
    # Not migrated yet: a deployment from before secrets.env keeps its value in .env.
    [ -n "$v" ] || { [ -f "$ENV_FILE" ] && v="$(grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)"; }
    printf '%s\n' "$v"
  fi
}

# $1 = VAR name, $2 = value. Writes it. On Linux this edits .env in place
# (creating the line if the key isn't there yet — unlike `novak config set`,
# which refuses an unknown key, since a secret can legitimately be the
# first time this deployment has ever seen that name). Sets 600 permissions
# every time, not just on first write, so a secret added by hand under a
# looser umask still ends up protected.
secret_set() {
  local key="$1" val="$2"
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    security delete-generic-password -s "novak/$key" >/dev/null 2>&1 || true
    if ! printf '%s\n%s\n' "$val" "$val" |
         security add-generic-password -s "novak/$key" -a "$(whoami)" \
           -T /usr/bin/security -w >/dev/null 2>&1; then
      return 1
    fi
    [ "$(secret_get "$key")" = "$val" ] || return 1
  else
    local sf; sf="$(secrets_file)"
    # umask first: the file must never exist, even for a moment, readable by others.
    [ -f "$sf" ] || { (umask 077; : > "$sf") || return 1; }
    local tmp; tmp="$(umask 077; mktemp)"
    if grep -qE "^${key}=" "$sf"; then
      # ENVIRON, not -v: awk -v would interpret a backslash in the value as an escape.
      K="$key" V="$val" awk '
        index($0, ENVIRON["K"] "=") == 1 && !done { print ENVIRON["K"] "=" ENVIRON["V"]; done=1; next } { print }
      ' "$sf" > "$tmp"
    else
      cp "$sf" "$tmp"
      printf '%s=%s\n' "$key" "$val" >> "$tmp"
    fi
    mv "$tmp" "$sf"
    chmod 600 "$sf"
    secret_drop_legacy "$key"
  fi
}

# Linux: remove a secret's line from .env (it has moved to secrets.env, or been deleted).
secret_drop_legacy() {
  [ -f "$ENV_FILE" ] || return 0
  grep -qE "^${1}=" "$ENV_FILE" || return 0
  local tmp; tmp="$(mktemp)"
  grep -vE "^${1}=" "$ENV_FILE" > "$tmp" || true      # exit 1 just means "no lines left"
  cat "$tmp" > "$ENV_FILE"                              # in place: keeps .env's owner and mode
  rm -f "$tmp"
}

# $1 = VAR name. Same generation logic on both platforms (openssl rand),
# only the storage differs.
secret_generate() {
  local key="$1"
  command -v openssl >/dev/null 2>&1 || { echo "openssl not found" >&2; return 1; }
  local gen; gen="$(openssl rand -hex 32)"
  secret_set "$key" "$gen" || return 1
  [ "$(secret_get "$key")" = "$gen" ] || return 1
}

secret_delete() {
  local key="$1"
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    security delete-generic-password -s "novak/$key" >/dev/null 2>&1 || true
  else
    local sf; sf="$(secrets_file)"
    if [ -f "$sf" ]; then
      local tmp; tmp="$(umask 077; mktemp)"
      grep -vE "^${key}=" "$sf" > "$tmp" || true; mv "$tmp" "$sf"; chmod 600 "$sf"
    fi
    secret_drop_legacy "$key"
  fi
}

# Prints one of: clean / hangs / absent — for `novak secret verify`.
# On Darwin this actually exercises the thing that can hang (a GUI
# authorisation dialog nothing will click on an unattended boot). On Linux
# a plain .env read cannot hang — there's no daemon and no dialog — so this
# just reports present/absent; the real Linux-equivalent risk (wrong file
# permissions) is checked separately by secret_permcheck below.
secret_verify() {
  local key="$1"
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    local out rc
    out="$(perl -e 'alarm 5; exec @ARGV' security find-generic-password \
            -s "novak/$key" -w 2>/dev/null)" && rc=0 || rc=$?
    if [ "$rc" -eq 0 ] && [ -n "$out" ]; then echo "clean"
    elif [ "$rc" -eq 142 ] || [ "$rc" -eq 14 ]; then echo "hangs"
    else echo "absent"; fi
  else
    [ -n "$(secret_get "$key")" ] && echo "clean" || echo "absent"
  fi
}

# Linux only: is the secrets file actually locked down? Prints "ok" or a reason string.
# A secret still sitting in .env (not yet migrated) is reported too, because .env is the file
# people print and paste.
secret_permcheck() {
  [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ] && { echo "ok"; return 0; }
  local sf; sf="$(secrets_file)"
  [ -f "$sf" ] || { echo "missing ($sf: run novak up, or novak secret migrate)"; return 0; }
  local perms; perms="$(stat -c '%a' "$sf" 2>/dev/null || stat -f '%Lp' "$sf" 2>/dev/null)"
  case "$perms" in
    600|400) ;;
    *) echo "loose ($perms, not 600)"; return 0 ;;
  esac
  local n; n="$(secrets_in_env | wc -l | tr -d ' ')"
  [ "$n" = "0" ] && echo "ok" || echo "$n secret(s) still in $ENV_FILE: run novak secret migrate"
}

# Names in .env that hold a secret and should not: the declared secrets, plus anything named
# like one (*_KEY, *_TOKEN, *_SECRET, *_PASSWORD) so a secret added by hand is not missed.
# Reads names only, never values. Needs SECRET_VARS (scripts/lib/vars.sh).
secrets_in_env() {
  [ -f "$ENV_FILE" ] || return 0
  local name
  while IFS= read -r name; do
    if [[ "$name" =~ (_KEY|_TOKEN|_SECRET|_PASSWORD)$ ]]; then echo "$name"; continue; fi
    local v; for v in "${SECRET_VARS[@]:-}"; do [ "$v" = "$name" ] && { echo "$name"; break; }; done
  done < <(grep -oE '^[A-Z][A-Z0-9_]*=' "$ENV_FILE" | tr -d '=' | sort -u)
}

# Moves every secret in .env to secrets.env. A placeholder (set-in-keychain and friends) is
# dropped, not moved: it was never a value. Prints "moved NAME" or "dropped NAME" per name,
# never a value.
secrets_migrate() {
  local name val
  for name in $(secrets_in_env); do
    val="$(grep -E "^${name}=" "$ENV_FILE" | head -1 | cut -d= -f2-)"
    case "$val" in
      ""|set-in-keychain|EDIT-ME|changeme) secret_drop_legacy "$name"; echo "dropped $name (placeholder)" ;;
      *) if [ -n "$(grep -E "^${name}=" "$(secrets_file)" 2>/dev/null)" ]; then
           secret_drop_legacy "$name"; echo "dropped $name (secrets.env already had it)"
         else
           secret_set "$name" "$val" && [ "$(secret_get "$name")" = "$val" ] && echo "moved $name" || { echo "FAILED $name"; return 1; }
         fi ;;
    esac
  done
}
