/**
 * Admin surface. Scaffolding — but note the gate is real: requireAdmin() throws
 * for non-admins, and the API routes this page will call gate independently.
 */
import { requireAdmin, AuthzError } from "@/lib/authz";

export default async function AdminPage() {
  try {
    await requireAdmin({ revalidate: false });
  } catch (err) {
    if (err instanceof AuthzError) {
      return (
        <main>
          <h1>Not authorized</h1>
          <p>This area requires the <code>admins.novak</code> group.</p>
        </main>
      );
    }
    throw err;
  }

  return (
    <main>
      <h1>MCP catalog</h1>
      <p>
        Edits here write <code>registry/mcp-servers.yaml</code>. The host-side
        reconciler applies it — this console has no Docker access by design.
      </p>
      <p>Catalog table and edit form — not yet built.</p>
    </main>
  );
}
