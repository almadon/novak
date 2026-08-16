import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    user: {
      /** Pocket ID subject — primary key for per-user state (incl. Mem0 user_id). */
      sub: string;
      /** Convenience copy of the claim. Never the basis for an admin decision. */
      groups: string[];
    } & DefaultSession["user"];
  }
}
