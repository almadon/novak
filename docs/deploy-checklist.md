# Setting up Novak

Work through this top to bottom. It is in the order you actually do things,
which is not the order the pieces are described anywhere else.

Two platforms are supported today (decision #28/#35): **macOS** (Apple
Silicon, oMLX) and **Unraid** (Linux, Ollama). Every phase below is one set
of steps where they don't differ, and a **macOS | Unraid** table where they
do. `novak status`/`novak checklist` give the exact same commands and output
shape on either platform — see [cli.md](cli.md).

> **Verified on real hardware for both platforms** (decision #28/#33/#35),
> but not on every path through this checklist. Anything marked **VERIFY**
> could not be checked without hardware this project doesn't have (a
> different NAS, a different GPU vendor, a non-Unraid Linux host). Expect to
> fix things; that is normal for a first install, not a sign it's broken.

**Roughly how long:** an evening for the stack, plus model downloads. Voice
and the console can wait for another day — the assistant works without them.

---

## Phase 0 — Before you touch the host

| | macOS | Unraid |
|---|---|---|
| **Hardware** | Apple Silicon. Tuned for a Mac mini M4/24GB — less memory means smaller models, not failure. | Any Unraid 7.x box (tested: AMD RDNA3/4 GPU via Vulkan — [ollama-settings.md](ollama-settings.md)). Runs on CPU alone too; expect it to be slow. |
| **Power-loss behavior, decide now** | FileVault decides whether the machine comes back on its own after a power cut, and is annoying to change later. macOS will not auto-login while it's on. Read [headless-operation.md](headless-operation.md) — a network KVM keeps encryption *and* remote recovery. | Settings → Disk Settings → confirm array auto-start is on (`novak checklist` checks `/boot/config/disk.cfg` for you). No FileVault-equivalent trade-off — nothing here is encrypted-at-rest by default. |

*(Console only, either platform)* Register an OIDC client in Pocket ID with
the `groups` scope, redirect URI
`http://<host>:<CONSOLE_PORT>/api/auth/callback/pocketid` for every hostname
you'll use (default `CONSOLE_PORT` is `13401`), and an `admins.novak` group
with you in it.

---

## Phase 1 — Admin setup

