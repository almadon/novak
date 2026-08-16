/**
 * Thin client for the Mem0 self-hosted REST API.
 *
 * UNVERIFIED: endpoint paths and response shapes come from Mem0's documented
 * REST surface, not from observed traffic against a running server. Check
 * these against your deployment before trusting them — see ../README.md.
 *
 * Every method takes userId explicitly and the caller must pass the value from
 * IdentityResolver. No method reads a user from its arguments object.
 */

export interface Memory {
  id: string;
  memory?: string;
  text?: string;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export class Mem0Error extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
  }
}

export class Mem0Client {
  constructor(
    private readonly baseUrl: string,
    private readonly apiKey: string,
  ) {
    if (!baseUrl) throw new Mem0Error("MEM0_URL not set");
    if (!apiKey) throw new Mem0Error("MEM0_API_KEY not set");
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) {
      // Body may contain server detail; keep it out of the message returned to
      // the model to avoid leaking internals into a chat transcript.
      throw new Mem0Error(`Mem0 request failed (${res.status})`, res.status);
    }
    return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
  }

  async search(userId: string, query: string, limit = 10): Promise<Memory[]> {
    const body = await this.request<{ results?: Memory[] } | Memory[]>("/search", {
      method: "POST",
      body: JSON.stringify({ query, filters: { user_id: userId }, limit }),
    });
    return normalizeList(body);
  }

  async list(userId: string, limit = 50): Promise<Memory[]> {
    const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
    const body = await this.request<{ results?: Memory[] } | Memory[]>(`/memories?${params}`);
    return normalizeList(body);
  }

  async add(userId: string, text: string): Promise<void> {
    await this.request("/memories", {
      method: "POST",
      body: JSON.stringify({
        messages: [{ role: "user", content: text }],
        user_id: userId,
      }),
    });
  }

  async get(id: string): Promise<Memory | undefined> {
    try {
      return await this.request<Memory>(`/memories/${encodeURIComponent(id)}`);
    } catch (err) {
      if (err instanceof Mem0Error && err.status === 404) return undefined;
      throw err;
    }
  }

  /**
   * Ownership is verified before deleting. Mem0's delete endpoint takes only a
   * memory id and does not check who owns it, so without this a caller could
   * delete another person's memory by guessing an id.
   */
  async deleteOwned(userId: string, id: string): Promise<"deleted" | "not_found" | "forbidden"> {
    const existing = await this.get(id);
    if (!existing) return "not_found";

    const owner = ownerOf(existing);
    // Fail closed: if the record carries no owner we can compare, refuse rather
    // than assume it belongs to the caller.
    if (owner === undefined || owner !== userId) return "forbidden";

    await this.request(`/memories/${encodeURIComponent(id)}`, { method: "DELETE" });
    return "deleted";
  }
}

function normalizeList(body: { results?: Memory[] } | Memory[]): Memory[] {
  if (Array.isArray(body)) return body;
  return body?.results ?? [];
}

function ownerOf(m: Memory): string | undefined {
  const direct = (m as Record<string, unknown>).user_id;
  if (typeof direct === "string") return direct;
  const nested = m.metadata?.user_id;
  return typeof nested === "string" ? nested : undefined;
}
