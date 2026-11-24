# Setting up Novak

This is the setup in the order you actually do it, which is not the order the pieces are described
anywhere else. It is written for an Unraid host with a GPU, which is the reference deployment (Spire). On a
Mac the steps differ in a few places, and [macos.md](macos.md) lists those phase by phase.

> **Verified on the reference host, but not on every path through this list.** Anything marked **VERIFY**
> could not be checked without hardware this project doesn't have, such as a different NAS or a GPU from
> another vendor. Expect to fix things on a first install. That is normal and not a sign it's broken.

It takes an evening for the stack, plus model downloads. Voice and the console can wait for another day,
because the assistant works without them. `novak checklist` walks through the same phases and runs the
checks it can, so you can use either.

---

## Phase 0: Before you touch the host

- [ ] **Hardware.** Any Unraid 7.x box. The reference host has an AMD RDNA 4 card with 16 GB of video memory
      running models through Vulkan ([ollama-settings.md](ollama-settings.md) has the real throughput).
      Novak also runs on the CPU alone, slowly.
- [ ] **Power loss.** In Settings, Disk Settings, confirm "Enable auto start" for the array is on. Nothing
      here is encrypted at rest by default, so there is no unlock prompt to plan around. Details are in
      [headless-operation.md](headless-operation.md).
- [ ] **Console only:** register an OIDC client in Pocket ID with the `groups` scope, the redirect URI
      `http://<host>:<CONSOLE_PORT>/api/auth/callback/pocketid` for every hostname you will use (the default
      `CONSOLE_PORT` is `13401`), and an `admins.novak` group with you in it.

---

## Phase 1: Admin setup

Unraid has one real admin account, root, so there is no account split.

- [ ] Clone this repository onto the host (for example under your cache pool) and, as root, run
      `./scripts/bootstrap-unraid.sh`. It puts the `novak` command on your PATH, adds a line to
      `/boot/config/go` so that survives a reboot (`/usr/local/bin` doesn't, because Unraid rebuilds it in
      memory), and asks where this deployment's config should live (`NOVAK_HOME`, remembered in
      `/boot/config/novak/novak_home`).
- [ ] `novak checklist` checks that you are root and that the array starts by itself.

---

## Phase 2: The CLI

- [ ] `command -v novak` should print `/usr/local/bin/novak`. The bootstrap script already did the work, so
      there is nothing else to do here. If it prints nothing, see [cli.md](cli.md).
- [ ] There is one Docker daemon for the whole host, running as root, so you won't meet the per-account
      confusion macOS has.

---

## Phase 3: Configure

Secrets live in a file called `secrets.env`, next to `.env`, readable only by root (mode 600). `.env` holds
settings and nothing secret, so you can print it. `novak secret verify` checks the file's permissions. See
[security.md](security.md) for why this is a lower bar than a keychain and what it protects.

- [ ] `novak status` lists exactly what is unset and the command to set each, so you won't need a text
      editor.
- [ ] Set the address other machines use to reach this host:

      novak config set HOST_NAME <name other machines use to reach this host>

      `HOST_NAME` must work from elsewhere, and a Tailscale name does. `localhost` won't, because it ends
      up in URLs handed to browsers and Home Assistant. Set `VIKUNJA_URL` only if you use Vikunja.

- [ ] Store the secrets:

      novak secret set HINDSIGHT_API_KEY     # openssl rand -hex 32
      novak secret set WEBUI_SECRET_KEY --generate

      `WEBUI_SECRET_KEY` isn't required to start, but without it Open WebUI makes up a random one on every
      container start, which silently logs everyone out on the next `novak up` or restart. Ollama has no
      key of its own, and `novak status` names anything else it needs.

- [ ] `novak status` again: **Config: ready**.
- [ ] `novak secret verify`: every secret reads back, and `secrets.env` shows `ok` (600).

---

## Phase 4: The model

The engine is Ollama, with `registry/engines.yaml` mapping Novak's role names (`chat`, `ha-voice`, `task`,
`deep`, `code`) to model tags. See [engines.md](engines.md) and [ollama-settings.md](ollama-settings.md).

- [ ] **Get the models.** For example `docker exec <ollama-container> ollama pull qwen3:4b-instruct` and
      `qwen3:14b`, plus `qwen2.5-coder:14b` for the `code` role. The voice and task roles use an 8k-context
      variant of the 4B model, which [ollama-settings.md](ollama-settings.md) shows how to create. A larger `deep` model is optional, and
      [ollama-settings.md](ollama-settings.md) explains which quantizations fit your GPU before you assume a
      27B-class model does.
