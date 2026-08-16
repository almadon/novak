/**
 * Token → user_id resolution.
 *
 * The single rule this file exists to enforce: the caller never chooses the
 * user. Everything downstream takes user_id from resolveUser() and nowhere
 * else. If you find yourself adding a user_id tool parameter, stop — that
 * reintroduces the cross-user read that this design prevents.
 */

export class IdentityError extends Error {}

export interface Identity {
  userId: string;
  /** True when resolved from MEMORY_DEFAULT_USER rather than a token. */
  viaDefault: boolean;
}

export class IdentityResolver {
  private readonly tokens: Map<string, string>;
  private readonly defaultUser?: string;

  constructor(env: NodeJS.ProcessEnv = process.env) {
    this.tokens = parseTokenMap(env.MEMORY_TOKEN_MAP);
    this.defaultUser = env.MEMORY_DEFAULT_USER?.trim() || undefined;

    if (this.tokens.size === 0 && !this.defaultUser) {
      throw new IdentityError(
        "Refusing to start: set MEMORY_TOKEN_MAP or MEMORY_DEFAULT_USER.",
      );
    }
    if (this.defaultUser) {
      console.warn(
        `[memory-mcp] MEMORY_DEFAULT_USER=${this.defaultUser} is set. ` +
          "Unauthenticated callers will be treated as this user. Prefer per-client tokens.",
      );
    }
  }

  /**
   * @param authorization raw Authorization header, if any
   * @throws IdentityError when the caller cannot be identified
   */
  resolve(authorization: string | undefined): Identity {
    const token = extractBearer(authorization);

    if (token) {
      const userId = this.lookup(token);
      if (!userId) throw new IdentityError("Unknown token");
      return { userId, viaDefault: false };
    }

    if (this.defaultUser) {
      return { userId: this.defaultUser, viaDefault: true };
    }

    throw new IdentityError("Missing bearer token");
  }

  /** Constant-time-ish lookup: always compare against every token. */
  private lookup(token: string): string | undefined {
    let found: string | undefined;
    for (const [candidate, userId] of this.tokens) {
      if (timingSafeEqual(candidate, token)) found = userId;
    }
    return found;
  }
}

function parseTokenMap(raw: string | undefined): Map<string, string> {
  if (!raw?.trim()) return new Map();

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new IdentityError("MEMORY_TOKEN_MAP is not valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new IdentityError('MEMORY_TOKEN_MAP must be an object: {"token": "user_id"}');
  }

  const map = new Map<string, string>();
  for (const [token, userId] of Object.entries(parsed as Record<string, unknown>)) {
    if (typeof userId !== "string" || !userId.trim()) {
      throw new IdentityError(`MEMORY_TOKEN_MAP: user_id for a token is not a non-empty string`);
    }
    if (token.length < 16) {
      // Short tokens are guessable and this is the only thing standing between
      // a LAN device and someone's memories.
      throw new IdentityError("MEMORY_TOKEN_MAP: tokens must be at least 16 characters");
    }
    map.set(token, userId);
  }
  return map;
}

function extractBearer(header: string | undefined): string | undefined {
  if (!header) return undefined;
  const match = /^Bearer\s+(.+)$/i.exec(header.trim());
  return match?.[1]?.trim() || undefined;
}

/** Length-independent comparison; avoids leaking token length via early exit. */
function timingSafeEqual(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length ^ b.length;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}