| | macOS | Unraid |
|---|---|---|
| **Who does this** | An admin account — the account that runs Novak deliberately has none. | Root — Unraid's normal, only real admin account. No account split needed. |
| **Steps** | Create the service account (System Settings → Users & Groups → Add User, **Standard**). Get any copy of this repo onto the machine and run `./scripts/bootstrap-admin.sh --service-user novak` — applies the power profile, installs OrbStack and oMLX into `/Applications`, gives `novak` a FileVault unlock token. | Clone this repo (e.g. `/mnt/cache/appdata/Novak/repo`) and run `./scripts/bootstrap-unraid.sh` as root — links the `novak` CLI onto PATH, persists that across reboots via `/boot/config/go` (required — `/usr/local/bin` doesn't survive a reboot on this platform), and asks where this deployment's config should live (`NOVAK_HOME`, persisted to `/boot/config/novak/novak_home`). |
| **Verify** | `sudo fdesetup list` — **`novak` must appear**, or it can't unlock at the pre-boot screen. `pmset -g \| grep -E 'autorestart\|sleep'` — autorestart 1, sleep 0. | `novak checklist` Phase 1 checks root + array auto-start directly. |

---

## Phase 2 — The CLI

| | macOS | Unraid |
|---|---|---|
| **Steps** | Log in as `novak` (separate account — nothing carries over). `git clone https://github.com/almadon/novak.git ~/Workspaces/Novak/novak && cd ~/Workspaces/Novak/novak && ./scripts/bootstrap.sh` — no sudo needed; it checks Phase 1 happened. | Already done by `bootstrap-unraid.sh` in Phase 1 — nothing further here. |
| **Confirm it's on PATH** | `command -v novak` → `~/.local/bin/novak` (not `/usr/local/bin` — this account has no sudo). If empty, see [cli.md](cli.md). | `command -v novak` → `/usr/local/bin/novak`. |
| **Docker gotcha** | Each macOS account has its own OrbStack VM — containers from another account are invisible here, and `docker ps` shows nothing while services are plainly running elsewhere. **Launch OrbStack once by hand** and click through any first-run dialog; until dismissed the Docker socket doesn't listen, and the error is an unhelpful `EOF`. | One Docker daemon for the whole host, running as root — no per-account split to run into. |

---

## Phase 3 — Configure

Same commands on both platforms — `novak status`, `novak config`, `novak
secret` behave identically. What differs is *where* a secret physically
lives (see [cli.md](cli.md#unraid-decision-35) / [security.md](security.md)):
macOS Keychain, or a real value directly in `.env` on Unraid (no OS keychain
to use headlessly there — `novak secret verify` checks `.env`'s file
permissions instead of Keychain-hang risk on that platform).

- [ ] `novak status` — lists exactly what is unset and the command to set
      each. Nothing below needs a text editor.
- [ ] Set the values it names:

      novak config set HOST_NAME <name other machines use to reach this host>

      `HOST_NAME` must be reachable from elsewhere — a Tailscale name works
      well. `localhost` will not; it ends up in URLs handed to browsers and
      Home Assistant. `VIKUNJA_URL` only if you use Vikunja.

- [ ] Store the secrets:

      novak secret set HINDSIGHT_API_KEY     # openssl rand -hex 32
      novak secret set OMLX_API_KEY          # or OLLAMA equivalent — see Phase 4
      novak secret set WEBUI_SECRET_KEY --generate

      `WEBUI_SECRET_KEY` isn't required to start, but skip it and Open WebUI
      makes up a random one on every container start, which silently logs
      everyone out on the next `novak up` or restart.

- [ ] `novak status` again — **Config: ready**.
- [ ] `novak secret verify` — every secret reads back cleanly, and (Unraid
      only) `.env` permissions show `ok` (600).
- [ ] macOS only: sanity check that `.env` still shows `set-in-keychain` on
      every secret line — that literal text is never used. If you replaced
      it with a real secret by hand, undo that and use `novak secret set`
      instead. (On Unraid, `.env` holding the real value *is* correct —
      that's the store on this platform.)

---

## Phase 4 — The model

The engine is chosen per platform, not assumed — see [engines.md](engines.md).

| | macOS: oMLX | Unraid: Ollama |
|---|---|---|
| **Reasoning** | [omlx-settings.md](omlx-settings.md) | [ollama-settings.md](ollama-settings.md) — real measured throughput for this hardware |
| **Enable the engine's own auth** | `novak secret set OMLX_API_KEY` | N/A — Ollama has no built-in auth; the router (Later section) is what gates access if you expose it beyond localhost |
| **Get the models** | Download **Qwen3-4B-Instruct 4bit** and **Qwen3-14B 4bit** in the oMLX app | `docker exec <ollama-container> ollama pull qwen3:4b` and `qwen3:14b`; a `deep`-tier model if your GPU has room — see ollama-settings.md's quant-fit notes before assuming a 27B-class model fits |
| **Idle behavior** | 15–30 min TTL on the 14B, **none on the 4B** — voice can't absorb a model load | `OLLAMA_KEEP_ALIVE` (default `20m`), one server-wide value — Ollama has no per-model TTL |
| **Model roles** | Create profiles `ha-voice`, `chat`, `deep`, `task` in oMLX | `registry/engines.yaml` maps roles to Ollama model names directly — no separate profile step |
| **Personas** | Set **per client** — profiles can't hold a system prompt (decision #17). Open WebUI's model preset and HA's agent prompt field each get their own copy from `prompts/`, which stays the master | Same requirement, same mechanism — the router (Later section) is the one place this gets injected once instead of per-client, if you set it up |
| **Survives a reboot?** | Confirm oMLX restarts on its own | Confirm the `ollama` compose service's `restart: unless-stopped` actually brought it back (`novak status`) |

---

## Phase 5 — Start it

- [ ] `novak up`

      First run pulls several images and builds a small Python virtualenv.
      Minutes with little output — not hung.

- [ ] `novak status` — everything running, nothing restarting.
- [ ] If something crash-loops: `novak logs <service>`.

---

## Phase 6 — Memory

Full detail in [memory-setup.md](memory-setup.md). Two settings decide
whether this is private and whether it is safe. Same on both platforms.

- [ ] **VERIFY the LLM base URL** in `docker-compose.yml` against
      Hindsight's own docs if you change `HINDSIGHT_LLM_BASE_URL` — the
      default (`DEFAULT_ENGINE_BASE_URL`, same as everything else) is
      confirmed working on both reference deployments.
- [ ] **Watch the logs while storing a memory and confirm the model call
      goes to your engine, not somewhere else.** This is the check that
      proves memories are computed on your hardware. The failure is silent.
- [ ] Confirm the endpoint refuses an unauthenticated request. If it
      answers, `HINDSIGHT_API_KEY` is not taking effect and **every bank is
      open**.
- [ ] Confirm you are in **single-bank mode**. Multi-bank adds tools that
      take a bank as an argument, which lets a model pick — undoing the
      isolation.
- [ ] The web UI (`HINDSIGHT_UI_PORT`, default `13404`) is reachable over
      Tailscale/LAN only.

---

## Phase 7 — Chat

- [ ] First account created becomes admin; then disable open signup.
- [ ] Models from your engine (including profiles/roles) appear in the
      switcher.
- [ ] Ask "who are you?" — it should answer as Novak. Then ask it for an
      API key and confirm it declines.
- [ ] *(Optional)* Pocket ID sign-in. Set in `.env`, **not** in Open
      WebUI — it reads these at startup and has no admin UI for them. Needs
      a second Pocket ID client, since the redirect URI differs from the
      console's: `http://<HOST_NAME>:<OPENWEBUI_PORT>/oauth/oidc/callback`
      (default `OPENWEBUI_PORT` is `13400`). **Give this client the
      `groups` scope too**, the same one the console's client already has —
      without it, `admins.novak` never reaches Open WebUI at all and the
      admin-grant below silently does nothing.

      novak config set OWUI_OIDC_ISSUER https://<host>/.well-known/openid-configuration
      novak config set OWUI_OIDC_CLIENT_ID <id>
      novak secret set OWUI_OIDC_CLIENT_SECRET

      Leave unset for local accounts. OAuth turns on only when all three are
      present. `OWUI_OIDC_SIGNUP=true` when your IdP admits only people you
      mean to let in.

      `admins.novak` membership also grants Open WebUI admin and syncs into
      an Open WebUI group of the same name, so one Pocket ID group governs
      both surfaces — see `.env.example`'s `OWUI_OIDC_*` block. **VERIFY**
      the actual claim shape by decoding the ID token after your first
      Pocket ID login through Open WebUI; an unmatched claim path grants
      nothing rather than granting admin to everyone, but it should still
      be confirmed rather than assumed.

- [ ] Register the MCP servers (Admin → Settings → Tools). `novak registry`
      prints each URL and the secret it needs.

      **Where the URL comes from depends on the entry kind.** An `external`
      entry keeps its address in `$NOVAK_HOME/registry/mcp-servers.yaml` as
      `url:` — there is no separate URL variable, and that is not an
      omission. A `container` entry Novak runs itself takes both halves
      from `.env` (e.g. `VIKUNJA_URL`, `HA_MCP_URL`). See
      [cli.md](cli.md#where-each-kind-of-setting-lives).

      The token is always resolved through `novak secret`, and `auth:` in
      the registry names it rather than holding it — you paste the value
      into the client's registration as an Authorization header.
      - Outline — whatever URL you configured for it (`https://<your-outline>/mcp`)
      - Hindsight — `http://<host>:<HINDSIGHT_PORT>/mcp/<your-bank>/` (default port `13403`)
      - Vikunja — wherever `VIKUNJA_URL` points
- [ ] If Open WebUI is reached through a separate proxy host (public or
      LAN-neighboring, see [proxy.md](proxy.md)), these URLs must be
      reachable **from there** — Tailscale names, not `<host>.local`.
- [ ] Create a second account and confirm it cannot see the first's chats.

---

## Phase 8 — Voice *(optional; skip to come back later)*

See [home-assistant.md](home-assistant.md). Not yet set up on the Unraid
reference deployment as of this writing — tracked as open follow-up work,
not verified there.

- [ ] HACS: install **Custom Conversation**
      (<https://github.com/michelle-avery/custom-conversation>), and point
      it at your engine's base URL (`DEFAULT_ENGINE_BASE_URL`, or the
      router once set up) with the `ha-voice` role's model name. Keep HA's
      built-in Assist API for device control; tools come via MCP below.
      Decision 19 covers why not the other two candidates.
- [ ] Wyoming integrations: STT (`WHISPER_PORT`, default `13405`), TTS
      (`PIPER_PORT`, default `13406`), wake word (`OPENWAKEWORD_PORT`,
      default `13407`).
- [ ] MCP integration → the household bank. **The household bank only.**
      Never a personal one: anyone who talks to a satellite would reach it,
      and a microphone cannot tell who is speaking.

      **This does not work pointed straight at Hindsight.** HA's MCP client
      authenticates by OAuth only; Hindsight takes a static API key in a
      header. Pointing it directly at Hindsight's MCP URL gives:

          httpx.HTTPStatusError: Client error '401 Unauthorized'

      Put a proxy in front that adds the Authorization header, restricted
      to HA's address — see [proxy.md](proxy.md). Decision 20 has the
      reasoning and what the alternatives cost.
- [ ] **openwakeword crash-loops until a model matching `WAKEWORD_MODEL`
      exists** in `$NOVAK_HOME/wakeword/models/`. Set a stock word
      (`ok_nabu`) until you have trained one. **VERIFY** whether the image
      wants `.tflite` or `.onnx` — the docs mention both.
- [ ] Assist pipeline named "Novak". Test a device command, then a memory
      question.
- [ ] Answers are one or two sentences with no markdown. If it rambles, the
      voice persona did not take.

---

## Phase 9 — The console *(optional; genuinely skippable)*

Lives in [novak-konzol](https://github.com/almadon/novak-konzol). Everything
it does can be done by editing the registry by hand, so skip it unless you
want it. Same on both platforms — the published image is `linux/amd64`,
native on Unraid, emulated (but fast) on Apple Silicon.

Skipping is a real option: the console sits behind a compose profile, so
leaving `OIDC_ISSUER`, `OIDC_CLIENT_ID` or `CONSOLE_AUTH_SECRET` unset skips
it and starts everything else. `novak up` says which values were missing.
Set them and re-run to add it later.

- [ ] `novak logs console` — started rather than crash-looping.
- [ ] Sign-in via Pocket ID redirects and comes back.
- [ ] **Test the gate, not the button.** With an account *not* in
      `admins.novak`, a direct `PUT /api/admin/registry` must return 403 —
      a hidden button proves nothing.
- [ ] Remove yourself from `admins.novak` and retry an admin action
      **without logging out**. It should fail immediately.

---

## Phase 10 — Unattended operation

The point of the whole exercise: it comes back without you. `novak
checklist`'s Phase 10 runs the checks in this table's bottom row directly
on either platform.

| | macOS | Unraid |
|---|---|---|
| **Login items** | OrbStack and oMLX, **as `novak`** — per-account, setting them as yourself does nothing here. | N/A — one Docker daemon, no per-account app launch. |
| **Auto-start mechanism** | A LaunchAgent. `bootstrap.sh` has already created `~/Library/LaunchAgents` and installed the plist with your checkout path substituted in — you only load it: `launchctl load ~/Library/LaunchAgents/one.a64.novak.stack.plist`. Don't `cp` the template by hand — it carries a placeholder, not a path. **Set your secrets before loading it** — `up.sh` exits non-zero on a missing secret, and `KeepAlive` retries every 60s, so loading early gets a failure loop in `/tmp/novak-stack.err` instead of a stack. | Compose Manager's own per-project `autostart` — confirm it's `true` (`novak checklist`, or `cat $NOVAK_HOME/autostart`). Separately, the `novak` CLI symlink itself needs `/boot/config/go` to survive a reboot (`bootstrap-unraid.sh` adds this; `novak checklist` confirms the line is present). |
| **Tailscale** | Runs as a system daemon, node tagged. Per-user Tailscale is invisible to other accounts, and user-owned keys expire (180 days) — the machine would silently leave the tailnet with nobody there to re-auth it. See [headless-operation.md](headless-operation.md). | Unraid's Tailscale plugin runs system-wide already — no per-account split to worry about. Still tag the node and avoid user-owned keys for the same expiry reason. |
| **Verify** | `tailscale status --json` shows tags and no key expiry. | Same command. |
| **Remote recovery hardware** | KVM: HDMI and USB to the Mac, Tailscale installed **on the KVM itself**. **UPS priority: KVM first, network gear second, Mac last** — a Mac that lost power is recoverable remotely; a Mac you cannot reach is not. UPS data cable connected so macOS shuts down cleanly. | Unraid's own webUI/IPMI (if the board has it) generally covers this without extra hardware — VERIFY for your specific board. UPS: array integrity matters more than clean shutdown timing here, since parity is checked on unclean shutdown; connect a UPS data cable via Unraid's own UPS settings if you have one. |

---

## Phase 11 — The test that counts

Do this deliberately, while you have time to fix what it finds. **Neither
platform's reference deployment has been through this yet** — tracked
explicitly as open, not assumed fine because the design says it should be.

| | macOS | Unraid |
|---|---|---|
| **Remote-unlock check** | Reach the KVM from a phone on cellular, with home wifi off — proves the unlock path isn't secretly LAN-dependent. `sudo fdesetup authrestart` — comes back to a logged-in session unaided. As `novak`: `ls /Users/<you>` → **Permission denied** (correct). | Reach the Unraid webUI/IPMI from a phone on cellular, with home wifi off. |
| **The real test** | **Pull the plug.** It should power back on and stop at the FileVault prompt; you unlock through the KVM and it proceeds to a running stack. Finding out the KVM shows no video at that screen during a real outage is the bad way to learn it. | **Pull the plug.** Array should auto-start, Compose Manager should bring the Novak project back per its `autostart` setting, and `novak status` should show everything running with no manual step. |

---

## Later

- [ ] Train a "hey novak" wake word ([wakeword.md](wakeword.md)).
- [ ] TLS on the LAN via your existing reverse proxy ([proxy.md](proxy.md)).
- [ ] The portal — one tab per app behind a single Pocket ID login
      ([proxy.md](proxy.md#portal-a-single-page-over-open-webui-and-konzol),
      decision #22). Needs a fourth Pocket ID client and TinyAuth's three
      OIDC endpoint URLs; genuinely optional and independent of everything
      above. TinyAuth here gates the portal specifically (LAN/tailnet only)
      — it's not the same thing as auth on a public-facing proxy elsewhere;
      see decision #34 if you're running a separate TinyAuth for that.
- [ ] Brave Search — `novak secret set BRAVE_API_KEY` is the only step
      left; the registry entry already ships enabled for both Open WebUI
      and Home Assistant. See the registry's own comment on why this isn't
      Open WebUI's built-in Web Search toggle instead.
- [ ] The inference router (decision #21/#23/#28) — injects Novak's
      persona into every request instead of a copy pasted into each
      client's own config, and is what lets more than one engine
      (oMLX + Ollama, or Ollama on two hosts) sit behind one set of model
      names. Needs only your engine's own API key (already set in Phase 4
      if auth is on) and `registry/engines.yaml` — see
      [engines.md](engines.md).

      novak router apply
      novak restart router

      Then point Open WebUI at it:

      novak config set OWUI_INFERENCE_BASE_URL http://host.docker.internal:13402/v1

      Same model names, same dropdown, just pointed at the router. **Home
      Assistant needs more than a URL change**: its conversation agent is
      configured with the engine's own long model id (e.g.
      `Qwen3-4B-Instruct-2507-4bit:ha-voice` on oMLX), and the router only
      knows the *short* role name (`ha-voice`) — set the model field to
      that, not the long id, and clear the system prompt field you set
      there under [home-assistant.md](home-assistant.md). Leaving it set
      doesn't break anything; the router never overrides a client that
      already sends its own system message, which quietly defeats the
      point of switching at all.

      Not switched over automatically for either client: confirm the
      persona actually shows up (ask it "who are you?") before trusting
      the switch. See [architecture.md](architecture.md) § Identity.
- [ ] Tududi — flip its registry entry on once it's running.
- [ ] Backups: Time Machine (macOS) covers OrbStack volumes and `~/.omlx`.
      Unraid: confirm the CA Appdata Backup plugin (or equivalent) actually
      covers `$NOVAK_HOME` and wherever `*_DATA_DIR`/`OLLAMA_DATA_DIR`
      point, if you've set them (decision #33) — not yet confirmed on the
      reference deployment.
- [ ] Check the licences marked VERIFY in [credits.md](credits.md) —
      **Outline is BSL 1.1**, which matters if anything commercial touches
      it.

## When something breaks

```
novak status          what's configured, what's running
novak logs <service>  why a container is unhappy
novak registry        what the reconciler thinks it should start
novak config          every setting and where its value comes from
novak checklist       phase-by-phase walk-through with live checks (either platform)
```

If a rebuild is easier than a diagnosis: `./scripts/reset.sh` removes
containers and keeps your config, secrets and data. `--purge-data` and
`--purge-config` exist and both ask first. **macOS only as written today**
— it hasn't been ported to Unraid; treat a reset there as manual until it
has (decision #35's open follow-up list).
