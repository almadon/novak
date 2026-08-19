# Running headless

How to make the Mac come back on its own after a reboot or a power cut, and
what that costs you in security.

## The constraint nobody warns you about

**macOS will not auto-login while FileVault is enabled.** It isn't a setting to
hunt for — FileVault's pre-boot password prompt *is* the login, so there is
nothing left to automate. Any guide describing both together is describing two
machines.

So "unattended after power loss" and "disk encrypted at rest" look like a
straight either/or. There is a third way, and it is the one this setup uses.

## The path here: FileVault on, unlocked remotely by the JetKVM

The trick is that **on macOS, unlocking FileVault _is_ logging in.** Type a
FileVault-enabled account's password at the pre-boot prompt and macOS carries
those credentials through and lands you in that account's desktop session — no
second login, and no auto-login needed.

So if `novak` is FileVault-enabled, one remote password entry after a power cut
gets you: the disk decrypted, `novak` logged in, a window server running, and
therefore oMLX and OrbStack able to start. Everything auto-login was wanted for,
without any of what it costs.

Compared with turning FileVault off:

| | FileVault off + auto-login | FileVault on + KVM unlock |
|---|---|---|
| Disk encrypted at rest | no | **yes** |
| Password on disk in `/etc/kcpassword` | yes, recoverable | **no** |
| Human needed after an outage | no | one remote password entry |
| Account may be Administrator | never safe | your choice |

The cost is one deliberate action per unexpected outage. The UPS makes those
rare, and planned reboots skip it entirely (see below).

### What has to be on the UPS

**This is the part that is easy to get wrong.** Remote unlock depends on a
chain of devices, and the Mac is only the last of them. If the outage takes
down the network but not the Mac, you cannot reach the thing that unlocks it.

On the UPS, in order of importance:

1. **The JetKVM** — no KVM, no unlock. It draws almost nothing.
2. **Router and switch** — the KVM needs a network path out.
3. **The Mac mini.**

If your UPS cannot carry all three, carry the KVM and the network gear and let
the Mac drop. A Mac that lost power is recoverable remotely; a Mac you cannot
reach is not.

**Put Tailscale on the JetKVM itself.** It has native support, so the KVM joins
the tailnet as its own node — meaning the unlock path does not depend on the
internal reverse proxy, or on any other host at home being up. One less thing
in the chain that has to survive the outage that broke everything else.

### Graceful shutdown

If the UPS has a USB data cable, connect it to the Mac. macOS reads UPS battery
state natively (System Settings → Energy Saver → UPS options) and can shut down
cleanly before the battery dies, instead of the Mac being cut off mid-write.
Worth the cable — an unclean shutdown of a running Postgres is a much worse
morning than a cold boot.

### Planned reboots need no KVM at all

For updates and anything else you initiate:

```bash
sudo fdesetup authrestart
```

This stores the unlock key in memory for exactly one reboot, so the machine
comes back to a logged-in session unattended. Verified supported on this
hardware (`fdesetup supportsauthrestart` → true). Use it instead of `reboot`
and remote unlock becomes an outage-only chore.

## The auto-login pitfall — why the other path was rejected

Recorded because it is not widely known, and because it is what makes
the KVM route worth the extra hardware:

**Auto-login writes the account password to `/etc/kcpassword`, obfuscated with
a fixed XOR key.** It is not encrypted. Anyone who can read that file — or the
disk, which is now unencrypted — recovers the password in seconds.

Consequences, and they are not theoretical:

- **The account would have to be Standard, not Administrator.** A recoverable
  password on an admin account is a recoverable root password.
- **`novak`'s Keychain is reachable** by anyone with that password, and the
  Keychain is where the stack's API keys live. That is the real cost of A: not
  "someone reads my files", but "someone gets the credentials".
- Physical access already implied a lot. Auto-login makes it immediate.

None of this applies to the KVM route: nothing is written to disk, because
nothing is automated — a person types the password each time.

Set a screen lock anyway (System Settings → Lock Screen → require password
immediately). It does not stop the services — the session stays active — it
just means a walk-past doesn't get a desktop.

## Why a dedicated user still helps

Running as `novak` rather than as yourself is worth it regardless:

- **Your home is already inaccessible.** `/Users/tmeuze` is mode `700`, so
  `novak` cannot read your documents, keys, or browser data. Nothing to
  configure — verify with `ls -ld /Users/tmeuze`.
- **Blast radius.** A compromised container escaping into the `novak` session
  finds a Standard account with its own Keychain and nothing of yours.
- **No accidental coupling.** Services can't quietly grow a dependency on a
  path in your home if they can't see it.

### Keep it that way: do not give `novak` access to your home

You asked whether the stack needs to reach your home directory. **It should
not, and it is easier if it doesn't.** Everything it needs can live in
`novak`'s own space:

| | Where it goes |
|---|---|
| The repos | `/Users/novak/novak`, `/Users/novak/novak-integracije` |
| oMLX models and settings | `/Users/novak/.omlx` |
| OrbStack data | `/Users/novak/.orbstack` |
| Secrets | `novak`'s own Keychain |

There is a second, sharper reason beyond tidiness. macOS TCC guards Desktop,
Documents and Downloads behind a **permission dialog**. If anything running as
`novak` touches a protected path, macOS shows a prompt — and on a headless box,
nobody clicks it. The process hangs or silently fails, at 3am, with no
indication why. Full separation avoids an entire class of confusing failure.

If you ever do need to share a file, use `/Users/Shared` rather than opening up
your home.

## Setup

Do these as your own admin user, in order.

Setup is split in two because the service account has no administrator rights
and shouldn't: `bootstrap-admin.sh` does everything needing sudo or a
system-wide install, once; `bootstrap.sh` does the rest, as `novak`.

