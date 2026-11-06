// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextResponse } from "next/server";
import { defaultBucket, listBuckets } from "@/lib/s3";

/** Read-only: buckets in the object store (SeaweedFS). */
export async function GET() {
  try {
    const buckets = await listBuckets();
    return NextResponse.json({ buckets, defaultBucket: defaultBucket() });
  } catch (err) {
    return NextResponse.json(
      { error: "Object store unreachable", detail: (err as Error).message },
      { status: 502 }
    );
  }
}
