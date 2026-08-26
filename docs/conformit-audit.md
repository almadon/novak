# conformIT conformance audit

Novak measured against [conformIT](https://github.com/almadon/conformIT), the
uniform engineering standard, at commit `a5ceb92` (2026-08-24).

This is a report, not a migration. conformIT decision #2 says existing repos
are not retroactively migrated, and `audit` reports rather than rewrites, so
nothing here is applied automatically. Each gap below states what it would
cost to close, because several of them are not obviously worth closing.

**Novak is one of the nine repos conformIT was derived from, and is cited by
name in six of its eight standards documents.** That makes this audit less
useful than it looks in places: where a rule was generalised from Novak's own
practice, Novak passes by construction. The findings worth reading are the
ones where Novak diverges from a rule it helped write.

## Method

Mechanical checks were run against the working tree. Judgment calls were made
by reading. Anything not actually checked is marked `VERIFY` rather than
assumed, per the licensing-and-provenance standard.

## Summary

| Standard | Result |
|---|---|
| Rules of engagement | Substantially conforming |
| Design principles | Conforming, and cited as a source for three of the ten |
| Security posture | One real gap: unpinned images |
| Licensing and provenance | One blocking gap: no `LICENSE` |
| Documentation standard | Four required files missing, one status line false |
| Writing style | Fails the one mechanically enforced rule, at scale |
| Commit and history | Conforming, with a hook that exceeds the template |

## Gaps, most consequential first

### 1. There is no `LICENSE` file

Both the documentation standard and licensing-and-provenance require one from
the first commit. The reasoning is that a repo without a licence is not open
by default, it is all rights reserved by default, which is the opposite of
what a public repo usually intends. Novak is public.

This is the only gap in the audit that is actively harmful to leave, and it
cannot be closed by an audit because choosing a licence is the maintainer's
call. conformIT's own default for an application not intended for reuse is
MIT, or an explicit all-rights-reserved, on the grounds that either is fine
and silence is not.

**Cost to close:** one decision and one file.

### 2. The README status line is false

The standard requires a status line of "in testing", "stable", or
"deprecated", stated near the top. Novak's says:

> **Status: not finished.** This has never been deployed. Some of it has
> never even been run.

The stack has been deployed, has run end to end, and now survives a boot
under launchd. `docs/STATE.md` has recorded that since 2026-08-19, so the two
documents contradict each other.

This is a rules-of-engagement rule 2 failure rather than a formatting one.
The rule asks that status claims name their evidence and that verified work
be stated plainly without hedging, and it explicitly calls false modesty as
much of a reporting failure as false confidence. Understating status is not
the safe direction, it is just the other error.

**Cost to close:** rewriting one paragraph. Done in this change.

### 3. No LLM disclosure in the README

Required by the documentation standard, and separate from the per-commit
trailer. The commit trailer says who wrote a given change; the README says
how the project as a whole is built. Novak carries the trailers and not the
repo-level disclosure.

**Cost to close:** one paragraph. Done in this change.

### 4. Every container image is unpinned

Security posture rule 8 is direct about this: a dependency fetched at runtime
is an unreviewed change on every start, and an outage when the network is
down.

| Service | Tag |
|---|---|
| open-webui | `:main` |
| console | `:latest` |
| hindsight | `:latest` |
| whisper | `:latest` |
| piper | `:latest` |
| openwakeword | `:latest` |

All six. `docs/credits.md` already records unpinned `npx -y` MCP servers as a
known weakness, which is the honest-open-item treatment the standard asks
for, but it does not cover the images themselves.

This one has a genuine trade-off rather than an obvious answer. Pinning
digests on a single-operator deployment means updates become manual work, and
the failure mode of a stale pinned image is quieter than the failure mode of
a surprise upstream change. The standard's position is that the surprise is
worse. Worth a decision entry either way, because right now the exposure is
undocumented rather than accepted.

**Cost to close:** digest pins plus a refresh procedure, or a decision entry
recording the exposure as deliberate.

### 5. The no-em-dash rule fails, at scale

This is the only standard with a mechanical check, and Novak fails it by a
wide margin:

```
563 lines containing em dashes
  390 in markdown, across 20 files
  173 outside markdown, across 20 files including scripts, compose, and hooks
```

The largest concentrations are `docs/decisions.md` (73), `docs/deploy-checklist.md`
(50), and `docs/headless-operation.md` (43).

**This is not a find-and-replace.** The rule says so explicitly: an em dash is
almost always standing in for a comma, a period, a colon, or parentheses, and
picking the right one is part of writing the sentence rather than a cosmetic
swap. Mechanically substituting one character for another produces 563 badly
punctuated sentences and satisfies the grep, which is worse than failing it
honestly.

The em dashes outside markdown matter less on the rule's own terms, since the
stated check covers `docs/` and `README.md`, but they are in user-facing hook
output and comments that people read.

**Cost to close:** a real editing pass over roughly 20 files, which should be
its own change and its own review. Deliberately not attempted here.

### 6. Four required documents are missing

| File | Standard says missing means |
|---|---|
| `CLAUDE.md` | Every session re-derives the conventions |
| `CHANGELOG.md` | History is only in git log |
| `CONTRIBUTING.md` | Only required once there are contributors |
| `VISION.md` | Only required for a project with a long-range shape |

`CLAUDE.md` is the one with immediate value, and the evidence for it is this
repo's own history: conventions like the 72-character subject limit have been
rediscovered by trial and error across sessions, which is exactly the cost the
standard names.

`CHANGELOG.md` is the weaker case at this stage. Nothing has been released,
there are no users to notice a change, and the standard's own justification is
about changes a user would notice. Worth starting at the first tagged release
rather than now.

`CONTRIBUTING.md` and `VISION.md` are conditional and neither condition is met,
although `docs/what-sets-novak-apart.md` already does much of what `VISION.md`
would.

**Cost to close:** `CLAUDE.md` is an afternoon and pays for itself. The others
can wait for their trigger.

### 7. Half the decision entries omit the cost

`docs/decisions.md` has 22 entries. 11 carry an explicit `**Cost:**` line.

The file's own header promises all four parts:

> Each entry says what was decided, why, what it cost, and what would make it
> worth revisiting.

Rules-of-engagement rule 3 asks for the same four. The entries that omit the
cost are mostly the early ones, and several state the trade-off in prose
without labelling it, so the gap is smaller than the count suggests. It is
still a promise the document makes and does not keep.

**Cost to close:** an editing pass, best combined with the em dash pass since
it touches the same file hardest.

## Where Novak already conforms

Recorded so the audit is not just a list of failures, and because several of
these were conscious work rather than accidents.

- **Identity comes from the connection, not a parameter** (security posture
  rule 4). Novak is the cited source for this rule, and rejected two memory
  backends on it.
- **Declare, apply, check for drift** (design principle 2). `registry/` plus
  `reconcile.py` and `omlx_apply.py`, with `novak drift` as the independent
  check. The check exists, which is the part the principle says people skip.
- **Uniformity is not a per-client setting** (design principle 8). Cited from
  Novak decision #21.
- **Native capability over a maintained wrapper** (design principle 3, rules
  of engagement rule 7). Adopting Hindsight deleted roughly 400 lines of shim.
- **Runtime data lives outside `docs/`.** `prompts/` and `registry/` are cited
  by the documentation standard as the worked example of this split.
- **`VERIFY` markers are used properly**, in ten places including every
  unchecked licence in `credits.md`.
- **`STATE.md` records what is broken and what previous notes got wrong**, and
  carries an expiry condition. The standard cites this file directly.
- **Evaluated-and-not-adopted is recorded** in `credits.md`, which the standard
  calls the highest-value part of that file and the first part people leave out.
- **Conventional Commits are hook-enforced.** Novak's `.githooks/commit-msg` is
  a superset of conformIT's template: it also passes `fixup!` and `squash!`
  through, exempts trivial subjects from the body nudge, and gives worked
  examples on failure.

## Not checked

- Whether the `VERIFY` licences in `credits.md` are correct. Unchanged by this
  audit, and still a release gate.
- Clean-room procedure. No reimplementation work has been done, so the standard
  does not apply. `VERIFY` if that changes.
- Whether `docs/security.md` covers every rule in the security posture
  individually. It was read for the pinning gap only.
