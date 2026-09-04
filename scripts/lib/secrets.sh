# Cross-platform secret storage. Sourced by scripts/novak and scripts/up.sh
# so both ever have exactly one idea of where a secret actually lives.
#
# Darwin (Mitochon and any other Mac): the macOS login Keychain, item
# "novak/<VAR>". The value in .env for these is always the placeholder
# "set-in-keychain" — never read, never trusted.
#
# Linux (Spire and any other Unraid/Linux host): there is no OS keychain to
# use headlessly — Unraid never has a logged-in desktop session to unlock
# one, and asking for a per-secret system daemon (gnome-keyring, `pass`+GPG,
# systemd-creds) would be real new infrastructure for one CLI, on a platform
# whose own real deployment (Spire, decision #28/#33) already stores these
# as plain values directly in .env today. So on Linux that IS the store:
# secret_set/secret_get read and write the real value in .env, same file
# `novak config` already edits. This is a REAL, LOWER security bar than
# Keychain — say so, don't pretend otherwise — traded for something that
# works unattended on a host with no per-user session at all. File
# permissions (600, root-owned — enforced by secret_set) are what stands in
# for Keychain's OS-level encryption; there is no second factor here.
#
# NOVAK_SECRETS_PLATFORM can force a value (used by tests); otherwise it's
# `uname -s`.
NOVAK_SECRETS_PLATFORM="${NOVAK_SECRETS_PLATFORM:-$(uname -s)}"

secrets_backend_label() {
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    echo "macOS Keychain, account $(whoami)"
  else
    echo "$ENV_FILE, plaintext (no OS keychain on Linux — see scripts/lib/secrets.sh)"
  fi
}

# $1 = VAR name. Prints the value, or nothing. Never errors.
secret_get() {
  if [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ]; then
    security find-generic-password -s "novak/${1}" -w 2>/dev/null || true
  else
    [ -f "$ENV_FILE" ] || return 0
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true
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
    [ -f "$ENV_FILE" ] || return 1
    local tmp; tmp="$(mktemp)"
    if grep -qE "^${key}=" "$ENV_FILE"; then
      awk -v k="$key" -v v="$val" '
        $0 ~ "^" k "=" && !done { print k "=" v; done=1; next } { print }
      ' "$ENV_FILE" > "$tmp"
    else
      cp "$ENV_FILE" "$tmp"
      printf '%s=%s\n' "$key" "$val" >> "$tmp"
    fi
    mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
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
    [ -f "$ENV_FILE" ] || return 0
    local tmp; tmp="$(mktemp)"
    grep -vE "^${key}=" "$ENV_FILE" > "$tmp" && mv "$tmp" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
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

# Linux only: is $ENV_FILE actually locked down? Meaningful here in a way
# it isn't on Darwin, since Linux secrets live IN this file. Prints
# "ok" or a reason string.
secret_permcheck() {
  [ "$NOVAK_SECRETS_PLATFORM" = "Darwin" ] && { echo "ok"; return 0; }
  [ -f "$ENV_FILE" ] || { echo "missing"; return 0; }
  local perms; perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null)"
  case "$perms" in
    600|400) echo "ok" ;;
    *) echo "loose ($perms, not 600)" ;;
  esac
}
