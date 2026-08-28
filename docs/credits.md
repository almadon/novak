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
| [Hindsight](https://github.com/vectorize-io/hindsight) | Long-term memory — serves MCP natively | MIT |

| [Outline](https://github.com/outline/outline) | Knowledge base | BSL 1.1 — **check before any commercial use** |
| [outline-mcp-server](https://www.npmjs.com/package/outline-mcp-server) | MCP access to Outline | VERIFY |
| [Vikunja](https://vikunja.io) | Tasks | AGPL-3.0 |
| [Tududi](https://github.com/chrisvel/tududi) | Tasks — **serves MCP natively**, no adapter needed | VERIFY |
| [@aimbitgmbh/vikunja-mcp](https://www.npmjs.com/package/@aimbitgmbh/vikunja-mcp) | MCP access to Vikunja | VERIFY |
| [Brave Search API](https://api.search.brave.com/) | Web search, shared by Open WebUI and Home Assistant | Proprietary API, free tier |
| [@modelcontextprotocol/server-brave-search](https://github.com/modelcontextprotocol/servers) | MCP access to Brave Search | MIT |
| [supergateway](https://github.com/supercorp-ai/supergateway) | Wraps stdio MCP servers as HTTP — now actually running (brave-search), previously catalogued but unused | VERIFY |
| [Wyoming / Rhasspy](https://github.com/rhasspy) | Voice protocol; whisper, piper, openWakeWord services | MIT |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Speech to text | MIT |
| [Piper](https://github.com/OHF-Voice/piper1-gpl) | Text to speech. Development moved to the Open Home Foundation as `piper1-gpl`; the old `rhasspy/piper` repo was archived Oct 2025 and its banner is widely misread as abandonment | GPL-3.0 |
| [openWakeWord](https://github.com/dscripka/openWakeWord) | Wake word detection | Apache-2.0 |
| [Pocket ID](https://github.com/pocket-id/pocket-id) | Single sign-on | VERIFY |
| [Home Assistant](https://www.home-assistant.io) | Home automation, voice pipeline | Apache-2.0 |
| [Caddy](https://github.com/caddyserver/caddy) | Reverse proxy in front of the portal | Apache-2.0 |
| [TinyAuth](https://github.com/tinyauthapp/tinyauth) | Forward-auth for the portal, against Pocket ID | AGPL-3.0 |
| [LiteLLM](https://github.com/BerriAI/litellm) | Inference router — persona injection in front of oMLX (decision #21/#23) | MIT for everything used here; an `enterprise/` subdirectory is separately licensed and not enabled |

## Used to build the console and shim

| Project | Used for | Licence |
|---|---|---|
| [Next.js](https://github.com/vercel/next.js) | Console web framework | MIT |
| [Auth.js / NextAuth](https://github.com/nextauthjs/next-auth) | OIDC login — **v5 is pre-1.0** | ISC |
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
| [Mem0](https://github.com/mem0ai/mem0) | No image for the current server, no MCP; needed a first-party shim (#3) |
| [supermemory](https://github.com/supermemoryai/supermemory) | Namespace is a caller-supplied parameter, not connection-bound (#4) |

## Under consideration

| Project | Note |
|---|---|
| [wyoming-voice-match](https://github.com/jxlarrea/wyoming-voice-match) | Speaker verification + audio cleanup. Adopt for audio quality; **not** for deciding who sees what (#9) |
| [speaker-recognition](https://github.com/EuleMitKeule/speaker-recognition) | Cleaner integration point than a text tag, but far less mature |
| [ha-mcp](https://github.com/homeassistant-ai/ha-mcp) | Rich Home Assistant control; classified `dangerous` in the registry (#10) |
| [Open Terminal](https://github.com/open-webui/open-terminal) | Sandboxed terminal/file browser for Open WebUI, Apache-2.0; classified `dangerous` in the registry, ships disabled, no Docker socket mount |
| [mcp-assist](https://github.com/mike-nott/mcp-assist) | Cuts voice token use ~95% by discovering entities instead of listing them; helps the 1–2s voice target |
| [Tududi AI assistant](https://docs.tududi.com/features/ai-assistant) | Optional, off by default, and `LLM_BASE_URL` can point at oMLX — so it can use Novak's model rather than a cloud one |

## On adding dependencies

Every entry above is something that can change under you. Before adding one:

1. Record it here with a link and licence.
2. Give it a `source` and `risk` block in
   [registry/mcp-servers.yaml](../registry/mcp-servers.yaml) if
   it's an MCP server.
3. Pin a version. Several existing MCP servers run `npx -y` at container start,
   which fetches the latest release every time — no pinning, and a failure if
   the network is down. That's a known weakness, tracked separately.
4. If it's AGPL (Vikunja, TinyAuth), that licence's obligation triggers on
   modifying the source and offering the modified version as a network
   service — not on merely running it. Both are run unmodified here,
   straight from the published image, which is the low-risk case. That
   stops being true the moment either gets patched and redeployed without
   publishing the change.
