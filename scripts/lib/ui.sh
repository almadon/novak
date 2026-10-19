# Terminal output helpers: colour, emoji and sections for up.sh.
#
# Colour is on when stdout or stderr is a terminal, or FORCE_COLOR is set, and
# off when NO_COLOR is set, so output piped into a file or another program stays
# plain. Warnings and errors go to stderr; sections and good news to stdout.

ui_color() {
  [ -z "${NO_COLOR:-}" ] || return 1
  [ -n "${FORCE_COLOR:-}" ] || [ -t 1 ] || [ -t 2 ]
}

# ui_c CODE TEXT: TEXT in an ANSI style (1 bold, 2 dim, 31 red, 32 green, 33 yellow, 36 cyan).
ui_c() {
  if ui_color; then printf '\033[%sm%s\033[0m' "$1" "$2"; else printf '%s' "$2"; fi
}

# ui_section EMOJI TITLE: a blank line, then a rule with a title.
ui_section() {
  local head="━━ $1  $2 " pad
  pad="$(printf '%*s' $(( 62 - ${#head} > 3 ? 62 - ${#head} : 3 )) '' | sed 's/ /━/g')"
  printf '\n'; ui_c '1;36' "${head}${pad}"; printf '\n'
}

ui_ok()   { printf '  ✅ %s\n' "$*"; }
ui_info() { printf '  ℹ️  %s\n' "$(ui_c 2 "$*")"; }
ui_dim()  { printf '%s\n' "$*" | fold -s -w 74 | while IFS= read -r l; do printf '     %s\n' "$(ui_c 2 "$l")"; done; }
ui_warn() { printf '  ⚠️  %s\n' "$(ui_c '1;33' "$*")" >&2; }
ui_skip() { printf '  ⏭️  %s %s\n' "$(ui_c 33 "$1")" "$(ui_c 2 "$2")" >&2; }
ui_err()  { printf '\n  ✋ %s\n' "$(ui_c '1;31' "$*")" >&2; }
ui_hint() { printf '     %s\n' "$(ui_c 2 "$*")" >&2; }
ui_cmd()  { printf '       %s\n' "$(ui_c 36 "$*")" >&2; }

# A file or step done once, under a "first run" heading printed only if needed.
_ui_first_run_shown=0
ui_seeded() {
  if [ "$_ui_first_run_shown" -eq 0 ]; then ui_section "📄" "First run"; _ui_first_run_shown=1; fi
  printf '  📄 %s %s\n' "${1#"${NOVAK_HOME:-}"/}" "$(ui_c 2 "$2")"
}

# Optional services that were left out, collected while the profiles are worked
# out and printed together under one heading.
ui_skipped_names=()
ui_skipped_why=()
ui_skip_later() { ui_skipped_names+=("$1"); ui_skipped_why+=("$2"); }
