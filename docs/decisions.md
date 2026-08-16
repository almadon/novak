# Decisions

Why things are the way they are. Each entry says what was decided, why, what it
cost, and what would make it worth revisiting.

Written in plain language on purpose. If a sentence here needs a glossary, it's
a bad sentence — rewrite it.

All entries dated 2026-08-16 unless noted.

---

## 1. The hub is a set of services, not an app

Every client — Open WebUI, Home Assistant, the console, anything later — talks
to the same inference server and the same tools. No single program owns the
system.

**Cost:** more moving parts than one all-in-one app.
**Why anyway:** if any one piece dies or gets abandoned, the rest still works.
This has already paid off twice (see #2 and #3).

## 2. Not adopting Tater

Tater is a capable all-in-one assistant platform: it runs models, voice, memory,
and talks to Home Assistant. Rejected because it wants to *be* the system —
Home Assistant becomes a plugin of Tater rather than an equal.

Two of its supporting repos were retired within about three months of each
other while we were evaluating it, which is a lot of churn to build on.

**What it genuinely has that we don't:** firmware for purpose-built voice
satellites like the Sat1. That firmware reports to Tater's own backend, so it
can't simply be borrowed.
**Revisit if:** you want the satellite hardware more than you want the
architecture, or Tater's pace of change settles down.

## 3. Memory: OpenMemory → Mem0 self-hosted

The stack was originally built on OpenMemory. Upstream deprecated and shut it
down. Its replacement, the Mem0 self-hosted server, supports multiple users
properly — but only speaks REST, and we need MCP so Home Assistant and Open
WebUI can share one memory store.

So we added `memory-mcp/`, a small piece of our own code that puts an MCP
front door on Mem0 and decides which user a request belongs to.

**Cost:** a component to maintain, and Mem0's documentation is thin.
**Why anyway:** all the thin-documentation pain is trapped in one file
(`memory-mcp/src/mem0.ts`). Swapping memory engines later means rewriting that
file, not redoing the integration.

## 4. Memory engines we looked at and passed on

- **Graphiti** (from the Zep team) — better at facts that change over time
  ("Alice *used to* work at X"). Passed for now: it wants a graph database, and
  it calls the language model several times for every memory it stores. On a
  24GB Mac mini that's also answering voice in 1–2 seconds, that competes for
  the same hardware.
  **Revisit if:** tracking how facts change over time becomes something you
  actually want. Pair it with Kuzu or FalkorDB, not Neo4j.
- **Letta** — mature, but it's an agent framework that wants to run the
  conversation itself. That's the same shape we rejected in #2.
- **keep** — MCP-native and actively developed, but it has no concept of
  users at all, and its multi-user option is a hosted cloud service. It's a
  good tool for *agent* memory; it just can't separate people.

Note: most "best memory framework" comparison articles are marketing from
companies selling one of the options. Their benchmark numbers were not used.

## 5. There is a web console, and that's allowed

The README says "no custom web frontend." The full sentence also says: *build
UI only for things chat can't express, and build it as a view over these same
services.*

Browsing memories, editing a persona, and managing plugins are things you can't
sensibly do by chatting. So the console exists — but it owns nothing important.
If it vanished, no data would be lost.

## 6. The console has no control over Docker

The console can add and remove MCP servers. It does this by writing a file
(`registry/mcp-servers.yaml`); a separate script on the host reads that
file and starts containers.

**Why not let the console run Docker directly:** anything that can create a
container can create one that has full access to the machine. There's no way to
allow "create a container" safely. So the web-facing part simply never gets
that power.

**What this buys:** if someone breaks into the console, they can write a YAML
file. That's it. And every change is a file in git, so you can see what changed
and undo it.

## 7. Staying on OrbStack (not Apple's container tool, not Podman)

Apple's `container` reached 1.0 in June 2026 and gives each container its own
small virtual machine — better separation than OrbStack, which uses one shared
VM for everything.

Passed because:
- It has no `docker compose` support, and this whole stack is compose.
- Its memory handling doesn't reliably give RAM back to the host. On a 24GB
  machine that's also running language models, that's a real problem.
- The extra separation was mostly answering a risk we removed in #6 anyway.

Podman on macOS also runs a VM, so switching there changes a lot and gains
little.
**Revisit if:** Apple's tool gains compose support and the memory behaviour
improves.

## 8. Voice shares one memory; it does not try to tell people apart

Per-person memory works in Open WebUI and the console, because those know who
you are. Voice doesn't get it.

Two separate reasons:
1. Home Assistant's MCP client can only authenticate with OAuth — no tokens, no
   custom headers — and the connection belongs to the integration, not to a
   person.
2. More fundamentally, a voice satellite doesn't know who is talking.

So Home Assistant connects without logging in and gets a shared "household"
identity. Personal memories still require a token and stay private.

**Cost:** the port that serves household memory answers anyone who can reach
it. Keep it on Tailscale, never on the open home network.
**Revisit if:** speaker identification becomes trustworthy — but see #9, which
is not as simple as it sounds.

## 9. Speaker identification: useful, but not for deciding who sees what

`wyoming-voice-match` is the best of the options examined — good model, fits our
existing voice setup, and it cleans up audio by removing other voices before
transcription. Worth adopting for that alone.

**But it must not decide whose memories get read.** It identifies a speaker by
adding a tag to the transcript text, like `[john] what's the weather`. That tag
lives inside the words sent to the model, which means anyone who says the right
words — or any document the model reads containing that text — can claim to be
someone else. It tells you who's *probably* speaking; it doesn't prove it.

Also: it adds 200–500ms on a CPU, and it's least accurate on short phrases,
which is what voice commands are.

**Safe path if you want per-person voice memory later:** strip the tag and pick
the memory connection *before* the model sees anything, so the model never gets
a say in whose data it's reading.

## 10. Powerful integrations are allowed, but must be turned on deliberately

`ha-mcp` gives a model 88+ tools over Home Assistant, including editing config
files and creating automations. That's genuinely useful and genuinely
dangerous — especially anywhere the model reads outside content like email or
calendar entries, which could contain instructions aimed at it.

Rather than ban things like this, the registry has a risk level. Anything above
`standard` won't start until someone writes down what it can do, who accepted
that, and when. Turning it off again needs no ceremony.

The principle: your call, but make it on purpose, and leave a note for
future-you.

## 11. Where things run

The stack is spread across machines, not all on the mini.

- **Must be on the mini:** oMLX (needs Apple's GPU directly).
- **Should be near oMLX:** memory — every memory written triggers model calls.
- **Already elsewhere:** Open WebUI, on a VPS.
- **Chosen: mini** — the console, so memory reads are local.

**Cost of that last one:** login uses Pocket ID, which runs on a VPS. If the
internet is down, you can't sign in to a console that is otherwise entirely
local. Existing sessions last 8 hours, so brief outages don't lock you out.

Also worth knowing: with the model at home and Open WebUI on a VPS, chat stops
working if the link between them drops. Voice keeps working, because it's all
local. Voice is the more reliable interface, not the less.

## 12. The console lives in its own repository

The web console was extracted to a separate repo, `novak-konzol`. The registry
it edits and the reconciler that applies that registry **stayed here**.

That division is the point. The registry describes what *this* stack runs, so
it belongs to this stack; the reconciler is the only thing with power over
containers, so it stays as far from the web app as possible. What moved out is
just the user interface.

The entire interface between the two repos is one bind-mounted directory. The
console writes a file. Something else, with no network exposure, acts on it.

**The console is optional.** Editing `registry/mcp-servers.yaml` by hand and
running `reconciler/reconcile.py` is a fully supported path — the stack has no
dependency on the console existing, and the deploy checklist treats it as a
skippable section.

**Cost:** two repos to keep in step, and the console is now consumed as a
published image rather than built in place, which means its CI has to work
before it can be deployed.
**Why anyway:** it's a Next.js app with a different toolchain, different CI, and
a different release rhythm from a pile of compose files — and making the
boundary a repository boundary means it can't quietly grow tendrils into the
stack it's supposed to merely view.

## 13. Three repos: core, integrations, console

Extending #12. The split is now:

| Repo | Holds | Why there |
|---|---|---|
| `novak` (srz) | compose, docs, registry, reconciler | The orchestration and the decisions |
| `novak-integracije` | MCP servers and adapters, incl. `memory-mcp` | Capabilities, replaceable individually |
| `novak-konzol` | the web console | A client, and optional |

The dividing line is **what a given install runs** versus **what exists to be
run**. The registry says "this machine runs memory and vikunja at these risk
levels" — that's per-deployment, so it stays in core. The integrations repo is
the catalogue of things that *could* be run. Those are different questions and
they change at different rates.

The reconciler stays in core because it's the only component with power over
containers, and it should sit as far as possible from anything a third party
might contribute to.

**Cost:** three repos, and integrations are now consumed as published images —
so an integration's CI has to work before you can deploy it.
**Why anyway:** "bring your own engine, hardware, integration" only works if
adding one doesn't mean editing the core. And a store needs a shelf.

## 14. MCP servers are defined in the registry, not in compose

Consequence of #13 that's worth stating separately, because it closed a real
piece of debt: `docker-compose.yml` no longer contains any MCP server. They are
registry entries, rendered by the reconciler into a second compose file that
`scripts/up.sh` applies alongside the first.

Previously both files described the same servers, and the docs carried a
warning not to enable both or the ports would collide. That warning is gone
because the duplication is gone.

`up.sh` now runs the reconciler as a **hard gate**: if a registry entry is
enabled at `elevated` or `dangerous` without a recorded acceptance, the whole
start fails rather than quietly skipping that one service.

## 15. Internet exposure is decided per service, and the home network takes
## nothing inbound

Not everything gets the same treatment, and the split follows what each piece
was *built* to withstand.

| Service | Where | Reachable from | Why |
|---|---|---|---|
| Reverse proxy, Open WebUI | VPS (Constant) | the internet | Designed to face it: accounts, sessions, TLS at the proxy |
| oMLX | Mac | Tailscale/LAN only | An inference API with no rate limiting; assumes friendly callers |
| Mem0, memory-mcp | Mac | Tailscale/LAN only | Holds everyone's memories, and answers unauthenticated when the household identity is enabled |
| Konzol | Mac | Tailscale/LAN only | Can reconfigure the stack |
| Wyoming voice | Mac | LAN only | Talks to satellites on the local network |

**The home network forwards no ports at all.** The VPS reaches the Mac over
Tailscale. So the chat interface is usable from anywhere, while nothing at home
accepts a connection from the internet.

The useful way to think about it: *being on the internet is a property a
service has to earn by being designed for it,* not a default you grant because
it would be convenient. Open WebUI has accounts and sessions and expects
strangers to knock. oMLX does not.

**Cost:** the chat interface stops working if the link between the VPS and home
drops — the model is at home. Voice keeps working, because voice is entirely
local. Voice is the more reliable interface, not the less.

**Revisit if:** something new needs public reach. That's a per-service decision
with the same shape as a risk acceptance in the registry — write down what it
is, why it needs to face the internet, and what's in front of it.
