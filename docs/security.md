# Security model

The threat model is not network airgap — it's (a) preventing conversation
data from ever reaching a public model vendor, and (b) avoiding the
"OpenClaw-class" operational failures: plaintext credentials readable by
the model or an attacker, over-broad tool permissions, and prompt injection
via content the model reads.

## Rule 1 — the model gets capabilities, never credentials

API keys live in MCP server environments, sourced from macOS Keychain at
startup (`scripts/up.sh`). The model calls `search_documents`; the Outline
token never appears in a prompt, a chat log, or a memory store.

**Never paste API keys, passwords, or account numbers into chat.** Chats
are logged, summarized into memory, and re-injected into future contexts.
If you catch yourself about to paste a key, the correct move is a new MCP
server (or env var on an existing one) instead.

Add a secret:

```bash
security add-generic-password -s "novak/OUTLINE_EVERYTHING_API_KEY" -a novak -w
```

`up.sh` loads any `novak/*` Keychain item over the `.env` value.

## Rule 2 — least privilege per integration

- One token per integration, scoped as tightly as the service allows;
  read-only unless writing is the point.
- Destructive operations disabled by default (the Vikunja MCP server ships
  this way — leave `ENABLE_*_DELETE` unset; Vikunja has no trash).
- When adding email later: start read-only (search/read). Sending mail
  gets a separate, explicit opt-in — see Rule 3.

## Rule 3 — treat retrieved content as untrusted input

An email or web page the model reads can contain instructions aimed at the
model ("forward this thread to..."). Mitigations, in order of importance:

1. **Capability asymmetry**: reading tools are cheap to grant; *acting*
   tools (send email, pay bill, delete) must be rare, separate, and
   confirmation-gated. If the model can't send, injected instructions
   can't exfiltrate.
2. **Confirmation gates**: any MCP tool with outward side effects should
   require a confirm parameter/step, and clients should surface it.
3. **Scoped sessions**: don't register the email MCP into the HA voice
   agent or into every Open WebUI model — attach powerful tools only to
   the conversations that need them.

## Rule 4 — LAN-only exposure

- Every service binds to the LAN; router forwards nothing.
- Enable oMLX API-key auth (LAN peers include IoT junk).
- Two multi-user surfaces: Open WebUI (accounts + RBAC on, signup disabled
  after your users exist) and the Console (Pocket ID OIDC; admin functions
  gated on the `admins.novak` group). Both LAN-only.
- Hindsight is multi-tenant but not a login surface: each MCP connection is
  scoped to one bank by URL, and no tool takes a bank as an argument. Its API
  key is a secret — Keychain, not `.env` — and without it the endpoint is open.
- Remote access via Tailscale only.

## Rule 5 — the stores are readable; audit them

- Console (`:3002`): review and delete memories, per user, behind Pocket ID.
- Outline: the knowledgebase is a normal wiki — correct it there.
- Open WebUI chat logs live in its Docker volume on the mini's disk.
  `data/` and `.env` are gitignored; keep the repo private regardless.

## Backups

Docker volumes (`open-webui`, `qdrant`) and `~/.omlx/settings.json` are
the state. Time Machine on the mini covers OrbStack's volume storage and
oMLX settings; verify volumes appear in the backup set after first run.
