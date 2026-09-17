// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";
import { storageReachable } from "@/lib/s3";

// SeaweedFS's S3 gateway has no MinIO-style /minio/health/live path, so probe
// liveness by HEAD-ing the lakehouse bucket through the S3 client instead.
export async function GET() {
  try {
    const ok = await storageReachable();
    return NextResponse.json(
      { status: ok ? "healthy" : "unhealthy" },
      { status: ok ? 200 : 503 }
    );
  } catch {
    return NextResponse.json({ status: "unknown" }, { status: 503 });
  }
}
