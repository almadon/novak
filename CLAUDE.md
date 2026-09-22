# Working in this repo

For an AI agent picking this project up cold. It exists because this
repo's own conventions (the 72-character commit subject limit, the branch
workflow, where live config lives versus docs) have been rediscovered by
trial and error across sessions more than once — exactly the cost
[conformIT](https://github.com/almadon/conformIT)'s documentation standard
names this file for.

## Read first

1. [docs/STATE.md](docs/STATE.md) — what's actually true right now: what's
   built, what's decided-but-not-built, what's still open. Has its own
   stated exit condition; if you find it deleted, that condition was met.
2. The tail of [docs/decisions.md](docs/decisions.md) — the most recent
   entries explain *why* the current architecture looks the way it does.
   Each entry states what was decided, why, what it cost, and what would
   make it worth revisiting. Don't re-litigate a decision without reading
   the entry that made it — the reasoning is usually still there.
3. [docs/architecture.md](docs/architecture.md) for the shape of the
   system; [docs/what-sets-novak-apart.md](docs/what-sets-novak-apart.md)
   for the principles behind it.

## Commits

[Conventional Commits](https://www.conventionalcommits.org), hook-enforced —
see [docs/commit-style.md](docs/commit-style.md) for the full rules and
`.githooks/commit-msg` for what's actually checked. The essentials:

- `type(scope): description` — lowercase, imperative mood ("add", not
  "added"/"adding"), no full stop, **72 characters or fewer**. The hook
  rejects anything that doesn't match; it isn't a style suggestion.
- Types: `feat fix docs style refactor perf test build ci chore revert`.
- The body is where the reasoning goes — why, what it cost, what was
  checked. Worth having in a year; the hook nudges but doesn't require it.
- Enable the hook per clone: `git config core.hooksPath .githooks` (hooks
  in `.git/hooks` aren't tracked, so a fresh clone needs this once).

## Branching and PRs

Recent history's actual pattern, not a formality:

```bash
git checkout -b <type>/<short-description>   # off main
# ... commit ...
git push -u GitHub <branch>
gh pr create --title "..." --body "..."       # body ends with the
                                                # Claude Code attribution
                                                # line when Claude wrote it
gh pr checks <n>                               # wait for CI, then
gh pr merge <n> --merge --delete-branch
```

Don't push directly to `main`. `main` tracks `GitHub` (the canonical
remote); a deprecated `Nexus` self-hosted mirror existed briefly and was
removed — if a remote by that name reappears, it's not canonical, check
before pushing to it.

## Writing style

Plain language, stated directly. "Checked directly" beats "should work" —
this project's own habit (and the actual root cause behind more than one
past bug, e.g. decision #38) is to distrust an untested assumption more
than an unfinished feature. Mark anything not actually verified `VERIFY`
rather than assuming it — see how [docs/credits.md](docs/credits.md) and
[docs/STATE.md](docs/STATE.md) already do this. Say what's true plainly;
don't hedge a verified fact and don't overstate an unverified one — both
are reporting failures, not just the second one.

No em dashes in `docs/` or `README.md` — an em dash is almost always
standing in for a comma, a period, a colon, or parentheses, and picking
the right one is part of writing the sentence, not a find-and-replace.
**This is a forward-looking rule, not yet true of the existing text** —
the conformIT audit found the docs fail it at scale and deliberately left
that cleanup as its own future pass. Don't add new em dashes; fixing old
ones is a separate, dedicated change, not something to do incidentally
while editing nearby text for an unrelated reason.

## Where things live

- **`prompts/`, `registry/`** are live, deployed configuration — the
  master copy an applier (`reconciler/*.py`) pushes out and `novak drift`
  checks deployments against. Not documentation about the system; part of
  the system.
- **`docs/`** is documentation and reasoning. `docs/STATE.md` and
  `docs/decisions.md` are the two that go stale fastest and are worth
  rereading before trusting anything else in `docs/` at face value.
- **`docker-compose.yml`** — project name is `novak` (`name: novak` at
  the top), so default container names are `novak-<service>-1`. Images
  pin to a digest, not a tag (decision #45) — see that entry's refresh
  procedure before bumping one.

## A live host is usually not reachable from a coding session

Several open items in STATE.md need a real deployment to verify (SSH,
docker socket, HA/Open WebUI API tokens) that a fresh session typically
doesn't have. When that's true, say so plainly, do what's verifiable
without it (offline logic tests, `docker compose config`, syntax checks,
registry API lookups), and mark the rest `VERIFY` rather than claiming
something is done that was only ever written. This project has a strong
distaste for code that claims more confidence than it earned.
