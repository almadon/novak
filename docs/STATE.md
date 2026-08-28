# Where this got to

Working notes for the Mac mini. Delete this once the stack has run for a while
unattended.

**Last updated:** 2026-08-27, from the mini (`Mitochon`) as `novak`. This is a
full rewrite, not a patch. The previous version was dated 2026-08-19 and
described problems (oMLX on the wrong port, the registry seeded from a
pre-Hindsight checkout, the Tailscale GUI app shadowing the CLI) that are all
resolved. That version is not reproduced here; see git history for it if the
detail is ever needed again.

**On this file's own exit condition:** the stack has now run unattended for
about a week, survived a deliberate reboot test, and the LaunchAgent path bug
that would have broken that is fixed (`fix/launchagent-path-substitution`).
The condition at the top of this file, "delete once it's run a while
unattended," is close to met. Not deleted yet because two things below are
still genuinely unverified in production (the portal's OAuth-group
restriction, and drift-adopt under real drift), not because the file has
nothing left to say.

## What is true right now

- Six core services up: console 3002, hindsight 8888/9999, open-webui 3000,
  whisper 10300, piper 10200, openwakeword 10400. All reachable on both
  localhost and Tailscale. `novak status` reports `Config: ready`.
- The portal and TinyAuth exist in `docker-compose.yml` but are **not yet
  configured on this deployment**: `novak drift` correctly reports their
  variables as unset, defaults apply, nothing starts. See
  [proxy.md](proxy.md#portal-a-single-page-over-open-webui-and-konzol) and
  decision #22.
- `novak drift` is real and works, but only for what it says it covers:
  settings and the registry, against the repo. It cannot see whether a
  client's persona still matches `prompts/`; that check does not exist (see
  Decided, not built below). Don't read "no drift" as "personas match";
  they're different claims.
