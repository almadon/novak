# Where this got to

Working notes for the current deployment. Delete this once the stack has
run a while unattended with nothing below it worth flagging — see "On
this file's own exit condition" below for why it hasn't been yet.

**Last full rewrite:** 2026-09-10, from Spire (Unraid), covering everything
since the previous version (2026-08-27, written from the Mac mini
`Mitochon`). That version is not reproduced here — see git history if the
detail is ever needed again — because almost everything in it is now
either done, superseded, or simply about the wrong host: Spire, not
Mitochon, has been the real household deployment since decision #33.

**Since then (2026-09-22, incremental, not a rewrite):** decisions
#43-#49 — wake word training actually completed, a real persona drift
detector, every remaining container image pinned, `CLAUDE.md` and a
`LICENSE` added, every VERIFY licence in `credits.md` checked, and
`security.md` rewritten against current reality. Written from a coding
session with no live host access, so anything needing a real deployment
to confirm is marked VERIFY below rather than claimed.

**On this file's own exit condition:** the previous version said the
stack was "close to" the point where this file could go away. It's
closer now — Spire has run daily for weeks, survived a real reboot test
unaided (decision #37) — but still not deleted, because the items under
Open VERIFY below are genuinely unchecked, and because tonight's own work
(the HA voice pipeline) is fresh enough that it hasn't had time to prove
itself the way the rest of the stack has.

## What is true right now

- **Spire (Unraid, AMD RDNA4 GPU) is the sole production host.**
  Hindsight, Open WebUI, the console, the router, Ollama, and
  `openwakeword` all run there (decision #28/#33). Mitochon is kept only
  for oMLX development; nothing in production depends on it being up.
- **Home Assistant runs on its own separate hardware** (a Home Assistant
  Yellow), reaching Spire's router over the LAN/tailnet — not part of the
  `docker-compose.yml` stack at all. See [home-assistant.md](home-assistant.md).
- **Voice went through a real overhaul tonight** (decisions #39–#42):
  Novak's own whisper/piper containers are gone, replaced by HA's own
  native Whisper/Piper add-ons; the conversation agent is now HA Core's
  own native `litellm` integration (added HA 2026.8), not the HACS
  `custom_conversation` this doc used to point at — that stays installed
  as a documented fallback for HA versions before 2026.8, but isn't what
  a fresh setup should reach for first. Persona-correct, device control
  verified with real state changes, not just plausible response text.
- **`novak status` reports `Config: ready`** on Spire. `novak drift` is
  real and works, but only for what it says it covers: settings and the
  registry, against the repo. It cannot see whether a client's persona
  still matches `prompts/` — that check does not exist (see Decided, not
  built, below).
- The portal and TinyAuth exist in `docker-compose.yml` but stay off on
  Spire on purpose (decision #34) — the VPS proxy already does that job;
  see [proxy.md](proxy.md).
- `admins.novak` (the Pocket ID group) governs three things: the console,
  Open WebUI's admin role and model RBAC, and the portal (where it's
  configured) — one group, three independent enforcement points, each
  worth spot-checking against a live login rather than assumed
  transitive from the others.
- Konzol's role stays narrow on purpose: memory/registry-editing only,
  not a dashboard. No plugin surface exists to fold it into Open WebUI,
  and the portal (where deployed) covers the "one glass pane" want
  instead.

## Built since the last version of this file

- **Full Spire migration** (decision #28/#33) — was aspirational in the
  previous version of this file, is complete now. Storage split per
  decision #33: compose manifests/`.env` under Unraid's appdata path;
  databases, media, and model weights on bulk storage
  (`/mnt/teracache/Novak/{data,models,config}`).
- **The `novak` CLI on Unraid**, built and tested end to end (decision
  #35) — `status`, `secret`, `drift`, `adopt`, `ports`, `router apply`,
  `checklist` all verified against the real host.
- **The internal proxy moved onto Spire itself** (decision #36),
  replacing a separate host that job used to need.
- **A real reboot test, survived** (decision #37) — the deploy
  checklist's Phase 11, actually run: all containers came back unaided,
  no manual step. The previous version of this file listed this as an
  open VERIFY item; it no longer is.
- **A real Open WebUI persona bug found and fixed** (decision #38) — its
  own Builtin Tools/Memory capabilities were silently sending a system
  message that defeated the router's persona injection. Not something
  `novak drift` could have caught (see the persona-drift-check gap
  below, still open).
- **Voice pipeline overhaul** (decisions #39–#42) — see above.
- **"Hey Novak" microWakeWord training completed** (decision #43) — a
  real `hey_novak.tflite` now exists, calibrated to 0.103 false-accepts/hour
  at 0.992 recall. Not yet on a device; see Open VERIFY below.
- **A real persona drift check, for the failure mode that actually
  happened** (decision #44) — `persona_hook.py` now logs `PERSONA_DRIFT`
  whenever `chat`/`deep` silently skip persona injection because a
  client sent its own system message (decision #38's bug, made
  observable instead of silent). `novak drift --live` surfaces it from
  the router's logs. Logic verified offline; not yet run against a live
  router — see Open VERIFY below.
- **Every container image now pins to a digest, not a moving tag**
  (decision #45) — closes conformIT audit gap #4. `open-webui`,
  `console`, `hindsight`, `openwakeword`, and `ollama` join `caddy`,
  `tinyauth`, and `router`, which were already pinned. Not yet pulled on
  a live host; see Open VERIFY below.
- **`CLAUDE.md` added** (decision #46) — conformIT's required-file gap,
  the one with the real immediate cost (conventions rediscovered by trial
  and error across sessions). Also caught and removed a stale claim in
  this file: `novak guided-setup` already existed and was never crossed
  off "Not started" below.
- **Every VERIFY licence in credits.md checked directly** (decision #47).
  Notably: Open WebUI's real licence has a branding-retention clause
  (this deployment is exempt, under its 50-user/30-day threshold), and
  the microWakeWord trainer (decision #43) has no LICENSE file at all —
  fine for local, never-redistributed use.
- **Licensed MIT across all three repos** (decision #48) — the audit's
  one "actively harmful to leave" gap, closed. Also fixed a second, more
  stale claim found along the way: `novak-konzol`'s README said "never
  built or run," while CI has published an image since 2026-08-21.
- **`docs/security.md` rewritten** (decision #49) against what's actually
  deployed — multi-platform secrets, the registry's risk levels, the
  persona's enforcement role (and decisions #38/#44 as the concrete case
  of it failing), and the real exposure table from `proxy.md`. Also fixed
  two stale "persona drift check still doesn't exist" claims found in
  `architecture.md` while cross-checking it, written before decision #44.

## Decided, not built

- **Persona push to clients** (decision #18's original proposal).
  Superseded by the router existing at all (decision #23); not going to
  be built.
- **The HA-side half of the client-side persona drift check.** Decision
  #44 built the other half — see Built, below. What's still open: HA's
  native `litellm` integration keeps its own copy of
  `prompts/novak-voice.md`'s text (decision #42, pasted into its
  Instructions field), and nothing checks whether that copy has since
  drifted from the master file. Needs HA's own API and a dedicated,
  read-only long-lived token — none exists yet, and none of this was
  built blind, since there's no live HA instance reachable from a coding
  session to verify it against.

## Open VERIFY items

- Whether Hindsight has a trash, before trusting `delete` to be
  recoverable.
- ~~Licences marked VERIFY in credits.md~~ — done (decision #47). All
  eight checked directly; none remain. Worth noting: Open WebUI's actual
  licence has a branding-retention clause (exempt under 50 users/30
  days, which this deployment is), and the microWakeWord trainer
  (decision #43) has no LICENSE file at all — fine for the local,
  never-redistributed use it gets here, not fine to build on for
  anything redistributed later.
- **The portal's OAuth-group restriction against a live Pocket ID
  login**, on whichever deployment actually runs the portal. Everything
  about TinyAuth's startup and the OIDC connection was verified
  directly; whether `TINYAUTH_APPS_PORTAL_OAUTH_GROUPS` actually refuses
  an account outside `admins.novak` needs a real round trip.
- **The exact Pocket ID claim shape** feeding `OWUI_OIDC_ROLES_CLAIM` /
  `OWUI_OIDC_GROUP_CLAIM`. Decode a real ID token after first login.
- **The `PERSONA_DRIFT` log line (decision #44) has not been run against
  a live router.** Its logic was checked offline with `litellm` stubbed
  out — confirmed it fires for `chat`/`deep` and stays silent for
  `ha-voice` — but `novak drift --live`'s actual `docker compose logs`
  grep has never been run against a real deployment. Run it on Spire, and
  ideally confirm the warning genuinely appears if Builtin Tools/Memory
  get flipped back on for a model preset.
- **The digest pins (decision #45) have not been pulled on a live host.**
  Confirmed against each registry's manifest API and `docker compose
  config`, not against an actual pull/start. Run `novak update` or a
  fresh `novak up` and confirm all five services still come up; for
  `open-webui` specifically, re-confirm decision #38's persona fix still
  holds against the pinned build through the real chat UI.
- **Wake word deployment to a satellite is not done.** Training itself
  is (decision #43) — a real `hey_novak.tflite` exists, calibrated to
  0.103 false-accepts/hour at 0.992 recall. What's left is
  device-specific: flashing it onto an actual Voice PE or streaming
  satellite, which `wakeword.md` already flags as costing more than a
  file copy. `openwakeword`'s own server-side model (a different format,
  for Wyoming satellites — see wakeword.md) is a separate, still-untouched
  question.
- **HA's native `litellm` conversation agent is new tonight** — working
  and verified in this session's testing, but hasn't had the kind of
  real-world daily use that would turn "verified once" into "trusted."
  Worth revisiting after it's actually been lived with for a while.

## Not started

- Konzol has three placeholder pages and a design token layer, no
  components — less urgent now that the portal (where deployed) covers
  the cross-app viewing want that was the main pressure on it.
- ~~No interactive first-run wizard~~ — stale claim, removed. `novak
  guided-setup` (also menu item 4) has existed since 2026-09-04, before
  this file's last full rewrite; it was simply never crossed off here.
  Walks through whatever `novak status` would list as missing, asking for
  each value. See [cli.md](cli.md)'s "Guided setup" section.
- ~~`docs/security.md` wants rewriting~~ — done (decision #49). Was
  describing a single-Mac, Qdrant-backed deployment; rewritten against
  Spire, Hindsight, the router's persona-enforcement role, and the real
  exposure table from [proxy.md](proxy.md).
- ~~`LICENSE` file~~ — done (decision #48). MIT, across all three repos.
- ~~`CLAUDE.md`~~ — done. `CHANGELOG.md` is still not started; conformIT's
  own justification for it is about changes a *user* would notice, and
  there's been no tagged release yet — worth starting at the first one
  rather than now.
- ~~**Version pinning**~~ — done (decision #45). Every image in
  `docker-compose.yml` now pins to a digest, not a moving tag. Not yet
  verified against a live pull; see Open VERIFY below.

## Traps already hit, all documented (still true, still worth knowing)

- Login Items, Keychain items, Docker, and Tailscale are **all
  per-account** on macOS. Something set up as the admin user does
  nothing for `novak`. (Mitochon/oMLX-development-specific; not relevant
  to Spire, which is Linux.)
- `HOST_NAME` does not affect what anything binds to; it only builds
  URLs.
- A dangling symlink or LaunchAgent pointing at an old checkout path
  fails silently, not loudly, and containers with
  `restart: unless-stopped` will keep looking healthy the whole time.
- `up.sh`'s own `envval()` was silently missing a guard that let ANY
  variable newly added to a gating array in `vars.sh` crash the whole
  script under `set -e`, before reaching Docker at all, if that variable
  wasn't yet a line in an already-deployed `.env`. Fixed; worth
  remembering that adding to `REQUIRED_EDITS`/`CONSOLE_EDITS`/`PORTAL_EDITS`
  and similar is not as side-effect-free as it looks without this guard.
- `TINYAUTH_APPURL` (and by extension anything relying on a forward-auth
  cookie domain) must be a real hostname with a scheme. A bare Tailscale
  IP is refused outright.
- A relative bind mount in `docker-compose.yml` resolves against
  `--project-directory`, which `up.sh` and `scripts/novak` both set to
  `$NOVAK_HOME`, not the checkout. When the source doesn't exist there,
  Docker silently creates an empty directory rather than erroring, so
  the failure surfaces later as an `IsADirectoryError` inside whatever's
  reading the file, not as a compose error. `REPO_DIR` is exported by
  both scripts specifically so mounts of repo files can use
  `${REPO_DIR}/...` instead.
- **`reconciler/router_apply.py` silently falls back to the repo's own
  checked-in template `registry/engines.yaml`** if `$NOVAK_HOME` isn't
  set in the shell running it — e.g. an ad-hoc `root` SSH session,
  rather than however the `novak` CLI normally runs. No error, just the
  wrong file, visible only in the dry-run output naming the wrong
  engine. Pass `NOVAK_HOME=...` explicitly outside the CLI's own
  invocation context (decision #42).
- **Docker container env vars are fixed at container creation.**
  `novak restart <service>` alone does not re-read a changed `env_file`
  — a genuinely new variable needs the container recreated
  (`docker compose up -d <service>`, not just a restart), same lesson as
  the `reconciler` one above, hit while debugging tonight (decision #42).
