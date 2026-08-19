# Setting up memory (Hindsight)

Memory runs in this stack's compose file. This covers the settings that decide
whether it is private and whether it is safe.

## Why Hindsight

It speaks MCP natively and scopes each connection to one memory "bank" by URL:

```
http://<host>:8888/mcp/<bank>/
```

The tools have no bank parameter, so a caller cannot reach another bank by
asking for it. That property is the whole reason this backend was chosen — it
is what lets different people have separate memories without a model being able
to cross between them, and it removed about 400 lines of first-party shim that
existed only to enforce the same thing over a backend that lacked it.

Postgres is embedded in the image, so it is genuinely one container.

## The two settings that matter

**1. Set `HINDSIGHT_API_KEY`, or the endpoint is open.** Authentication is off
by default. Without the tenant extension and a key, anything that can reach
port 8888 reads and writes every bank.

```bash
openssl rand -hex 32
security add-generic-password -s "novak/HINDSIGHT_API_KEY" -a novak -w
```

Run that **as the account that runs the stack** — the login keychain is
per-user. `up.sh` refuses to start while this is still `changeme`.

**2. Stay in single-bank mode.** Multi-bank mode exposes extra tools that take
a bank id as an argument. That hands the choice back to the model and undoes
the isolation the URL scoping provides. Single-bank is the default; do not
change it.

## Pointing inference at oMLX

Hindsight calls a language model to decide what is worth remembering. That
call is where your conversations could leave the machine, so it is worth
verifying rather than assuming:

```
HINDSIGHT_API_LLM_PROVIDER=openai
HINDSIGHT_API_LLM_BASE_URL=http://host.docker.internal:8080/v1
```

Provider `openai` with a local base URL, because oMLX is OpenAI-compatible.
`ollama` and `lmstudio` are also accepted, which is good evidence local setups
are a supported path rather than an afterthought.

**The base URL variable name is marked VERIFY in docker-compose.yml** — it was
not confirmed off-host. Check it against upstream's docs on first run, and
watch Hindsight's logs while storing a memory to confirm the call lands on
oMLX. That check is the one that proves privacy; the failure is silent.

## Banks

One bank per person, plus one shared:

| Bank | For | Registered in |
|---|---|---|
| `household` | voice — everyone | Home Assistant |
| `tmeuze` | one person's memories | Open WebUI, that person's account |

**Home Assistant finally works properly here.** Its MCP client cannot send an
`Authorization` header, which is why the previous backend forced voice into a
single shared identity. With the bank in the URL path, HA points at
`/mcp/household/` and is correctly scoped with no header at all.

Voice still gets the shared bank rather than a personal one, but now for the
one honest reason: a microphone cannot tell who is speaking. That is a property
of voice, not a limitation of the backend.

**Never register a personal bank in Home Assistant.** Anyone who talks to a
satellite would reach it.

## Checks worth doing

- [ ] `curl http://<host>:8888/` without the API key — should be refused. If it
      answers, the tenant extension is not configured and every bank is open.
- [ ] Store a memory while watching the logs; confirm the model call goes to
      oMLX and not outward.
- [ ] Register `hindsight-tmeuze` in Open WebUI, ask it to remember something,
      start a new conversation, ask about it.
- [ ] Confirm the household bank and a personal bank do not see each other's
      memories.
- [ ] The web UI on 9999 is reachable only over Tailscale/LAN, never the WAN.

## Upgrading

Its own image tag. The only coupling is the URL and the API key, so an upgrade
is invisible here unless the MCP surface changes — and since there is no shim
any more, there is no first-party code to fix if it does.
