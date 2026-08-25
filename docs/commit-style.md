# Commit style

[Conventional Commits](https://www.conventionalcommits.org). Enforced by a
hook, so it can't quietly drift.

```
type(scope): description

Why. What it cost. What you checked.

BREAKING CHANGE: only when something breaks
```

## The subject

Lowercase type, optional scope in parentheses, colon, space, description.
72 characters or fewer, **imperative mood** ("add", not "added" or "adding"),
lowercase description, no full stop. The hook checks all four.

| Type | For | Version effect |
|---|---|---|
| `feat` | New capability | minor |
| `fix` | Something was broken and now isn't | patch |
| `docs` | Documentation only | — |
| `refactor` | Restructuring, no behaviour change | — |
| `perf` | Performance | patch |
| `test` | Tests | — |
| `build` | Build system, images, dependencies | — |
| `ci` | Pipeline | — |
| `chore` | Housekeeping | — |
| `style` | Formatting only, no logic | — |
| `revert` | Undoing something | — |

Breaking changes get `!` before the colon **and** a `BREAKING CHANGE:` footer.
The `!` is for tooling; the footer is for the person who has to deal with it.

```
feat(memory)!: identity comes from the connection, not a tool argument

BREAKING CHANGE: clients passing user_id as a tool parameter will be
ignored. Register a per-client token in MEMORY_TOKEN_MAP instead.
```

## Scopes

Not mandatory, but they make history searchable. Ones that fit these repos:

`memory` · `registry` · `konzol` · `integrations` · `voice` · `proxy` ·
`security` · `deploy` · `omlx`

**`security` earns its place as a scope.** When you're working out whether an
old decision still holds, `git log --grep 'security'` showing every change that
touched the trust model is worth the small discipline of tagging them.

```
feat(integrations): add Tududi
fix(konzol): mobile UI overflow
fix(security): re-check admin group on every mutating request
docs(deploy): rewrite README for people who are not me
build(integrations): pin supergateway instead of npx-at-runtime
```

## The body

**The diff already says what changed. The body is for why.**

This matters more here than in most projects, because much of what's in these
repos is decisions rather than code — and a decision with no recorded reasoning
gets re-litigated, or quietly reversed by someone who assumed it was arbitrary.

Worth writing down:

- The reason, particularly if the change looks strange without context
- What you traded away, and what would justify revisiting it
- **What you verified, and what you didn't.** An untested change described
  honestly is far more useful than one implying confidence it hasn't earned
- Alternatives you rejected, so nobody re-treads that ground

The hook nudges when a commit has no body but doesn't block it. Some changes
really are one-liners.

## What this buys

Conventional Commits is machine-readable, which unlocks things later without
extra work now:

- **Changelogs** generated from history rather than maintained by hand
- **Semantic versioning** — `feat` bumps minor, `fix` bumps patch, `!` bumps
  major
- **Release notes** on GitHub, grouped by type
- Filtering: `git log --grep '^fix(security)'`

None of that is set up yet. The point is that the history will already be in
the right shape whenever it is.

## Setup

Hooks live in `.git/hooks`, which isn't tracked, so each clone needs:

```bash
git config core.hooksPath .githooks
git config commit.template .gitmessage
```

`scripts/bootstrap.sh` does this for you. To bypass the hook once:
`git commit --no-verify`.
