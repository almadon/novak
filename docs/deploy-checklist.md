# Setting up Novak

Work through this top to bottom. It is in the order you actually do things,
which is not the order the pieces are described anywhere else.

> **Nothing here has been run end to end.** This repo was written off-host.
> Anything marked **VERIFY** could not be checked without the hardware, and
> some of it will be wrong. Expect to fix things; that is normal for a first
> install, not a sign it's broken.

**Roughly how long:** an evening for the stack, plus model downloads. Voice and
the console can wait for another day — the assistant works without them.

---

## Phase 0 — Before you touch the Mac

- [ ] **A Mac with Apple Silicon.** Tuned for a Mac mini M4 with 24GB. Less
      memory means smaller models, not failure.
- [ ] **Decide about FileVault now**, because it decides whether the machine
      comes back on its own after a power cut, and it is annoying to change
      later. macOS will not auto-login while FileVault is on. Read
      [headless-operation.md](headless-operation.md) — with a network KVM you
      can keep encryption *and* recover remotely, which is the best of the
      options.
- [ ] *(Console only)* Register an OIDC client in Pocket ID with the `groups`
      scope, redirect URI `http://<host>:3002/api/auth/callback/pocketid` for
      every hostname you'll use, and an `admins.novak` group with you in it.

---

## Phase 1 — Admin setup (once, from your own account)

These need administrator rights. The account that runs Novak deliberately has
none, so they happen here instead.

- [ ] Create the service account: System Settings → Users & Groups → Add User.
      Name it `novak`, type **Standard**.
- [ ] Get any copy of this repo onto the machine and run:

      ./scripts/bootstrap-admin.sh --service-user novak

      Applies the power profile (never sleep, restart after a power failure),
      installs OrbStack and oMLX into `/Applications` so every account can run
      them, and gives `novak` a FileVault unlock token.

- [ ] `sudo fdesetup list` — **`novak` must appear.** Without this it cannot
      unlock at the pre-boot screen, and you would only find out during an
      outage.
- [ ] `pmset -g | grep -E 'autorestart|sleep'` — autorestart 1, sleep 0.

---

## Phase 2 — The novak account

Log in as `novak`. It is a separate account: none of your settings, keys or
checkouts carry over, and that is the point.

- [ ] Clone and bootstrap:

      git clone https://github.com/almadon/novak.git ~/Workspaces/Novak/novak
      cd ~/Workspaces/Novak/novak && ./scripts/bootstrap.sh

      No sudo needed. It checks Phase 1 actually happened and tells you what to
      ask for if not.

- [ ] Put the CLI on PATH — everything below uses it:

      ln -s "$PWD/scripts/novak" /usr/local/bin/novak

- [ ] **Everything from here runs as `novak`, including Docker.** Each macOS
      account has its own OrbStack VM: containers started from another account
      are invisible here, and `docker ps` will show nothing while the services
      are plainly running. If you tested from your admin account, stop those
      containers there first.
- [ ] **Launch OrbStack once by hand and click through any first-run dialog.**
      A new account usually gets one. Until it's dismissed the Docker socket
      never starts listening, and the error you get instead is an unhelpful
      `EOF`.

---

## Phase 3 — Configure

- [ ] `novak status` — it lists exactly what is unset and the command to set
      each. Nothing below needs you to open a text editor.
- [ ] Set the values it names:

      novak config set HOST_NAME <name other machines use to reach this Mac>
      novak config set VIKUNJA_URL https://<host>/api/v1

      `HOST_NAME` must be reachable from elsewhere — a Tailscale name works
      well. `localhost` will not; it ends up in URLs handed to browsers and to
      Home Assistant.

- [ ] Store the secrets. These go in the Keychain, never in a file:

      novak secret set HINDSIGHT_API_KEY     # openssl rand -hex 32
      novak secret set OMLX_API_KEY

- [ ] `novak status` again — **Config: ready**.
- [ ] Sanity check: the `.env` still shows `set-in-keychain` on every secret
      line. That literal text is never used; if you replaced it with a real
      secret, undo that and use `novak secret set` instead.

