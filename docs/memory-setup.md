# Setting up memory (Mem0)

Memory is the one dependency Novak does not run for you. This explains why, and
what to do instead.

## Why it isn't in docker-compose.yml

Upstream publishes **no container image** for the current Mem0 self-hosted
server. Their own compose builds it from `server/Dockerfile`, and bringing it up
involves more than starting a container:

- a Postgres init script (`init-db.sh`) mounted at first boot
- Alembic schema migrations (`alembic upgrade head`)
- a bootstrap step that creates the first admin account and generates the first
  API key — **printed once, and unrecoverable afterwards**

There is an older image on Docker Hub, `mem0/mem0-api-server`, last pushed in
September 2025. It predates the current server and does not match these docs.
An earlier version of this repo referenced `mem0/mem0-server`, which does not
exist at all — that was a mistake, not a version drift.

Reproducing upstream's bootstrap inside our compose would mean owning the most
breakable parts of someone else's deployment, and re-owning them at every
upstream change. Running it as upstream intends is less work and less wrong.

It also dissolves a problem this repo used to document: `MEM0_API_KEY` is
issued *by* Mem0 at bootstrap, but was needed *before* other services started.
Setting Mem0 up first makes that ordering natural rather than awkward.

## Setting it up

```bash
git clone https://github.com/mem0ai/mem0.git
cd mem0/server
cp .env.example .env
```

Edit `.env`:

- **`POSTGRES_PASSWORD`** — required, no default.
- **Point inference at oMLX, not OpenAI.** Mem0 calls a language model to
  decide what is worth remembering, so this is the setting that determines
  whether your memories are computed locally. Confirm the exact variable names
  against upstream's `.env.example`; the base URL wants oMLX's `/v1` endpoint.
- **`MEM0_TELEMETRY=false`** — on by default.

Then:

```bash
make bootstrap
```

This starts the stack, waits for readiness, creates an admin, and prints
credentials in a `=== Ready ===` block. **Save the password and API key before
closing that terminal.** The key cannot be recovered.

Store the key where the rest of the stack expects it:

```bash
security add-generic-password -s "novak/MEM0_API_KEY" -a novak -w
```

Run that **as the account that runs Novak** — the login keychain is per-user.

## Connecting Novak to it

Set `MEM0_URL` in `$NOVAK_HOME/.env` to wherever it listens. Upstream's compose
publishes the API on **8888** (the container's own port is 8000):

```
MEM0_URL=http://host.docker.internal:8888
```

`host.docker.internal` because `memory-mcp` runs in Novak's compose project and
Mem0 runs in its own — they are not on a shared Docker network. If you put Mem0
on another host entirely, use its Tailscale address instead.

## Checks worth doing

- [ ] `curl $MEM0_URL/docs` — the OpenAPI page loads
- [ ] **`AUTH_DISABLED` is not set.** It bypasses authentication completely on
      a service holding every user's memories.
- [ ] Watch Mem0's logs while storing a memory and confirm the model call goes
      to oMLX. This is the check that proves memories are computed locally —
      the failure mode is silent and only visible here.
- [ ] `curl http://<mini>:8003/healthz` — memory-mcp is up
- [ ] Ask the assistant to remember something, then start a new conversation
      and ask about it

## Upgrading

Mem0's own repo, its own `git pull`, its own migrations. Novak's only coupling
is `MEM0_URL` and the API key — so an upgrade there is invisible here unless the
REST surface changes, in which case the single file to fix is
`memory-mcp/src/mem0.ts` in the integrations repo.