- [ ] **Context length.** Every model runs with an 8,192-token window (`OLLAMA_CONTEXT_LENGTH`), and Ollama
      cuts off anything longer without saying so. Keep prompts and tool lists small. This is the single
      most useful thing to know about the stack.
- [ ] **Idle time.** `OLLAMA_KEEP_ALIVE` is one server-wide value, because Ollama has no per-model setting.
      Without a long keep-alive the first request after a quiet period waits for a model to load.
- [ ] **Roles.** Edit `registry/engines.yaml` in `$NOVAK_HOME`, then `novak router apply` and
      `novak restart router`.
- [ ] **Personas** are set per client or injected by the router, and `prompts/` stays the master copy
      (decision #17).
- [ ] **Survives a reboot?** The `ollama` service uses `restart: unless-stopped`, so `novak status` should
      show it back after a restart.

---

## Phase 5: Start it

- [ ] `novak up`

      The first run pulls several images and builds a small Python environment. Expect minutes with little
      output. It isn't hung.

- [ ] `novak status`: everything running, nothing restarting.
- [ ] If something crash-loops, `novak logs <service>` says why.

---

## Phase 6: Memory

The detail is in [memory-setup.md](memory-setup.md). Two settings decide whether memory is private and
whether it is safe.

- [ ] **VERIFY the model address** in `docker-compose.yml` against Hindsight's own documentation if you
      change `HINDSIGHT_LLM_BASE_URL`. The default (`DEFAULT_ENGINE_BASE_URL`, the same as everything else)
      works on the reference host.
- [ ] **Watch the logs while you store a memory** and confirm the model call goes to your engine and not
      somewhere else. This proves memories are computed on your hardware, and the failure is silent.
- [ ] Confirm the endpoint refuses an unauthenticated request. If it answers, `HINDSIGHT_API_KEY` isn't
      taking effect and every bank is open.
- [ ] Confirm you are in single-bank mode. Multi-bank adds tools that take a bank as an argument, which lets
      a model pick one and undoes the isolation.
- [ ] The Hindsight web UI is on localhost only on the reference host. Reach it over SSH or Tailscale
      forwarding rather than opening it up.

---

## Phase 7: Chat

- [ ] The first account created becomes admin. After that, disable open signup.
- [ ] Models from your engine appear in the model switcher.
- [ ] Ask "who are you?" and it should answer as Novak. Then ask it for an API key and confirm it declines.
- [ ] **Optional: Pocket ID sign-in.** Set these in `.env`, not in Open WebUI, because Open WebUI reads them
      at startup and has no admin page for them. They need a second Pocket ID client, because the redirect
      URI differs from the console's: `http://<HOST_NAME>:<OPENWEBUI_PORT>/oauth/oidc/callback` (the default
      `OPENWEBUI_PORT` is `13400`). Give this client the `groups` scope too. Without it, `admins.novak`
      never reaches Open WebUI and the admin grant silently does nothing.

      novak config set OWUI_OIDC_ISSUER https://<host>/.well-known/openid-configuration
      novak config set OWUI_OIDC_CLIENT_ID <id>
      novak secret set OWUI_OIDC_CLIENT_SECRET

      Leave these unset for local accounts. Single sign-on turns on only when all three are present, and
      `OWUI_OIDC_SIGNUP=true` is for when your identity provider admits only people you mean to let in.
      Once Pocket ID works, you can turn the local login form off (`OWUI_ENABLE_LOGIN_FORM=false` and
      `OWUI_ENABLE_PASSWORD_AUTH=false`) so a password with no second factor can't be used.

      `admins.novak` membership also grants Open WebUI admin and syncs into a group of the same name, so one
      Pocket ID group governs both. **VERIFY** the real claim shape by decoding the ID token after your
      first login. A claim path that doesn't match grants nothing rather than granting admin to everyone,
      but you should confirm it instead of assuming.

