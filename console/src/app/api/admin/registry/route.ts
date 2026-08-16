/**
 * Admin API for the MCP registry.
 *
 * This is the reference pattern for every admin route: call requireAdmin()
 * first, and let authzResponse() turn a failure into 401/403. Middleware is
 * defence in depth — a route that skips this call is unprotected regardless of
 * what middleware.ts says.
 *
 * Note what this route does NOT do: touch Docker. Writes land in the registry
 * file, which the host-side reconciler picks up. See ../../../../README.md.
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import { requireAdmin, authzResponse } from "@/lib/authz";

const REGISTRY_PATH = path.join(process.cwd(), "registry", "mcp-servers.yaml");

export async function GET() {
  try {
    // Read-only: session groups are good enough, no provider round-trip.
    await requireAdmin({ revalidate: false });
    const raw = await readFile(REGISTRY_PATH, "utf8");
    return Response.json({ registry: raw });
  } catch (err) {
    return authzResponse(err);
  }
}

export async function PUT(req: Request) {
  try {
    // Mutating: re-validate against Pocket ID so revoked admins are locked out
    // immediately rather than at session expiry.
    const principal = await requireAdmin();

    const body = await req.json();
    if (typeof body?.registry !== "string") {
      return Response.json({ error: "expected { registry: string }" }, { status: 400 });
    }

    // TODO: validate against the same schema the reconciler enforces before
    // writing, so the UI reports errors instead of leaving a file the
    // reconciler will reject. The reconciler validates independently
    // regardless — it must never trust this path.
    // TODO: write via git commit (author = principal.sub) rather than a bare
    // file write, so the audit trail lands in history.
    console.warn(`registry write requested by ${principal.sub} — not yet implemented`);

    return Response.json({ error: "not implemented" }, { status: 501 });
  } catch (err) {
    return authzResponse(err);
  }
}
