# Where this got to

Working notes for the Mac mini. Delete this once the stack has run for a while
unattended.

**Last updated:** 2026-08-19, from the mini (`Mitochon`) as `novak`.
**The stack has now run end to end for the first time.**

## What is true right now

- Six services up, zero restarts, reachable on both localhost and Tailscale:
  console 3002, hindsight 8888/9999, open-webui 3000, whisper 10300,
  piper 10200, openwakeword 10400.
- Tailscale: node `mitochon`, `100.120.1.110`, tagged `tag:infra`, **no key
  expiry**. `HOST_NAME` already matches, so nothing was re-pinned.
- oMLX (8080) is a host app, not a container. Still not running — start it
  separately.
- No MCP servers are running. Both enabled ones are unconfigured; see below.
- The design decisions are in [decisions.md](decisions.md). Read that before
  changing anything structural.

## What the previous notes got wrong

Both diagnoses in the old version of this file were wrong. Recorded because
the wrong guesses are plausible and someone will make them again.

1. **"Containers are running in the wrong account."** They were not running at
   all. OrbStack was fine in `novak`'s session and `docker info` succeeded;
   `novak up` had simply never been run, and could not run — `up.sh` refused to
   start while `VIKUNJA_URL` was unset. See the next section.

2. **"The CLI cannot reach the daemon."** The system daemon was reachable,
   logged in, tagged, and holding the tailnet address the whole time. What
   fails is *which* daemon the CLI picks: on macOS `tailscale` prefers a
   per-user GUI app's local API when one is running, and the installed
   **App Store build (`io.tailscale.ipn.macos`, sandboxed)** answers
   `NeedsLogin` while the system daemon underneath is up. So
   `tailscale ip -4` reported nothing about a machine that was fully online.

   `tailscale --socket=/var/run/tailscaled.socket ip -4` was the tell, and
   `novak ports` now pins that socket ([scripts/novak](../scripts/novak)).

   The old note's *remedy* — quit the GUI app — was right even though its
   reasoning was not. But quitting is not enough: it is a login item and
   relaunches within seconds.

## Still to do

- **Remove the App Store Tailscale app.** It is the sandboxed build, it cannot
  host the system daemon (see [headless-operation.md](headless-operation.md)),
  it relaunches at login, and it shadows the CLI. `novak ports` works around
  it; nothing else does. Needs a human to drag it out of /Applications and
  clear the login item.
- **Configure the memory MCP.** `MEM0_URL`, `MEM0_API_KEY`,
  `MEMORY_TOKEN_MAP`, `MEMORY_DEFAULT_USER` are declared by the `memory` entry
  in the registry but **absent from `.env.example` entirely** — so that server
  could never have started. Add them to `.env.example` and fill them in.
- **`VIKUNJA_URL` is commented out** in `~/.novak/.env` (line 25). Uncomment
  and set it, plus the `VIKUNJA_API_TOKEN` keychain item, to enable that MCP.
- Missing keychain items: `OMLX_API_KEY`, `TUDUDI_API_TOKEN`,
  `VIKUNJA_API_TOKEN`.
- The console image is `linux/amd64` and runs under emulation on this arm64
  host. Works, but worth building a native image.

## Failing soft, not hard

An unconfigured integration used to stop the entire stack. It no longer does:

- `REQUIRED_EDITS` in [vars.sh](../scripts/lib/vars.sh) now holds only
  `HOST_NAME` — the one value the whole stack needs. Anything used by a single
  MCP server or extension must not go in that list.
- The reconciler skips any enabled server whose declared `env` variables are
  unset or still placeholders, and logs which ones
  (`skipped: vikunja — not configured: VIKUNJA_URL, VIKUNJA_API_TOKEN`).
  Nothing else is affected.

This is why `novak up` now succeeds with both MCP servers unconfigured.

## Traps already hit, all documented

- Login Items, Keychain items, Docker, and Tailscale are **all per-account** on
  macOS. Something set up as the admin user does nothing for `novak`.
- OrbStack's first launch in a new account shows a dialog; until it is
  dismissed the Docker socket never listens and the error is a bare `EOF`.
- `HOST_NAME` does not affect what anything binds to — it only builds URLs.
- `pip --user` is per-account and Homebrew python refuses it; the reconciler
  uses its own virtualenv under `$NOVAK_HOME` for that reason.
- A macOS Tailscale CLI with no `--socket` may be talking to a GUI app rather
  than the daemon. Never trust a bare `tailscale status` on this machine.

## Open VERIFY items

- Hindsight's LLM base-URL variable name (`docker-compose.yml`) — the setting
  that decides whether memory extraction stays local. Failure is silent.
- Whether Hindsight has a trash, before trusting `delete` to be recoverable.
- openwakeword's model extension: `.tflite` or `.onnx`.
- Whether oMLX profiles carry a system prompt.
- Licences marked VERIFY in [credits.md](credits.md). **Outline is BSL 1.1.**

`Tailscaled install-system-daemon` is **confirmed working** — the daemon is
installed at `/usr/local/bin/tailscaled` from
`/Library/LaunchDaemons/com.tailscale.tailscaled.plist` and survives logout.

## Not started

- Konzol has three placeholder pages and a design token layer, no components.
- No interactive first-run wizard; `novak status` names what is missing.
- `docs/security.md` still uses jargon its reader found impenetrable and wants
  rewriting in the plain style of [decisions.md](decisions.md).