- [ ] **Tools and presets.** Open WebUI's tool connections and the model presets are declared in
      `registry/openwebui.yaml` and applied with `novak owui apply` (it needs `OWUI_ADMIN_API_KEY`, made on
      a service account and not a person's own account). `novak owui drift` shows what differs. The gateway
      is the one connection that carries each person's tools, so you don't register services by hand. See
      [gateway.md](gateway.md).
- [ ] If Open WebUI is reached through a separate proxy host, the addresses it uses must work from there, so
      use Tailscale names and not `<host>.local`. See [proxy.md](proxy.md).
- [ ] Create a second account and confirm it can't see the first one's chats.

---

## Phase 8: Voice *(optional; skip it and come back later)*

See [home-assistant.md](home-assistant.md). This is set up and verified on the reference host (decisions
#39 to #42).

- [ ] Add Home Assistant's own **LiteLLM** integration (Settings, Devices & Services, Add Integration;
      built in since 2026.8, so there is nothing to install from HACS). Point it at the router's address
      and add a conversation agent for the `ha-voice` role. Leave "Assist" as the only tool source and don't
      attach MCP tools, because the voice model's 8,192-token window can't hold their definitions. Then add
      the new agent to your Assist pipeline (Settings, Voice assistants), because adding the integration
      doesn't do that. On Home Assistant versions before 2026.8, use Custom Conversation from HACS (see
      the "History" section of [home-assistant.md](home-assistant.md)).
- [ ] **Keep the exposed entities short.** Every entity you expose to Assist adds text to every voice
      request. Hundreds of them, such as update and button entities, can push a request past the context
      window and Assist will report "error connecting to the API". Expose lights, switches, covers and
      what you'd actually ask for.
