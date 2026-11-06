/**
 * Data lake routes: input validation and S3 error mapping (S3 client mocked).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest } from "next/server";

const send = vi.fn();
vi.mock("@aws-sdk/client-s3", async (orig) => {
  const actual = await orig<typeof import("@aws-sdk/client-s3")>();
  return {
    ...actual,
    S3Client: vi.fn().mockImplementation(() => ({ send })),
  };
});

process.env.AWS_ACCESS_KEY_ID = "k";
process.env.AWS_SECRET_ACCESS_KEY = "s";

function req(path: string) {
  return new NextRequest(`http://localhost:3000${path}`);
}

describe("data lake API", () => {
  beforeEach(() => send.mockReset());

  it("lists one folder level with folders and files", async () => {
    send.mockResolvedValueOnce({
      CommonPrefixes: [{ Prefix: "warehouse/sales/_delta_log/" }],
      Contents: [
        { Key: "warehouse/sales/", Size: 0 },
        { Key: "warehouse/sales/part-0.parquet", Size: 42, LastModified: new Date("2026-01-01T00:00:00Z") },
      ],
      IsTruncated: false,
    });
    const { GET } = await import("@/app/api/datalake/objects/route");
    const res = await GET(req("/api/datalake/objects?bucket=lakehouse&prefix=warehouse/sales/"));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.folders).toEqual([{ prefix: "warehouse/sales/_delta_log/", name: "_delta_log" }]);
    expect(body.objects).toHaveLength(1);
    expect(body.objects[0]).toMatchObject({ name: "part-0.parquet", size: 42 });
  });

  it("rejects an invalid bucket name", async () => {
    const { GET } = await import("@/app/api/datalake/objects/route");
    const res = await GET(req("/api/datalake/objects?bucket=../etc"));
    expect(res.status).toBe(400);
    expect(send).not.toHaveBeenCalled();
  });

  it("rejects a prefix that is not a folder", async () => {
    const { GET } = await import("@/app/api/datalake/objects/route");
    const res = await GET(req("/api/datalake/objects?bucket=lakehouse&prefix=warehouse"));
    expect(res.status).toBe(400);
  });

  it("maps NoSuchBucket to 404", async () => {
    send.mockRejectedValueOnce(Object.assign(new Error("x"), { name: "NoSuchBucket" }));
    const { GET } = await import("@/app/api/datalake/objects/route");
    const res = await GET(req("/api/datalake/objects?bucket=missing"));
    expect(res.status).toBe(404);
  });

  it("previews text objects", async () => {
    send
      .mockResolvedValueOnce({ ContentLength: 11, ContentType: "application/json" })
      .mockResolvedValueOnce({ Body: { transformToString: async () => '{"a": 1}' } });
    const { GET } = await import("@/app/api/datalake/object/route");
    const res = await GET(req("/api/datalake/object?bucket=lakehouse&key=t/_delta_log/0.json"));
    const body = await res.json();
    expect(body.preview).toBe('{"a": 1}');
    expect(body.previewTruncated).toBe(false);
  });

  it("does not download binary objects", async () => {
    send.mockResolvedValueOnce({ ContentLength: 5_000_000, ContentType: "application/octet-stream" });
    const { GET } = await import("@/app/api/datalake/object/route");
    const res = await GET(req("/api/datalake/object?bucket=lakehouse&key=t/part-0.parquet"));
    const body = await res.json();
    expect(body.preview).toBeNull();
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("maps a missing object to 404", async () => {
    send.mockRejectedValueOnce(Object.assign(new Error("x"), { name: "NotFound" }));
    const { GET } = await import("@/app/api/datalake/object/route");
    const res = await GET(req("/api/datalake/object?bucket=lakehouse&key=nope.json"));
    expect(res.status).toBe(404);
  });
});
