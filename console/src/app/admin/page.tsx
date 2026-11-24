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
          <h1>Admins only</h1>
          <p>This page is for Novak admins. Ask whoever runs Novak if you need access.</p>
        </main>
      );
    }
    throw err;
  }

  return (
    <main>
      <h1>Tool catalog</h1>
      <p>
        Changes here are saved to <code>registry/mcp-servers.yaml</code> and applied on the
        server by a separate step, because the console is not allowed to touch Docker.
      </p>
      <p>The catalog table and edit form are not built yet. For now, edit that file by hand.</p>
    </main>
  );
}
