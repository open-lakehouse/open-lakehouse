// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { checkCredentials } from "@/lib/auth";
import { SESSION_COOKIE, SESSION_TTL_SECONDS, signSession } from "@/lib/session";

export async function POST(req: NextRequest) {
  let body: { username?: unknown; password?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
  const username = typeof body.username === "string" ? body.username.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!username || !password) {
    return NextResponse.json({ error: "Username and password are required" }, { status: 400 });
  }

  if (!process.env.DASHBOARD_PASSWORD) {
    return NextResponse.json(
      { error: "Login is not configured. Set DASHBOARD_PASSWORD and restart the dashboard." },
      { status: 503 }
    );
  }

  if (!checkCredentials(username, password)) {
    return NextResponse.json({ error: "Incorrect username or password" }, { status: 401 });
  }

  const res = NextResponse.json({ user: username });
  res.cookies.set(SESSION_COOKIE, await signSession(username), {
    httpOnly: true,
    sameSite: "lax",
    // The dashboard is served over plain HTTP on loopback; Secure would drop it.
    secure: false,
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  });
  return res;
}
