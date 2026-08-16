# Credits

Novak is mostly other people's work wired together. This lists what it depends
on and what was evaluated, so credit is traceable and so licence obligations
can be checked before anything is published.

**Licences marked VERIFY have not been checked.** Do that before distributing
this repo or any image built from it.

## Running in the stack

| Project | Used for | Licence |
|---|---|---|
| [oMLX](https://omlx.ai) | Inference on Apple Silicon | VERIFY |
| [MLX](https://github.com/ml-explore/mlx) | Apple's array framework under oMLX | MIT |
| [Open WebUI](https://github.com/open-webui/open-webui) | Chat frontend | VERIFY (has had licence changes) |
| [Mem0](https://github.com/mem0ai/mem0) | Long-term memory | Apache-2.0 (VERIFY server) |
| [pgvector](https://github.com/pgvector/pgvector) | Vector storage in Postgres | PostgreSQL Licence |
| [Outline](https://github.com/outline/outline) | Knowledge base | BSL 1.1 — **check before any commercial use** |
| [outline-mcp-server](https://www.npmjs.com/package/outline-mcp-server) | MCP access to Outline | VERIFY |
| [Vikunja](https://vikunja.io) | Tasks | AGPL-3.0 |
| [@aimbitgmbh/vikunja-mcp](https://www.npmjs.com/package/@aimbitgmbh/vikunja-mcp) | MCP access to Vikunja | VERIFY |
| [supergateway](https://github.com/supercorp-ai/supergateway) | Wraps stdio MCP servers as HTTP | VERIFY |
| [Wyoming / Rhasspy](https://github.com/rhasspy) | Voice protocol; whisper, piper, openWakeWord services | MIT |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech to text | MIT |
| [Piper](https://github.com/rhasspy/piper) | Text to speech — **archived Oct 2025** | MIT |
| [openWakeWord](https://github.com/dscripka/openWakeWord) | Wake word detection | Apache-2.0 |
| [Pocket ID](https://github.com/pocket-id/pocket-id) | Single sign-on | VERIFY |
| [Home Assistant](https://www.home-assistant.io) | Home automation, voice pipeline | Apache-2.0 |

## Used to build the console and shim

| Project | Used for | Licence |
|---|---|---|
| [Next.js](https://github.com/vercel/next.js) | Console web framework | MIT |
| [Auth.js / NextAuth](https://github.com/nextauthjs/next-auth) | OIDC login — **v5 is pre-1.0** | ISC |
| [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) | MCP protocol in memory-mcp | MIT |
| [Zod](https://github.com/colinhacks/zod) | Input validation | MIT |
| [Express](https://github.com/expressjs/express) | HTTP server in memory-mcp | MIT |
| [PyYAML](https://github.com/yaml/pyyaml) | Registry parsing in the reconciler | MIT |

## Evaluated and not adopted

Recorded because the reasoning is worth keeping — see
[decisions.md](decisions.md). No criticism of the projects intended; several
are excellent and simply aim at a different shape of problem.

| Project | Outcome |
|---|---|
| [Tater](https://github.com/TaterTotterson/Tater) | Capable all-in-one platform; wants to own the whole system (#2) |
| [keep](https://github.com/generalbusiness-ai/keep) | Good agent memory, no concept of users (#4) |
| [Graphiti](https://github.com/getzep/graphiti) | Better at facts changing over time; too resource-hungry here (#4) |
| [Letta](https://github.com/letta-ai/letta) | Agent framework, wants to run the conversation (#4) |
| [Apple container](https://github.com/apple/container) | No compose support, memory reclamation issues (#7) |

## Under consideration

| Project | Note |
|---|---|
| [wyoming-voice-match](https://github.com/jxlarrea/wyoming-voice-match) | Speaker verification + audio cleanup. Adopt for audio quality; **not** for deciding who sees what (#9) |
| [speaker-recognition](https://github.com/EuleMitKeule/speaker-recognition) | Cleaner integration point than a text tag, but far less mature |
| [ha-mcp](https://github.com/homeassistant-ai/ha-mcp) | Rich Home Assistant control; classified `dangerous` in the registry (#10) |
| [mcp-assist](https://github.com/mike-nott/mcp-assist) | Cuts voice token use ~95% by discovering entities instead of listing them; helps the 1–2s voice target |

## On adding dependencies

Every entry above is something that can change under you. Before adding one:

1. Record it here with a link and licence.
2. Give it a `source` and `risk` block in
   [console/registry/mcp-servers.yaml](../console/registry/mcp-servers.yaml) if
   it's an MCP server.
3. Pin a version. Several existing MCP servers run `npx -y` at container start,
   which fetches the latest release every time — no pinning, and a failure if
   the network is down. That's a known weakness, tracked separately.
