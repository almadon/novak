# Where this got to

Working notes for picking up on the Mac mini. Delete this once the stack runs.

**Last updated:** 2026-08-19, from the development Mac. Nothing has ever run
end to end.

## What is true right now

- The repo is complete and pushed. Three repos: `novak` (this), `novak-konzol`
  (optional web console, never run), `novak-integracije` (currently no code —
  everything speaks MCP natively).
- CI passes on all three. `novak-konzol`'s image publishes to ghcr; packages
  are public.
- The design decisions are in [decisions.md](decisions.md) — 16 of them, with
  reasoning and cost. Read that before changing anything structural; several
  choices look arbitrary and are not.
- **Nothing has been verified against real hardware.** Anything marked
  `VERIFY` in any file was a guess.

## The current problem

`novak ports` reports **nothing listening on localhost**, and no Tailscale
address, after switching Tailscale to daemon mode.

Two things to separate — they are unrelated and were conflated once already:

1. **Nothing listening.** Almost certainly the containers are not running *in
   this account*. Each macOS user gets their own OrbStack VM, so containers
   started from the admin account are invisible to `novak` and `docker ps`
   comes back empty. Check: is OrbStack running in `novak`'s own session, and
   has `novak up` been run there?

2. **No Tailscale address.** `tailscale ip -4` returns nothing, so the CLI
   cannot reach the daemon. After `install-system-daemon` the per-user GUI app
   may still be running and competing — try quitting it. Confirm with
   `tailscale status` and check whether the CLI needs sudo in daemon mode.

## Sequence that should work

```bash
# as novak, in novak's own GUI session
open /Applications/OrbStack.app     # click through any first-run dialog
docker info                          # must succeed before anything else
novak status                         # what config is missing
novak up
novak ports                          # localhost should now answer
```

## Traps already hit, all documented

- Login Items, Keychain items, Docker, and Tailscale are **all per-account** on
  macOS. Something set up as the admin user does nothing for `novak`.
- OrbStack's first launch in a new account shows a dialog; until it is
  dismissed the Docker socket never listens and the error is a bare `EOF`.
- `HOST_NAME` does not affect what anything binds to — it only builds URLs.
- `pip --user` is per-account and Homebrew python refuses it; the reconciler
  uses its own virtualenv under `$NOVAK_HOME` for that reason.

## Open VERIFY items

- Hindsight's LLM base-URL variable name (`docker-compose.yml`) — the setting
  that decides whether memory extraction stays local. Failure is silent.
- Whether Hindsight has a trash, before trusting `delete` to be recoverable.
- openwakeword's model extension: `.tflite` or `.onnx`.
- Whether oMLX profiles carry a system prompt.
- The `Tailscaled install-system-daemon` path (reported working — remove this
  line once confirmed).
- Licences marked VERIFY in [credits.md](credits.md). **Outline is BSL 1.1.**

## Not started

- Konzol has three placeholder pages and a design token layer, no components.
- No interactive first-run wizard; `novak status` names what is missing.
- `docs/security.md` still uses jargon its reader found impenetrable and wants
  rewriting in the plain style of [decisions.md](decisions.md).