- `admins.novak` (the Pocket ID group) now governs three things instead of
  one: the console (original), Open WebUI's admin role and model RBAC
  (`feat/owui-oauth-group-admin`), and the portal (decision #22). One group,
  three enforcement points, each independent, not itself a single
  mechanism, and each one's actual behaviour against a live Pocket ID login
  should be spot-checked on its own rather than assumed transitive.
- The registry has a `brave-search` entry (`kind: container`, official
  `@modelcontextprotocol/server-brave-search` wrapped by `supergateway`),
  enabled for both `open-webui` and `home-assistant`. Currently skipped:
  `BRAVE_API_KEY` is unset on this deployment.
- Konzol's role narrowed on purpose, not by neglect. It was never going to
  become a section of Open WebUI (checked directly, no plugin surface for
  that exists); the portal covers the "one glass pane" want instead, and
  konzol keeps the memory/registry-editing job it always had. See decision
  #22 if this reads as a demotion. It isn't one; the two solve different
  problems.

## Built now, out of the order decision #21 itself named

**The inference router exists** (decision #23): `router/` runs LiteLLM in
front of oMLX, injecting the persona from `prompts/` for `chat`, `deep`,
and `ha-voice`, transparently. Built on explicit direct instruction to
build it now, ahead of the persona drift check #21 said should come
first. That departure is recorded in #23, not silently taken, and the
reasoning for the original order hasn't changed.

**Only half of what #21 asked for.** Persona uniformity: done, verified
end to end against the real deployment. Identity travelling with the
request, and the per-user memory routing it was meant to enable: **not
built, not started.** The router today does one thing (inject a system
prompt) and nothing about who is calling.

## Decided, not built

Two items now, not three.

- **Persona push to clients** (decision #18's original proposal: per-client
  copies kept in sync by an applier). Superseded by the router existing at
  all; not going to be built now that #21 has a working alternative.
- **Client-side persona drift check** (decision #18's weaker half, decision
  #21's stated prerequisite for the router). Still does not exist.
  `novak drift` (built, working) checks settings and the registry only. A
  check for whether a client's actual persona still matches `prompts/`
  needs each client's credentials and has not been written, and now that
  the router is live, this is also the only way to confirm it's actually
  being used rather than assumed to be, since nothing stops a client from
  still pointing at oMLX directly.

## Open VERIFY items

Carried forward, plus what the last few days of work added:

- Whether Hindsight has a trash, before trusting `delete` to be recoverable.
- openwakeword's model extension: `.tflite` or `.onnx`.
- Licences marked VERIFY in [credits.md](credits.md): oMLX, Open WebUI
  (licence changed once already, confirm the version in use), Pocket ID,
  outline-mcp-server, Tududi, @aimbitgmbh/vikunja-mcp, **supergateway**
  (checked its `package.json` directly this week; no license field set at
  all, not merely undocumented).
- **The portal's OAuth-group restriction against a live Pocket ID login.**
  Everything about TinyAuth's startup and the OIDC connection was verified
  directly; whether `TINYAUTH_APPS_PORTAL_OAUTH_GROUPS` actually refuses an
  account outside `admins.novak` was not, since that needs a real round
  trip. Confirm before treating it as an enforced boundary.
- **The exact Pocket ID claim shape** feeding `OWUI_OIDC_ROLES_CLAIM` /
  `OWUI_OIDC_GROUP_CLAIM`. Decode a real ID token after first login; some
  IdPs nest or namespace group names differently than a flat string.

## Not started

- Konzol has three placeholder pages and a design token layer, no
  components, unchanged since the previous note, and now less urgent given
  the portal covers the cross-app viewing want that was the main pressure on
  it.
- No interactive first-run wizard; `novak status` names what is missing.
- `docs/security.md` still wants rewriting in the plain style of
  [decisions.md](decisions.md), flagged before, still true.
- **`LICENSE` file.** Public repo, still all-rights-reserved by default.
  Flagged by the conformIT audit (`docs/conformit-audit.md`) as the one gap
  in that audit worth treating as active harm, not a backlog item. Choosing
  one is the maintainer's call, not something an audit resolves on its own.
- **`CLAUDE.md` and `CHANGELOG.md`**, both on conformIT's required-file
  list. `CLAUDE.md` is the one with a real, immediate cost: conventions like
  the 72-character commit subject limit have been rediscovered by trial and
  error across sessions repeatedly, which is exactly what the file exists to
  prevent.
- **Version pinning on the six core images**, still `:latest`/`:main`
  across the board. `novak update` (added this week) makes pulling a new
  version a one-command action, which makes the *lack* of pinning more
  consequential, not less: it's now easier to accidentally run something
  new than before.

## Traps already hit, all documented (still true, still worth knowing)

- Login Items, Keychain items, Docker, and Tailscale are **all per-account**
  on macOS. Something set up as the admin user does nothing for `novak`.
- `HOST_NAME` does not affect what anything binds to; it only builds URLs.
- A dangling symlink or LaunchAgent pointing at an old checkout path fails
  silently, not loudly, and containers with `restart: unless-stopped` will
  keep looking healthy the whole time. Both `~/.local/bin/novak` and the
  LaunchAgent hit this for real after the repo moved to
  `~/Workspaces/Apps/Novak/novak`; both are fixed and both are now installed
  by `bootstrap.sh` rather than copied by hand, specifically so this class
  of bug can't recur the same way.
- `up.sh`'s own `envval()` was silently missing a guard that let ANY
  variable newly added to a gating array in `vars.sh` crash the whole script
  under `set -e`, before reaching Docker at all, if that variable wasn't yet
  a line in an already-deployed `.env`. Fixed; worth remembering that adding
  to `REQUIRED_EDITS`/`CONSOLE_EDITS`/`PORTAL_EDITS` and similar is not as
  side-effect-free as it looks without this guard.
- `TINYAUTH_APPURL` (and by extension anything relying on a forward-auth
  cookie domain) must be a real hostname with a scheme. A bare Tailscale IP
  (otherwise a perfectly valid way to reach every other service in this
  stack) is refused outright.
- A relative bind mount in `docker-compose.yml` (`./router/config.yaml`,
  and the portal's two before this) resolves against `--project-directory`,
  which `up.sh` and `scripts/novak` both set to `$NOVAK_HOME`, not the
  checkout. When the source doesn't exist there, Docker silently creates an
  empty directory rather than erroring, so the failure surfaces later, as
  an `IsADirectoryError` inside whatever's reading the file, not as a
  compose error. `REPO_DIR` is now exported by both scripts specifically so
  new mounts of repo files can use `${REPO_DIR}/...` instead.
