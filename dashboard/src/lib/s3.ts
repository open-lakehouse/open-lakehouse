// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import {
  S3Client,
  GetObjectCommand,
  PutObjectCommand,
  HeadBucketCommand,
} from "@aws-sdk/client-s3";
import { requireEnv } from "./env";

const BUCKET = process.env.S3_BUCKET || "lakehouse";
const HISTORY_KEY = "pipeline-history/runs.json";

let _client: S3Client | null = null;

function client(): S3Client {
  if (!_client) {
    _client = new S3Client({
      region: process.env.AWS_REGION || "us-east-1",
      endpoint: process.env.S3_ENDPOINT || "http://seaweedfs:8333",
      forcePathStyle: true,
      credentials: {
        accessKeyId: requireEnv("AWS_ACCESS_KEY_ID"),
        secretAccessKey: requireEnv("AWS_SECRET_ACCESS_KEY"),
      },
    });
  }
  return _client;
}

/**
 * Liveness probe for the object store: HEAD the lakehouse bucket. Returns true
 * only when the S3 endpoint answers and the bucket exists. Used by
 * /api/health/storage (SeaweedFS has no MinIO-style /minio/health/live path).
 */
export async function storageReachable(): Promise<boolean> {
  try {
    await client().send(new HeadBucketCommand({ Bucket: BUCKET }));
    return true;
  } catch {
    return false;
  }
}

export interface RunHistoryEntry {
  id: string;
  timestamp: string;
  spec: string;
  mode: "run" | "dry-run";
  exitCode: number | null;
  message: string | null;
  output: string;
  durationMs: number | null;
}

const MAX_HISTORY = 100;

export async function getRunHistory(): Promise<RunHistoryEntry[]> {
  try {
    const res = await client().send(
      new GetObjectCommand({ Bucket: BUCKET, Key: HISTORY_KEY })
    );
    const body = await res.Body?.transformToString();
    if (!body) return [];
    const parsed = JSON.parse(body);
    return Array.isArray(parsed) ? (parsed as RunHistoryEntry[]) : [];
  } catch (err: unknown) {
    const code = (err as { name?: string }).name;
    if (code === "NoSuchKey" || code === "NoSuchBucket") return [];
    console.error("Failed to read run history from the object store:", err);
    return [];
  }
}

export async function saveRunHistory(entries: RunHistoryEntry[]): Promise<void> {
  const trimmed = entries.slice(0, MAX_HISTORY);
  await client().send(
    new PutObjectCommand({
      Bucket: BUCKET,
      Key: HISTORY_KEY,
      Body: JSON.stringify(trimmed, null, 2),
      ContentType: "application/json",
    })
  );
}

export async function appendRun(entry: RunHistoryEntry): Promise<RunHistoryEntry[]> {
  const existing = await getRunHistory();
  const updated = [entry, ...existing].slice(0, MAX_HISTORY);
  await saveRunHistory(updated);
  return updated;
}

export async function deleteRun(id: string): Promise<RunHistoryEntry[]> {
  const existing = await getRunHistory();
  const updated = existing.filter((e) => e.id !== id);
  await saveRunHistory(updated);
  return updated;
}

export async function clearRunHistory(): Promise<void> {
  await saveRunHistory([]);
}
