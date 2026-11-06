// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE, verifySession } from "@/lib/session";

/** Who is signed in (or null). Public, so the login page can probe it. */
export async function GET(req: NextRequest) {
  const session = await verifySession(req.cookies.get(SESSION_COOKIE)?.value);
  return NextResponse.json({
    user: session?.u ?? null,
    loginConfigured: !!process.env.DASHBOARD_PASSWORD,
  });
}