---

## Phase 4 — The model

See [../omlx/settings.md](../omlx/settings.md) for the reasoning.

- [ ] Note oMLX's port → `novak config set OMLX_PORT <port>`.
- [ ] Enable API-key auth in oMLX → `novak secret set OMLX_API_KEY`.
- [ ] Bind to the LAN; check from another machine:
      `curl http://<host>:<port>/v1/models`
- [ ] Download **Qwen3-4B-Instruct 4bit** and **Qwen3-14B 4bit**.
- [ ] Idle TTL: 15–30 min on the 14B, **none on the 4B** — voice cannot absorb
      a model load.
- [ ] Create profiles `ha-voice`, `chat`, `deep`.
- [ ] Set the personas **per client** — profiles cannot hold a system prompt
      (confirmed; see decision 17). Open WebUI's model preset and HA's agent
      prompt field each get their own copy from `prompts/`, which stays the
      master.
- [ ] Confirm oMLX restarts on its own after a reboot.

---

## Phase 5 — Start it

- [ ] `novak up`

      First run pulls several images and builds a small Python virtualenv.
      Minutes with little output — not hung.

- [ ] `novak status` — everything running, nothing restarting.
- [ ] If something crash-loops: `novak logs <service>`.

---

## Phase 6 — Memory

Full detail in [memory-setup.md](memory-setup.md). Two settings decide whether
this is private and whether it is safe.

- [ ] **VERIFY the LLM base URL** in `docker-compose.yml` against Hindsight's
      docs — the variable name was not confirmed off-host.
- [ ] **Watch the logs while storing a memory and confirm the model call goes
      to oMLX.** This is the check that proves memories are computed on your
      hardware. The failure is silent.
- [ ] Confirm the endpoint refuses an unauthenticated request. If it answers,
      `HINDSIGHT_API_KEY` is not taking effect and **every bank is open**.
- [ ] Confirm you are in **single-bank mode**. Multi-bank adds tools that take
      a bank as an argument, which lets a model pick — undoing the isolation.
- [ ] The web UI (port 9999) is reachable over Tailscale/LAN only.

---

## Phase 7 — Chat

- [ ] First account created becomes admin; then disable open signup.
- [ ] Models from oMLX (including profiles) appear in the switcher.
- [ ] Ask "who are you?" — it should answer as Novak. Then ask it for an API
      key and confirm it declines.
- [ ] Register the MCP servers (Admin → Settings → Tools). `novak registry`
      prints each URL and the token variable it needs:
      - Outline — `https://et.a64.one/mcp`
      - Hindsight — `http://<host>:8888/mcp/<your-bank>/`
      - Vikunja — `http://<host>:8002/mcp`
- [ ] Open WebUI runs on a VPS, so those URLs must be reachable **from there** —
      Tailscale names, not `mini.local`.
- [ ] Create a second account and confirm it cannot see the first's chats.

---

## Phase 8 — Voice *(optional; skip to come back later)*

See [home-assistant.md](home-assistant.md).

- [ ] HACS: install `openai-compatible-conversation`.
- [ ] Wyoming integrations: STT 10300, TTS 10200, wake word 10400.
- [ ] MCP integration → `http://<host>:8888/mcp/household/`.
      **The household bank only.** Never a personal one: anyone who talks to a
      satellite would reach it, and a microphone cannot tell who is speaking.
- [ ] **openwakeword crash-loops until a model matching `WAKEWORD_MODEL`
      exists** in `$NOVAK_HOME/wakeword/models/`. Set a stock word (`ok_nabu`)
      until you have trained one. **VERIFY** whether the image wants `.tflite`
      or `.onnx` — the docs mention both.
- [ ] Assist pipeline named "Novak". Test a device command, then a memory
      question.
- [ ] Answers are one or two sentences with no markdown. If it rambles, the
      voice persona did not take.

---

## Phase 9 — The console *(optional; genuinely skippable)*

