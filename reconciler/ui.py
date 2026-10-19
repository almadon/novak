"""Terminal output helpers for the reconciler: colour, emoji and sections.

Pretty output is for a person at a terminal. It is on when stdout is a terminal
or FORCE_COLOR is set, and off when NO_COLOR is set or stdout is piped, so
anything that reads this output (novak registry --check parses it) keeps getting
the plain lines it always did.
"""
import os
import sys

RESET = "\033[0m"
CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
         "blue": "34", "magenta": "35", "cyan": "36", "boldcyan": "1;36", "boldyellow": "1;33",
         "boldred": "1;31"}
WIDTH = 62


def pretty(stream=None) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(os.environ.get("FORCE_COLOR")) or (stream or sys.stdout).isatty()


def c(name: str, text: str, on: bool) -> str:
    return f"\033[{CODES[name]}m{text}{RESET}" if on else text


def section(emoji: str, title: str, on: bool) -> str:
    """A rule with a title: a blank line, then '━━ 🔌 Title ━━━━━━'."""
    head = f"━━ {emoji}  {title} "
    return "\n" + c("boldcyan", head + "━" * max(3, WIDTH - len(head)), on)
