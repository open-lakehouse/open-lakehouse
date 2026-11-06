import { describe, it, expect } from "vitest";
import { dataLakeHref, parseS3Uri } from "@/lib/api";
import { isTextLike, isValidBucketName } from "@/lib/s3";

describe("storage location helpers", () => {
  it("parses s3 and s3a URIs", () => {
    expect(parseS3Uri("s3://lakehouse/warehouse/t")).toEqual({ bucket: "lakehouse", key: "warehouse/t" });
    expect(parseS3Uri("s3a://lakehouse/x/")).toEqual({ bucket: "lakehouse", key: "x/" });
    expect(parseS3Uri("file:///tmp/x")).toBeNull();
  });

  it("builds a Data Lake link to the table folder", () => {
    expect(dataLakeHref("s3://lakehouse/warehouse/t")).toBe("/datalake?bucket=lakehouse&prefix=warehouse%2Ft%2F");
  });

  it("validates bucket names", () => {
    expect(isValidBucketName("lakehouse")).toBe(true);
    expect(isValidBucketName("Bad_Name")).toBe(false);
    expect(isValidBucketName("..")).toBe(false);
  });

  it("detects text-like objects", () => {
    expect(isTextLike("t/_delta_log/00000.json", null)).toBe(true);
    expect(isTextLike("t/part-0.snappy.parquet", "application/octet-stream")).toBe(false);
    expect(isTextLike("notes", "text/plain")).toBe(true);
  });
});
