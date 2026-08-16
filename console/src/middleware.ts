/**
 * Defence in depth only. Real authorization lives in the route handlers via
 * requireAdmin() — see lib/authz.ts. This just keeps unauthenticated browsers
 * off console pages so they get a sign-in redirect instead of an empty shell.
 */
import { auth } from "@/auth";

export default auth((req) => {
  if (!req.auth) {
    const signIn = new URL("/api/auth/signin", req.nextUrl.origin);
    signIn.searchParams.set("callbackUrl", req.nextUrl.pathname);
    return Response.redirect(signIn);
  }
});

export const config = {
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
};
