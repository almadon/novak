# Where this got to

Working notes for the current deployment. Delete this once the stack has run a
while unattended with nothing below it worth flagging; see "On this file's own
exit condition" below for why it has not been yet.

**Last full rewrite:** 2026-10-24, covering everything since the 2026-09-10 version
(decisions #55 to #73). Earlier versions are in git history. Written in a long working
session with live access to Spire and Home Assistant, so most items say what was checked
directly and what was not.

**On this file's own exit condition:** Spire has run daily for weeks and survived a real
reboot test (decision #37), but the identity, approvals and Open WebUI work below is days
old and has had one or two real runs each, not the daily use that turns "verified once"
into "trusted". The file can go when nothing under Open VERIFY is open and the newest
decisions have lived through a few weeks.

## What is true right now

- **Spire (Unraid, AMD RDNA4, 16 GB VRAM) is the sole production host.** Open WebUI, the
  router (LiteLLM v1.106.0, with its own key), Ollama on Vulkan, Hindsight, the gateway,
  ingest and its Whisper container, the console (Konzol), the persona server, openWakeWord
  and the Brave search MCP all run there. Models: `chat` is qwen3:14b, `deep` is a ByteShape
  IQ4_XS build, `task` and `ha-voice` are a 4B instruct model. **Every model runs with an
  8,192-token context window**, and the card is almost full with the 14B and the 4B loaded;
  this limit shaped most of the recent decisions.
- **Home Assistant runs on its own host**, `xenia` (tailnet address 100.125.1.10, public name
  xenia.rmrg.casa), no longer the Yellow. It holds the Supernotify and HA-MCP integrations,
  the household voice pipeline "Novak", one pipeline and agent per person ("Novak tmeuze",
  "Novak ushy"), and the approvals helper, automation and dashboard.
- **Identity is real.** Two people (tmeuze, ushy) plus a household. The gateway
  ([gateway.md](gateway.md)) gives each person only their own tools with their own
  credentials, holds removals until they confirm, filters tool lists, and audits who did
  what (names of arguments, never values). Pocket ID (Inti) is the only way into Open WebUI
  and the console; local sign-in is off (decision #68).
- **Approvals reach a phone.** The gateway sends a held call through Supernotify to the
  person's phone with Approve and Deny buttons; a press fires a Home Assistant event, an
  automation writes it to a helper, and the gateway acts on it (decisions #64, #72). A tap
  opens an approvals page in the app (decision #65). Light, scene, fan and media-player calls
  need no tap (decision #63).
- **The tool lists are lean.** The gateway offers two built-in house tools (about 450 tokens)
  and a per-connection allowlist, because Home Assistant's own tools alone were about 21,000
  tokens against an 8,192 window (decision #71).
- **Open WebUI is declared, not clicked.** `registry/openwebui.yaml` defines the gateway
  connections and the presets Novak, Novak Deep, Home and Code, with built-in tools off;
  `novak up` re-applies it, because Open WebUI forgets its connections on restart
  (decisions #66, #67).
- **Ingest delivers as the recording's owner**, through the gateway, with plain notices through
  Home Assistant (Apprise is wired but dormant for Novak, decisions #60, #70).
- **Secrets live in `secrets.env`** (mode 600), not `.env`, which is now safe to print
  (decision #69). **Hindsight listens on loopback only** (decision #62).
- **Pi (a terminal coding agent) is installed on the owner's Mac** and can use the router;
  `novak pi config` and `novak pi hint` help (decision #73, [pi.md](pi.md)).
- `novak status` reports `Config: ready` on Spire.

## Built since the last version

| Decision | What |
|---|---|
| #55 to #57 | No hidden reasoning for chat, the ByteShape `deep` build, the ingest extension |
| #58 to #60 | The gateway, a keyed router, ingest through the gateway |
| #62 | Hindsight on loopback only |
| #63, #64, #65 | Harmless device calls need no tap; Approve and Deny buttons; an in-app approvals page |
| #66, #67 | Open WebUI declared and applied; a picker of presets instead of router roles |
| #68 | Open WebUI sign-in through Pocket ID only |
| #69 | Secrets in their own file |
| #70, #72 | Apprise for the fleet's alerts and plain notices; Supernotify for Novak's approvals |
| #71 | Lean house tools, because the context window is small |
| #73 | Pi in the terminal |

## Verified live, and not

**Checked directly on the running system:** the lighting request on the Home preset (one call,
correct arguments, confirmed in Home Assistant); a held call approved from an Android phone and
then run, with exactly one notification and both buttons; the Hindsight port refusing
connections off the host; the secrets migration (21 secrets moved, none left in `.env`); local
sign-in refused with a 403; the console's sign-in redirect accepted by Pocket ID after the
callback address was corrected; the gateway's tool allowlists (Home about 300 tokens, the main
connection about 2,200); Pi finishing a small task and, with four lines of editing rules, a
rename across a file.

**Not yet checked live:** a passkey sign-in to the console at `nv.sp.a64.one`; any of ushy's own
flows beyond her tool list; the Apprise sender against a real Apprise (the fleet's key is not
created yet); a house request in Home Assistant voice through the new pipelines.

## Decided, not built

- **Persona push to clients** (decision #18's original proposal). Superseded by the router
  existing at all (decision #23); not going to be built.
- **A tasks snapshot for chat**, like `house_state` is for lights (decision #71's reasoning).
- **Hosted-provider keys through the router**, so Open WebUI and Pi reach a hosted model with the
  router key and the provider key stays in `secrets.env` (decision #73).
- **A fallback notice when Home Assistant is down.** An approval request cannot reach a phone
  while Home Assistant is unreachable (it expired silently during an outage); a plain Apprise
  notice would at least say something is waiting.
- **A larger context window for `chat`**, which depends on VRAM that has not been measured with
  the 4B model loaded beside it.

## Open VERIFY items

- **Supernotify's behaviour across a release.** The gateway's call shape was checked against v2.16.0
  (top-level `actions`, `delivery` and `dry_run`; list-shaped delivery targets; one delivery named
  explicitly). A release could change it; the tests pin what the gateway sends, not what
  Supernotify accepts.
- **The Home preset's base model.** It runs on the 14B `chat` model; whether the 4B is enough for
  tool calls on the two lean house tools has not been tried.

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
  is (decision #43), and the artifact is committed to this repo (decision
  #50), not just local to whichever Mac trained it. What's left is
  device-specific: flashing it onto an actual Voice PE or streaming
  satellite, which `wakeword.md` already flags as costing more than a
  file copy. `openwakeword`'s own server-side model (a different format,
  for Wyoming satellites — see wakeword.md) is a separate, still-untouched
  question.
- **HA's native `litellm` conversation agent is new tonight** — working
  and verified in this session's testing, but hasn't had the kind of
  real-world daily use that would turn "verified once" into "trusted."
  Worth revisiting after it's actually been lived with for a while.
- **HA persona pull (decision #53) needs confirming on a live HA.** The
  server and the pull-health check are tested offline and against the
  reference deployment's HA for reachability. Confirm that the Instructions
  template renders the sensor's text (ask `ha-voice` who it is), and that
  `novak drift --live` reports "matches" once the sensor exists.

## Not started

- Konzol has three placeholder pages and a design token layer, no components. Approvals and the
  audit log are the likely first uses now that the data exists.
- `CHANGELOG.md`: conformIT's own justification is about changes a user would notice, and there
  has been no tagged release yet; worth starting at the first one.
- The old claims about an interactive wizard, `docs/security.md`, `LICENSE`, `CLAUDE.md` and
  version pinning are all done (decisions #45 to #49); see git history for the detail.

## Traps already hit, all documented (still true, still worth knowing)

- Login Items, Keychain items, Docker, and Tailscale are **all
  per-account** on macOS. Something set up as the admin user does
  nothing for `novak`. (macOS/oMLX-development-specific; not relevant
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
- **A simulation is only a simulation if the flag is where the service looks for it.** A Supernotify
  call with `dry_run` inside `advanced` was not recognised and sent a real notification to two
  phones; `dry_run` belongs at the top level of the call (decision #72).
- **Left to choose, Supernotify sends twice**: through the phone's push delivery and again through
  the person's notify entity. Name the delivery and set `delivery_selection: explicit`.
- **A model silently loses the start of its prompt when it is longer than the window.** Ollama
  truncates; the router and Open WebUI show nothing wrong, and the model "ignores" its
  instructions. Measure tool definitions in tokens before offering them (decision #71).
- **Open WebUI forgets runtime-set tool connections on restart** while `OWUI_PERSISTENT_CONFIG=false`;
  model presets live in its database and survive (decision #66).
- **Piping `novak up` or `novak update` into `head` can stop it before the containers are
  recreated.** Closing the pipe sends SIGPIPE mid-run; let it finish, or send output to a file.
- **A bare `on` or `off` in YAML is a boolean.** A rule listing `[on, off, toggle]` silently became
  `[True, False, "toggle"]`; quote them.
- **Open WebUI's own `ask_user` tool will be used by a small model in place of acting.** Turn
  built-in tools off per preset (`capabilities.builtin_tools: false`).
- **Pi's `edit` tool needs old text that matches in exactly one place**, and a small model will
  repeat an ambiguous edit about a hundred times unless told to use `sed` (decision #73).
- **A retired phone can re-register itself.** Disabling a Mobile App entry in Home Assistant was
  undone once; sign the app out on the phone, then delete the device.