- [ ] **Persona: let Home Assistant pull it** (decision #53). Bind the `persona` service to the host's
      Tailscale address (`novak config set PERSONA_BIND ...`, then `novak up`), add the REST sensor to
      Home Assistant's `configuration.yaml`, and set the agent's Instructions to the template that reads
      it. Exact steps are in [home-assistant.md](home-assistant.md).
- [ ] **Optional: pull-health check.** Make a second, non-admin Home Assistant user, create a long-lived
      token from its own profile page, then `novak config set HA_URL ...` and
      `novak secret set HA_DRIFT_TOKEN`. `novak drift --live` then confirms the sensor exists and matches
      the repository. Never use an admin token for this.
- [ ] **Speech to text and back.** Use Home Assistant's own Whisper and Piper add-ons (decision #39) and
      install both from the Store if they aren't there. Wake word detection comes from Novak's own stack
      (`OPENWAKEWORD_PORT`, default `13407`), because Home Assistant has no native equivalent for
      server-side wake words on Wyoming satellites.
- [ ] **Memory for voice is the household bank only.** Never a personal bank. Anyone who talks to a
      satellite would reach it, and a microphone can't tell who is speaking. Home Assistant's MCP client
      authenticates with OAuth only and Hindsight takes a static key, so it can't point at Hindsight
      directly (you'd get a `401 Unauthorized`). Put a proxy in front that adds the header, restricted to
      Home Assistant's address. See [proxy.md](proxy.md) and decision #20.
- [ ] **The wake word service crash-loops until a model matching `WAKEWORD_MODEL` exists** in
      `$NOVAK_HOME/wakeword/models/`. Use a stock word (`ok_nabu`) until you have trained one. Whether the
      image wants `.tflite` or `.onnx` files is **VERIFY**, because its documentation mentions both.
- [ ] Make an Assist pipeline called "Novak". Test a device command, then a memory question.
- [ ] Answers should be one or two sentences with no markdown. If it rambles, the voice persona didn't
      take.

---

## Phase 9: The console *(optional; skip it if you don't want it)*

The console is in `console/` in this repository. Everything it does can be done by editing the registry by
hand, so skip it unless you want it. It sits behind a compose profile, so leaving `OIDC_ISSUER`,
`OIDC_CLIENT_ID` or `CONSOLE_AUTH_SECRET` unset skips it and starts everything else. `novak up` says which
values were missing, and you can set them and run it again later.

- [ ] `novak logs console`: it started and isn't crash-looping.
- [ ] Signing in through Pocket ID redirects and comes back.
- [ ] **Test the gate, not the button.** With an account that isn't in `admins.novak`, a direct
      `PUT /api/admin/registry` must return 403. A hidden button proves nothing.
- [ ] Remove yourself from `admins.novak` and retry an admin action without logging out. It should fail
      right away.

---

## Phase 10: Unattended operation

The point of all of this is that it comes back without you. [headless-operation.md](headless-operation.md)
explains each piece. `novak checklist` checks the first three of these directly.

- [ ] The array starts by itself (Settings, Disk Settings).
- [ ] Docker starts by itself, and the Novak services use `restart: unless-stopped`.
- [ ] If you use the Compose Manager plugin, its `autostart` flag is `true` (`cat $NOVAK_HOME/autostart`).
      The reference host doesn't use it and still starts cold with no help.
- [ ] The `novak` command comes back after a reboot, because `/boot/config/go` has its line.
- [ ] Tailscale is the Unraid plugin, the node is tagged, and `tailscale status --json` shows no key expiry.
      A key tied to a person expires and the host drops off the tailnet with nobody there to sign in again.
- [ ] You can reach the machine when the operating system is down, through IPMI or a network KVM (the
      reference host has a KVM).
- [ ] A UPS with its data cable connected to Unraid (Settings, UPS Settings), so an outage ends in a clean
      shutdown and not a parity check.

---

## Phase 11: The test that counts

Do this on purpose, while you have time to fix what it finds. The reference host starts everything on a
cold boot with no manual step (decision #37, and confirmed again on the stack as it runs today), so you
are checking that yours does the same.

- [ ] Reach the Unraid web UI from a phone on cellular with home wifi off. That proves remote access isn't
      secretly depending on the LAN.
- [ ] **Pull the plug**, or reboot from the web UI. The array should start, Docker should bring the Novak
      services back, and `novak status` should show everything running with no manual step.

---

## Later

- [ ] Train a "hey novak" wake word ([wakeword.md](wakeword.md)).
- [ ] TLS on the LAN through your existing reverse proxy ([proxy.md](proxy.md)).
- [ ] The portal, with one tab per app behind a single Pocket ID login
      ([proxy.md](proxy.md#portal-a-single-page-over-open-webui-and-konzol), decision #22). It needs a
      fourth Pocket ID client and TinyAuth's three OIDC endpoint URLs, and it is optional and independent
      of everything above. TinyAuth here gates the portal only, on the LAN and tailnet, and it isn't the same
      as auth on a public-facing proxy elsewhere. See decision #34 if you run a separate TinyAuth for that.
- [ ] Brave Search. `novak secret set BRAVE_API_KEY` is the only step left. The registry entry already ships
      enabled, and the registry's own comment explains why this isn't Open WebUI's built-in Web Search
      toggle.
- [ ] The inference router (decisions #21, #23 and #28) injects Novak's persona into every request instead of
      a copy in each client, and lets more than one engine sit behind one set of model names. It needs
      `registry/engines.yaml` and nothing else. See [engines.md](engines.md).

      novak router apply
      novak restart router

      Open WebUI and Home Assistant talk to the router by its role names (`chat`, `ha-voice`), not the
      engine's own long model ids. For Home Assistant, set the model field to the short role name and clear
      the system prompt field, because the router never overrides a client that already sends its own
      system message, which quietly defeats the point. After switching either client, ask it "who are you?"
      to confirm the persona showed up. See [architecture.md](architecture.md).
- [ ] Backups. They run for the whole host outside Novak and need to cover `$NOVAK_HOME` and the gateway
      volume. [headless-operation.md](headless-operation.md#what-to-back-up) lists what matters and what to
      leave out.
- [ ] Check the licences marked VERIFY in [credits.md](credits.md). Outline is BSL 1.1, which matters if
      anything commercial touches it.

## When something breaks

```
novak status          what's configured, what's running
novak logs <service>  why a container is unhappy
novak registry        what the reconciler thinks it should start
novak config          every setting and where its value comes from
novak checklist       phase-by-phase walk-through with live checks
```

If a rebuild is easier than a diagnosis, `./scripts/reset.sh` removes containers and keeps your config,
secrets and data. It is written for macOS and hasn't been ported to Unraid, so treat a reset here as manual
for now (decision #35's follow-up list).

## See also

| Read | For |
|---|---|
| [headless-operation.md](headless-operation.md) | How the host comes back after a reboot or a power cut |
| [macos.md](macos.md) | The differences if you run on a Mac |
| [cli.md](cli.md) | Every `novak` command |
| [gateway.md](gateway.md) | The one endpoint that carries each person's tools |
| [home-assistant.md](home-assistant.md) | Voice, the persona pull and approvals |
| [security.md](security.md) | Where each secret lives and what protects it |
