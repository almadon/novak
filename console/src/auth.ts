/**
 * Pocket ID OIDC. The `groups` scope is required — it carries the claim that
 * gates admin access (see lib/authz.ts).
 *
 * Session lifetime is deliberately short. Group membership is re-validated
 * against the provider for mutating admin actions, but a short session limits
 * the blast radius of everything else.
 */
import NextAuth from "next-auth";

const issuer = process.env.OIDC_ISSUER!;

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    {
      id: "pocketid",
      name: "Pocket ID",
      type: "oidc",
      issuer,
      clientId: process.env.OIDC_CLIENT_ID!,
      clientSecret: process.env.OIDC_CLIENT_SECRET!,
      authorization: { params: { scope: "openid profile email groups" } },
      checks: ["pkce", "state"],
    },
  ],
  session: { strategy: "jwt", maxAge: 60 * 60 * 8 },
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account) {
        token.accessToken = account.access_token;
      }
      if (profile) {
        token.sub = profile.sub ?? token.sub;
        const groups = (profile as Record<string, unknown>).groups;
        token.groups = Array.isArray(groups)
          ? groups.filter((g): g is string => typeof g === "string")
          : [];
      }
      return token;
    },
    async session({ session, token }) {
      session.user.sub = token.sub as string;
      // Convenience only — never the basis for an admin decision. Admin routes
      // re-validate against the provider. See lib/authz.ts.
      session.user.groups = (token.groups as string[]) ?? [];
      session.accessToken = token.accessToken as string | undefined;
      return session;
    },
  },
});