**1. Create the account.** System Settings → Users & Groups → Add User.
Name it `novak`. Standard is the safer default; Administrator is defensible
here since no password is being written to disk — but the stack does not need
it, so Standard unless something later proves otherwise.

**2. Run the admin half**, from your own admin account:

```bash
./scripts/bootstrap-admin.sh --service-user novak
```

Applies the power profile (never sleep, **restart after power failure**),
installs OrbStack and oMLX into `/Applications` so every account can run them,
and gives `novak` a FileVault unlock token. Without that token `novak` cannot
unlock at the pre-boot screen and the whole approach collapses — so confirm it
took, rather than assuming:

```bash
sudo fdesetup list          # novak must appear
```

**3. Log in as `novak`** and install the stack there — repos, `bootstrap.sh`,
Keychain secrets. It is a separate account, so none of your setup carries over:

```bash
git clone https://github.com/almadon/novak.git ~/novak
cd ~/novak && ./scripts/bootstrap.sh
```

`bootstrap.sh` needs no sudo. It checks the admin half has been done and tells
you exactly what to ask for if not, rather than failing halfway through.

**4. Start on login.** Add OrbStack and oMLX to Login Items (Users & Groups →
Login Items) while logged in as `novak`, then install the LaunchAgent below to
bring the stack up once Docker is actually ready.

**5. Wire up the JetKVM.** HDMI and USB to the Mac, Tailscale installed on the
KVM, and both it and the network gear on the UPS. Then test it *before* you
need it — see below.

## Where things live

Three separate concerns, deliberately not in one place:

| | Path (as `novak`) | Who owns it |
|---|---|---|
| **Code** | `/Users/novak/novak` | git — replaceable, never written to at runtime |
| **Runtime** | `/Users/novak/.novak` | you — config, per-deployment settings, data |
| **Container data** | Docker volumes | Docker — memories, chat history, Postgres |

Runtime is split out so `git pull` never conflicts with a running stack, and so
a checkout can be deleted and re-cloned without losing configuration. The
mechanism is `docker compose --project-directory`, which makes every relative
bind in `docker-compose.yml` resolve against the runtime directory rather than
the checkout.

`~/.novak` is the default. Set `NOVAK_HOME` to put it anywhere:

```bash
export NOVAK_HOME="$HOME/Almadon/Novak"
```

What ends up there:

```
~/.novak/
  .env                        config and non-Keychain settings
  registry/mcp-servers.yaml   which MCP servers THIS install runs
  wakeword/models/            wake-word models you trained
  docker-compose.mcp.yml      generated; never edit
```

**The registry lives here, not in the repo.** It records what this particular
machine runs and at what risk level — a per-deployment fact, not catalogue
content. The copy in the checkout is a starting template, copied across on
first run and yours from then on. Edit it here; the repo's copy is not read
once this exists.

### `novak` needs its own checkout

Your home directory is mode `700`, so `novak` cannot read a checkout under
`/Users/tmeuze`. That is working as intended — do not loosen it. `novak` clones
from GitHub itself:

```bash
git clone https://github.com/almadon/novak.git ~/novak
```

So there are two checkouts: yours for development, `novak`'s for running. They
meet through GitHub, not the filesystem. Deploying is `git pull` as `novak`.

### Starting over

`scripts/reset.sh` undoes what `bootstrap.sh` did, so it can be re-run:

```bash
./scripts/reset.sh                 # containers only; config and data kept
./scripts/reset.sh --purge-data    # also volumes — memories and chats gone
./scripts/reset.sh --purge-config  # also ~/.novak
```

The default is conservative on purpose: re-running bootstrap is routine and
shouldn't be a decision with consequences. Keychain secrets, oMLX models,
Homebrew and OrbStack are never touched by any flag — the script prints the
commands to remove those by hand if you actually want them gone.

## The LaunchAgent

Login Items start OrbStack, but Docker isn't usable the instant the app
launches — `docker compose` run too early fails against a socket that isn't
listening yet. `scripts/launch-stack.sh` waits for it.

```bash
cp scripts/one.a64.novak.stack.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/one.a64.novak.stack.plist
```

The plist defaults to `~/Workspaces/Novak/novak`. If your checkout is
elsewhere, edit that one line in the copy under `~/Library/LaunchAgents/`.

Logs to `/tmp/novak-stack.log` and `/tmp/novak-stack.err`.

**It must be a LaunchAgent, not a LaunchDaemon.** Daemons run at boot with no
login session and no window server. oMLX and OrbStack are GUI applications and
cannot run there — which is the underlying reason a logged-in session is
required at all, and therefore why auto-login matters.

## Checking it worked

The only test that counts is pulling the plug.

- [ ] `pmset -g | grep -E 'autorestart|sleep'` — autorestart 1, sleep 0
- [ ] `sudo fdesetup list` — `novak` is there
- [ ] **Reach the JetKVM over Tailscale from a phone on cellular**, with home
      wifi off. This proves the unlock path does not secretly depend on being
      on the home network.
- [ ] `sudo fdesetup authrestart` — comes back to a logged-in `novak` session
      with no intervention
- [ ] `docker compose ps` as `novak` — everything running
- [ ] Voice through Home Assistant answers, with nobody having touched the Mac
- [ ] As `novak`: `ls /Users/tmeuze` → **Permission denied** (this is correct)
- [ ] **Pull the plug.** The Mac should power back on and stop at the FileVault
      prompt; you unlock it through the KVM and it proceeds to a running stack.
      Do this once deliberately, when you have time — finding out the KVM has
      no video at the pre-boot screen during a real outage is the bad version.
