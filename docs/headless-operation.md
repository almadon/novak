# Running headless

How to make the Mac come back on its own after a reboot or a power cut, and
what that costs you in security.

## The constraint nobody warns you about

**macOS will not auto-login while FileVault is enabled.** It isn't a setting to
hunt for — FileVault's pre-boot password prompt *is* the login, so there is
nothing left to automate. Any guide describing both together is describing two
machines.

So "unattended after power loss" and "disk encrypted at rest" are, on macOS, a
straight either/or. Pick deliberately.

| | Unattended boot | Encrypted at rest | Needs |
|---|---|---|---|
| **A. FileVault off + auto-login** | yes | **no** | nothing |
| **B. FileVault on, manual unlock** | no | yes | someone at the keyboard |
| **C. FileVault on + network KVM** | effectively | yes | KVM already attached |
| **D. FileVault on + UPS** | for short cuts | yes | a UPS |

**C is worth a look before you settle for A.** This fleet already runs
KVM-over-IP devices (`*.kvm.sky.a64.one`). A KVM on the Mac lets you type the
FileVault password remotely, which turns "drive home after an outage" into
"open a browser tab" — and keeps the disk encrypted. C and D combine well: the
UPS absorbs brief cuts, the KVM covers the long ones.

## The auto-login pitfall

If you go with A, know this:

**Auto-login writes the account password to `/etc/kcpassword`, obfuscated with
a fixed XOR key.** It is not encrypted. Anyone who can read that file — or the
disk, which is now unencrypted — recovers the password in seconds.

Consequences, and they are not theoretical:

- **The `novak` account must be Standard, not Administrator.** A recoverable
  password on an admin account is a recoverable root password. This single
  choice is most of what makes option A tolerable.
- **`novak`'s Keychain is reachable** by anyone with that password, and the
  Keychain is where the stack's API keys live. That is the real cost of A: not
  "someone reads my files", but "someone gets the credentials".
- Physical access already implied a lot. A makes it immediate.

Set a screen lock anyway (System Settings → Lock Screen → require password
immediately). It does not stop the services — the session stays active — it
just means a walk-past doesn't get a desktop.

## Why a dedicated user still helps

Even under A, running as `novak` rather than as yourself is worth it:

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

**1. Power profile — do this first.** It is independent of everything else, and
without it the machine sleeps after a minute:

```bash
sudo ~/novak/scripts/power.sh
```

Sets: never sleep on AC, disks stay awake, **restart automatically after a
power failure**, Power Nap off, wake-on-LAN on.

**2. Create the account.** System Settings → Users & Groups → Add User.
Choose **Standard** — not Administrator. Name it `novak`.

**3. If you chose option A**, turn FileVault off (System Settings → Privacy &
Security → FileVault), then enable auto-login for `novak` (Users & Groups →
Automatically log in as). The auto-login option is greyed out until FileVault
is fully decrypted, which takes a while on a large disk.

**4. Log in as `novak`** and install the stack there — repos, `bootstrap.sh`,
Keychain secrets. It is a separate account, so none of your setup carries over.

**5. Start on login.** Add OrbStack and oMLX to Login Items (Users & Groups →
Login Items) while logged in as `novak`, then install the LaunchAgent below to
bring the stack up once Docker is actually ready.

## The LaunchAgent

Login Items start OrbStack, but Docker isn't usable the instant the app
launches — `docker compose` run too early fails against a socket that isn't
listening yet. `scripts/launch-stack.sh` waits for it.

```bash
cp ~/novak/scripts/one.a64.novak.stack.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/one.a64.novak.stack.plist
```

Logs to `/tmp/novak-stack.log` and `/tmp/novak-stack.err`.

**It must be a LaunchAgent, not a LaunchDaemon.** Daemons run at boot with no
login session and no window server. oMLX and OrbStack are GUI applications and
cannot run there — which is the underlying reason a logged-in session is
required at all, and therefore why auto-login matters.

## Checking it worked

The only test that counts is pulling the plug.

- [ ] `pmset -g | grep -E 'autorestart|sleep'` — autorestart 1, sleep 0
- [ ] Reboot. Does it come back to a logged-in `novak` session unaided?
- [ ] `docker compose ps` as `novak` — everything running
- [ ] Voice through Home Assistant answers, with nobody having touched the Mac
- [ ] As `novak`: `ls /Users/tmeuze` → **Permission denied** (this is correct)
- [ ] Cut the power for real. Same checks.
