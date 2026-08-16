/**
 * MCP server (streamable HTTP) over the Mem0 REST API.
 *
 * Structural guarantee: the server instance is built *per request*, with the
 * resolved user id closed over in the tool handlers. Tools therefore have no
 * parameter and no code path by which a caller can reference another user —
 * the isolation is a property of the construction, not of validation logic
 * someone might later weaken.
 *
 * UNVERIFIED against a running Mem0 server and against this SDK version's API.
 */
import express from "express";
import { z } from "zod";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { IdentityResolver, IdentityError } from "./identity.js";
import { Mem0Client, Mem0Error } from "./mem0.js";

const PORT = Number(process.env.PORT ?? 8000);

const identities = new IdentityResolver();
const mem0 = new Mem0Client(process.env.MEM0_URL ?? "", process.env.MEM0_API_KEY ?? "");

/** Builds a server whose tools can only ever touch `userId`. */
function buildServer(userId: string): McpServer {
  const server = new McpServer({ name: "novak-memory", version: "0.1.0" });

  server.tool(
    "search_memories",
    "Search your own stored memories by meaning.",
    { query: z.string().min(1), limit: z.number().int().min(1).max(50).optional() },
    async ({ query, limit }) => {
      const results = await mem0.search(userId, query, limit ?? 10);
      return { content: [{ type: "text", text: render(results) }] };
    },
  );

  server.tool(
    "list_memories",
    "List your own stored memories.",
    { limit: z.number().int().min(1).max(100).optional() },
    async ({ limit }) => {
      const results = await mem0.list(userId, limit ?? 50);
      return { content: [{ type: "text", text: render(results) }] };
    },
  );

  server.tool(
    "add_memory",
    "Store a durable fact about yourself for future conversations.",
    { text: z.string().min(1).max(4000) },
    async ({ text }) => {
      await mem0.add(userId, text);
      return { content: [{ type: "text", text: "Stored." }] };
    },
  );

  server.tool(
    "delete_memory",
    "Delete one of your own memories by id.",
    { id: z.string().min(1) },
    async ({ id }) => {
      const outcome = await mem0.deleteOwned(userId, id);
      const message = {
        deleted: "Deleted.",
        not_found: "No memory with that id.",
        // Deliberately identical to not_found from the caller's perspective:
        // distinguishing them would confirm the existence of another user's
        // memory to anyone probing ids.
        forbidden: "No memory with that id.",
      }[outcome];
      return { content: [{ type: "text", text: message }] };
    },
  );

  return server;
}

function render(memories: { id: string; memory?: string; text?: string }[]): string {
  if (memories.length === 0) return "No memories found.";
  return memories.map((m) => `- [${m.id}] ${m.memory ?? m.text ?? ""}`).join("\n");
}

const app = express();
app.use(express.json({ limit: "1mb" }));

app.get("/healthz", (_req, res) => res.json({ ok: true }));

app.post("/mcp", async (req, res) => {
  let userId: string;
  try {
    userId = identities.resolve(req.header("authorization")).userId;
  } catch (err) {
    if (err instanceof IdentityError) {
      res.status(401).json({ error: "Unauthorized" });
      return;
    }
    throw err;
  }

  // Stateless: a fresh server+transport per request, bound to this identity.
  const server = buildServer(userId);
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });

  res.on("close", () => {
    transport.close().catch(() => {});
    server.close().catch(() => {});
  });

  try {
    await server.connect(transport);
    await transport.handleRequest(req, res, req.body);
  } catch (err) {
    const detail = err instanceof Mem0Error ? err.message : "Internal error";
    if (!res.headersSent) res.status(500).json({ error: detail });
  }
});

app.listen(PORT, () => {
  console.log(`[memory-mcp] listening on ${PORT}`);
});
