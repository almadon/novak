/**
 * Scaffolding. The per-user surfaces (persona, memories, attached tools) go
 * here — each one a view over an existing service, keyed by principal.sub.
 */
import { requireUser, ADMIN_GROUP } from "@/lib/authz";

export default async function Home() {
  const principal = await requireUser();
  const isAdmin = principal.groups.includes(ADMIN_GROUP);

  return (
    <main>
      <h1>Novak Console</h1>
      <p>
        Signed in as {principal.name ?? principal.email ?? principal.sub}
        {isAdmin ? " (admin)" : ""}
      </p>
      <ul>
        <li>Persona — not yet built</li>
        <li>Memories — not yet built (Mem0 REST, scoped to this sub)</li>
        <li>Attached tools — not yet built</li>
        {isAdmin && <li><a href="/admin">Admin: MCP catalog</a></li>}
      </ul>
    </main>
  );
}
