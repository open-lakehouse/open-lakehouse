// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { getObjectDetail, isValidBucketName } from "@/lib/s3";

/** Read-only: object metadata plus a bounded text preview for text-like files. */
export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams;
  const bucket = q.get("bucket") ?? "";
  const key = q.get("key") ?? "";

  if (!isValidBucketName(bucket)) {
    return NextResponse.json({ error: "Invalid bucket name" }, { status: 400 });
  }
  if (!key || key.endsWith("/") || key.length > 1024) {
    return NextResponse.json({ error: "Invalid object key" }, { status: 400 });
  }

  try {
    return NextResponse.json(await getObjectDetail(bucket, key));
  } catch (err) {
    const name = (err as { name?: string }).name;
    if (name === "NotFound" || name === "NoSuchKey" || name === "NoSuchBucket") {
      return NextResponse.json({ error: "Object not found" }, { status: 404 });
    }
    return NextResponse.json(
      { error: "Object store unreachable", detail: (err as Error).message },
      { status: 502 }
    );
  }
}
