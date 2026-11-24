# Running without a keyboard

How the Unraid host brings Novak back after a reboot or a power cut with nobody there, and what to check so
you find out before the first real outage. This is the reference deployment. If you run Novak on a Mac,
the macOS version of this, which has a FileVault problem Unraid doesn't, is in [macos.md](macos.md).

## What brings it back

Four things have to be true after a power cut, and each one is a separate setting:

1. **The array starts by itself.** Unraid doesn't run Docker until the array is up. In Settings, Disk
   Settings, "Enable auto start" should be on. The checklist reads `startArray` in `/boot/config/disk.cfg`
   to confirm it.
2. **The Docker service starts by itself.** Settings, Docker, "Enable Docker" and its autostart both on.
3. **The containers restart themselves.** Every service in `docker-compose.yml` has
   `restart: unless-stopped`, so the Docker daemon brings the whole stack back once it is running. The
   Compose Manager plugin also keeps a per-project `autostart` flag, and `novak checklist` reads that file
   (`$NOVAK_HOME/autostart`) too. On the reference deployment the stack no longer shows up in the Compose
   Manager list, so the restart policy is what does the work there. Whether a cold boot with the plugin
   flag set alone is enough is **VERIFY**.
4. **The `novak` command comes back.** Unraid's `/` and `/usr` are rebuilt in memory from the flash drive
   at every boot, so a symlink in `/usr/local/bin` disappears at the next reboot. `bootstrap-unraid.sh`
   adds a line to `/boot/config/go` that recreates it. Without that line the stack still runs but you
   have no CLI after a restart.

## Tailscale

Unraid's Tailscale plugin runs system-wide, so there is no per-user trap to avoid. Two things are still
worth setting. Tag the node, because a node authenticated by a person's key stops working when that key
expires (180 days by default) and the host silently leaves the tailnet, which is exactly when nobody is
there to sign in again. Then check `tailscale status --json` for the tag and for no key expiry.

Most of the stack is meant to be reachable only over Tailscale. On the reference host the router, Ollama,
the persona server, ingest, the gateway and the Brave search server are bound to the host's Tailscale
address, and Hindsight listens on localhost only. Open WebUI, the console and the wake word service are on
every interface. The bind addresses are `.env` settings (`ROUTER_BIND`, `OLLAMA_BIND`, `PERSONA_BIND`,
`INGEST_BIND`, `GATEWAY_BIND` and so on), and `novak ports` shows what is actually listening and who can reach
it.

## Power and recovery hardware

- **A UPS with its data cable connected to Unraid.** Set it up under Settings, UPS Settings, so the array
  is stopped cleanly. An unclean shutdown forces a parity check, which slows everything for hours.
- **Out-of-band access.** If the board has IPMI, or you have a network KVM, you can reach the machine when
  the operating system is down. Whether your board has this is **VERIFY**. Put the KVM and the network gear
  on the UPS before the host, because a host that lost power is recoverable remotely and one you cannot
  reach is not.
- **No disk encryption trade-off.** Unraid doesn't encrypt the array by default, so nothing waits for a
  password at boot. If you add encryption, you give that up and need a plan for typing the key.

## Where things live

| Path | What | Who owns it |
|---|---|---|
| `$NOVAK_HOME` (on the reference host, a folder on the cache pool) | `.env`, `secrets.env`, registry, `data/`, `models/`, wake word files | You. Config and data. |
| `$NOVAK_HOME/repo/novak` | This repository | git. Replaceable and never written to at runtime. |
| `/boot/config/novak/novak_home` | The one line that says where `$NOVAK_HOME` is | `bootstrap-unraid.sh` |
| Docker volumes and bind mounts | Memories, chat history, Postgres | Docker |

`.env` is readable on screen, with no secret values in it. Secrets are in `secrets.env` next to it, mode
600. That is a lower bar than a macOS Keychain, because there is no logged-in session to unlock anything,
and it is the reason file permissions are checked by `novak secret verify`.

## The test that counts

Do this on purpose, while you have time to fix what it finds. A clean reboot of the reference host brought
all eight containers it had then back with no manual step (decision #37). The stack has moved since then, with a folder
migration on 2026-10-06 and several new services, so a fresh run is **VERIFY**.

1. Run `novak status` and note what is running.
2. Reboot from the Unraid web UI (`Main`, then `Reboot`), or pull the plug if you want the real thing.
3. Without touching anything, wait for the array, then run `novak status`.
4. Everything should be running with no restart loops. If `novak` is not found, the `/boot/config/go` line
   is missing: run `scripts/bootstrap-unraid.sh` again.
5. Check that a chat in Open WebUI works and that a voice request still gets an answer. The first reply
   after a boot is slower because the model has to load.

## See also

| Read | For |
|---|---|
| [deploy-checklist.md](deploy-checklist.md) | The whole setup, phase by phase, including Phase 10 and 11 which this page expands |
| [security.md](security.md) | What each secret protects and where it is stored |
| [ollama-settings.md](ollama-settings.md) | How long models stay in memory and why |
| [macos.md](macos.md) | The same problem on a Mac, where disk encryption changes the answer |
