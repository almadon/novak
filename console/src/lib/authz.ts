/**
 * Authorization. This file is the entire access-control story — review it
 * before anything else in the console.
 *
 * Two rules:
 *   1. Every admin API route calls requireAdmin(). Middleware is defence in
 *      depth, not the gate; a route that forgets this call is unprotected.
 *   2. Mutating operations re-validate group membership against Pocket ID
 *      instead of trusting the session, so revoking admin takes effect
 *      immediately rather than at session expiry.
 */
import { auth } from "@/auth";

export const ADMIN_GROUP = "admins.novak";

export class AuthzError extends Error {
  constructor(
    message: string,
    readonly status: 401 | 403,
  ) {
    super(message);
  }
}

export interface Principal {
  /** Pocket ID subject. Primary key for all per-user state, incl. Mem0 user_id. */
  sub: string;
  email?: string;
  name?: string;
  groups: string[];
}

/** Any authenticated user. Throws AuthzError if not signed in. */
export async function requireUser(): Promise<Principal> {
  const session = await auth();
  const sub = session?.user?.sub;
  if (!sub) throw new AuthzError("Not authenticated", 401);
  return {
    sub,
    email: session.user.email ?? undefined,
    name: session.user.name ?? undefined,
    groups: session.user.groups ?? [],
  };
}

/**
 * Admin access.
 *
 * `revalidate` (default true) re-fetches groups from Pocket ID's userinfo
 * endpoint rather than reading them from the session. Keep it on for anything
 * that writes. It may be set false for read-only admin views where a stale
 * session is tolerable and the extra round-trip is not worth it.
 */
export async function requireAdmin(
  { revalidate = true }: { revalidate?: boolean } = {},
): Promise<Principal> {
  const principal = await requireUser();

  if (!revalidate) {
    if (!principal.groups.includes(ADMIN_GROUP)) {
      throw new AuthzError(`Requires group ${ADMIN_GROUP}`, 403);
    }
    return principal;
  }

  const session = await auth();
  const accessToken = session?.accessToken;
  if (!accessToken) {
    // No token to check with — fail closed rather than falling back to the
    // session's own copy of the claim.
    throw new AuthzError("Cannot verify group membership", 403);
  }

  const groups = await fetchGroupsFromProvider(accessToken);
  if (!groups.includes(ADMIN_GROUP)) {
    throw new AuthzError(`Requires group ${ADMIN_GROUP}`, 403);
  }
  return { ...principal, groups };
}

async function fetchGroupsFromProvider(accessToken: string): Promise<string[]> {
  const issuer = process.env.OIDC_ISSUER;
  if (!issuer) throw new AuthzError("OIDC_ISSUER not configured", 403);

  const res = await fetch(`${issuer.replace(/\/$/, "")}/userinfo`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new AuthzError("Group revalidation failed", 403);

  const claims: unknown = await res.json();
  const raw = (claims as Record<string, unknown>)?.groups;
  return Array.isArray(raw) ? raw.filter((g): g is string => typeof g === "string") : [];
}

/** Maps an AuthzError to a Response; rethrows anything else. */
export function authzResponse(err: unknown): Response {
  if (err instanceof AuthzError) {
    return Response.json({ error: err.message }, { status: err.status });
  }
  throw err;
}
