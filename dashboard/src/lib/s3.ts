// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Containerized Lakehouse Platform Contributors

import {
  S3Client,
  GetObjectCommand,
  PutObjectCommand,
  HeadBucketCommand,
  HeadObjectCommand,
  ListBucketsCommand,
  ListObjectsV2Command,
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

// --- Data lake browser (read-only) ---

export interface LakeBucket {
  name: string;
  createdAt: string | null;
}

export interface LakeFolder {
  prefix: string;
  name: string;
}

export interface LakeObject {
  key: string;
  name: string;
  size: number;
  lastModified: string | null;
}

export interface LakeListing {
  bucket: string;
  prefix: string;
  folders: LakeFolder[];
  objects: LakeObject[];
  nextToken: string | null;
  truncated: boolean;
}

export interface LakeObjectDetail {
  bucket: string;
  key: string;
  size: number;
  contentType: string | null;
  lastModified: string | null;
  etag: string | null;
  /** Text preview (first PREVIEW_BYTES), only for text-like objects. */
  preview: string | null;
  previewTruncated: boolean;
}

export const PREVIEW_BYTES = 64 * 1024;

/** S3 bucket naming rules (lowercase, digits, dots, hyphens; 3-63 chars). */
export function isValidBucketName(name: string): boolean {
  return /^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$/.test(name);
}

export function defaultBucket(): string {
  return BUCKET;
}

export async function listBuckets(): Promise<LakeBucket[]> {
  const res = await client().send(new ListBucketsCommand({}));
  return (res.Buckets ?? [])
    .filter((b) => !!b.Name)
    .map((b) => ({
      name: b.Name as string,
      createdAt: b.CreationDate ? b.CreationDate.toISOString() : null,
    }));
}

function lastSegment(path: string): string {
  const trimmed = path.endsWith("/") ? path.slice(0, -1) : path;
  return trimmed.slice(trimmed.lastIndexOf("/") + 1);
}

export async function listObjects(
  bucket: string,
  prefix: string,
  continuationToken?: string,
  maxKeys = 500
): Promise<LakeListing> {
  const res = await client().send(
    new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: prefix || undefined,
      Delimiter: "/",
      MaxKeys: maxKeys,
      ContinuationToken: continuationToken || undefined,
    })
  );
  const folders = (res.CommonPrefixes ?? [])
    .map((p) => p.Prefix)
    .filter((p): p is string => !!p)
    .map((p) => ({ prefix: p, name: lastSegment(p) }));
  const objects = (res.Contents ?? [])
    .filter((o) => !!o.Key && o.Key !== prefix)
    .map((o) => ({
      key: o.Key as string,
      name: lastSegment(o.Key as string),
      size: o.Size ?? 0,
      lastModified: o.LastModified ? o.LastModified.toISOString() : null,
    }));
  return {
    bucket,
    prefix,
    folders,
    objects,
    nextToken: res.NextContinuationToken ?? null,
    truncated: !!res.IsTruncated,
  };
}

const TEXT_EXTENSIONS = new Set([
  "json", "crc", "txt", "csv", "tsv", "log", "md", "yaml", "yml", "xml",
  "properties", "conf", "sql", "py", "sh", "avsc", "ndjson", "jsonl",
]);

/** Whether an object is worth previewing as text (by content type or extension). */
export function isTextLike(key: string, contentType: string | null | undefined): boolean {
  if (contentType && /^(text\/|application\/(json|xml|x-ndjson|yaml))/.test(contentType)) {
    return true;
  }
  const name = lastSegment(key);
  const dot = name.lastIndexOf(".");
  if (dot < 0) return false;
  return TEXT_EXTENSIONS.has(name.slice(dot + 1).toLowerCase());
}

export async function getObjectDetail(bucket: string, key: string): Promise<LakeObjectDetail> {
  const head = await client().send(new HeadObjectCommand({ Bucket: bucket, Key: key }));
  const size = head.ContentLength ?? 0;
  const contentType = head.ContentType ?? null;
  let preview: string | null = null;
  if (size > 0 && isTextLike(key, contentType)) {
    const res = await client().send(
      new GetObjectCommand({ Bucket: bucket, Key: key, Range: `bytes=0-${PREVIEW_BYTES - 1}` })
    );
    preview = (await res.Body?.transformToString("utf-8")) ?? null;
  }
  return {
    bucket,
    key,
    size,
    contentType,
    lastModified: head.LastModified ? head.LastModified.toISOString() : null,
    etag: head.ETag ?? null,
    preview,
    previewTruncated: preview !== null && size > PREVIEW_BYTES,
  };
}
