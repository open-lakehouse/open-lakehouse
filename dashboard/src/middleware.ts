// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

/**
 * Authentication gate for the whole platform UI.
 *  - "/" is the login page (public). A signed-in user is sent on to /home.
 *  - /api/auth/login is public; every other /api route answers 401 without a session.
 *  - Every other page redirects to the login page, remembering where it was headed.
 */
const PUBLIC_API = new Set(["/api/auth/login", "/api/auth/session"]);

export async function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  const session = await verifySession(req.cookies.get(SESSION_COOKIE)?.value);

  if (pathname === "/") {
    if (session) return NextResponse.redirect(new URL("/home", req.url));
    return NextResponse.next();
  }

  if (PUBLIC_API.has(pathname) || session) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  const login = new URL("/", req.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Node runtime: shares process.env with instrumentation.ts (the session secret).
  runtime: "nodejs",
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
