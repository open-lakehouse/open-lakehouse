// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import { NextRequest, NextResponse } from "next/server";
import { isValidBucketName, listObjects } from "@/lib/s3";

/** Read-only: one "directory" level of a bucket (delimiter "/"). */
export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams;
  const bucket = q.get("bucket") ?? "";
  const prefix = q.get("prefix") ?? "";
  const token = q.get("token") ?? undefined;

  if (!isValidBucketName(bucket)) {
    return NextResponse.json({ error: "Invalid bucket name" }, { status: 400 });
  }
  if (prefix && !prefix.endsWith("/")) {
    return NextResponse.json({ error: "Prefix must end with '/'" }, { status: 400 });
  }

  try {
    return NextResponse.json(await listObjects(bucket, prefix, token));
  } catch (err) {
    const name = (err as { name?: string }).name;
    if (name === "NoSuchBucket") {
      return NextResponse.json({ error: `Bucket '${bucket}' does not exist` }, { status: 404 });
    }
    return NextResponse.json(
      { error: "Object store unreachable", detail: (err as Error).message },
      { status: 502 }
    );
  }
}