Lives in [novak-konzol](https://github.com/almadon/novak-konzol). Everything it
does can be done by editing the registry by hand, so skip it unless you want it.

Skipping is now a real option rather than a wish: the console sits behind a
compose profile, so leaving `OIDC_ISSUER`, `OIDC_CLIENT_ID` or
`CONSOLE_AUTH_SECRET` unset skips it and starts everything else. `novak up`
says which values were missing. Set them and re-run to add it later.

**The published image is `linux/amd64`.** On Apple Silicon it runs under
emulation — it works, and starts in well under a second, but it is the only
non-native image in the stack and worth building for `arm64`.

- [ ] `novak logs console` — started rather than crash-looping.
- [ ] Sign-in via Pocket ID redirects and comes back.
- [ ] **Test the gate, not the button.** With an account *not* in
      `admins.novak`, a direct `PUT /api/admin/registry` must return 403 — a
      hidden button proves nothing.
- [ ] Remove yourself from `admins.novak` and retry an admin action **without
      logging out**. It should fail immediately.

---

## Phase 10 — Unattended operation

The point of the whole exercise: it comes back without you.

- [ ] Login Items **as `novak`**: OrbStack and oMLX. They are per-account —
      setting them as yourself does nothing here.
- [ ] Install the LaunchAgent. **`mkdir -p` is not optional** — a fresh macOS
      account has no `~/Library/LaunchAgents`, and `cp` into a missing
      directory fails:

      mkdir -p ~/Library/LaunchAgents
      cp scripts/one.a64.novak.stack.plist ~/Library/LaunchAgents/
      launchctl load ~/Library/LaunchAgents/one.a64.novak.stack.plist

      Edit the path inside if your checkout is not at `~/Workspaces/Novak/novak`.

      **Set your secrets before loading it.** `up.sh` exits non-zero when a
      required secret is missing, and `KeepAlive` retries every 60s — so
      loading it early gets you a failure loop in `/tmp/novak-stack.err`
      rather than a stack.

- [ ] **Tailscale runs as a system daemon and the node is tagged.** Per-user
      Tailscale is invisible to other accounts, and user-owned keys expire
      (180 days) — the machine would silently leave the tailnet with nobody
      there to re-auth it. See headless-operation.md.
- [ ] `tailscale status --json` shows tags and no key expiry.
- [ ] KVM: HDMI and USB to the Mac, Tailscale installed **on the KVM itself**.
- [ ] **UPS priority: KVM first, network gear second, Mac last.** A Mac that
      lost power is recoverable remotely; a Mac you cannot reach is not.
- [ ] UPS data cable connected, so macOS can shut down cleanly rather than
      being cut off mid-write.

---

## Phase 11 — The test that counts

Do this deliberately, while you have time to fix what it finds.

- [ ] **Reach the KVM from a phone on cellular, with home wifi off.** Proves
      the unlock path is not secretly LAN-dependent.
- [ ] `sudo fdesetup authrestart` — comes back to a logged-in session unaided.
- [ ] As `novak`: `ls /Users/<you>` → **Permission denied**. That is correct.
- [ ] **Pull the plug.** It should power back on and stop at the FileVault
      prompt; you unlock through the KVM and it proceeds to a running stack.
      Finding out the KVM shows no video at that screen during a real outage is
      the bad way to learn it.

---

## Later

- [ ] Train a "hey novak" wake word ([../wakeword/README.md](../wakeword/README.md)).
- [ ] TLS on the LAN via your existing reverse proxy ([../proxy/README.md](../proxy/README.md)).
- [ ] Tududi — flip its registry entry on once it's running.
- [ ] Time Machine covers OrbStack volumes and `~/.omlx`.
- [ ] Check the licences marked VERIFY in [credits.md](credits.md) —
      **Outline is BSL 1.1**, which matters if anything commercial touches it.

## When something breaks

```
novak status          what's configured, what's running
novak logs <service>  why a container is unhappy
novak registry        what the reconciler thinks it should start
novak config          every setting and where its value comes from
```

If a rebuild is easier than a diagnosis: `./scripts/reset.sh` removes
containers and keeps your config, secrets and data. `--purge-data` and
`--purge-config` exist and both ask first.
