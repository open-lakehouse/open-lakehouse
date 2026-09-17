import { describe, it, expect } from "vitest";
import { sanitizeHtml } from "@/lib/sanitize";

describe("sanitizeHtml", () => {
  it("strips script tags", () => {
    const input = '<p>Hello</p><script>alert("xss")</script>';
    expect(sanitizeHtml(input)).not.toContain("<script");
    expect(sanitizeHtml(input)).toContain("<p>Hello</p>");
  });

  it("strips event handlers", () => {
    const input = '<img src="x" onerror="alert(1)">';
    const result = sanitizeHtml(input);
    expect(result).not.toContain("onerror");
  });

  it("strips javascript: URLs", () => {
    const input = '<a href="javascript:alert(1)">click</a>';
    expect(sanitizeHtml(input)).not.toContain("javascript:");
  });

  it("preserves safe HTML", () => {
    const input = '<p>Hello <strong>world</strong></p>';
    expect(sanitizeHtml(input)).toBe(input);
  });

  it("preserves data:image URLs", () => {
    const input = '<img src="data:image/png;base64,abc123">';
    expect(sanitizeHtml(input)).toContain("data:image/png");
  });

  it("strips data:text/html in a navigational (href) context, any quoting", () => {
    // An <img src=data:...> is non-scriptable in browsers (DOMPurify keeps it);
    // the real vector is a navigable href, which must be neutralized.
    expect(
      sanitizeHtml('<a href="data:text/html,<script>alert(1)</script>">x</a>')
    ).not.toContain("data:text/html");
    expect(sanitizeHtml("<a href='data:text/html;base64,abc'>x</a>")).not.toContain(
      "data:text/html"
    );
    expect(sanitizeHtml("<a href=data:text/html,x>y</a>")).not.toContain("data:text/html");
  });

  it("strips single-quoted and unquoted javascript: URLs", () => {
    expect(sanitizeHtml("<a href='javascript:alert(1)'>x</a>")).not.toContain(
      "javascript:"
    );
    expect(sanitizeHtml("<img src=javascript:alert(1)>")).not.toContain("javascript:");
  });

  it("strips iframe tags", () => {
    const input = '<iframe src="http://evil.com"></iframe>';
    expect(sanitizeHtml(input)).not.toContain("iframe");
  });

  // Classes a regex sanitizer misses but a DOM-based one closes:
  it("strips unclosed / malformed script tags", () => {
    expect(sanitizeHtml("<p>ok</p><script>alert(1)")).not.toContain("alert(1)");
    expect(sanitizeHtml("<p>ok</p><script>alert(1)")).toContain("<p>ok</p>");
  });

  it("strips leading-whitespace javascript: URLs", () => {
    expect(sanitizeHtml('<a href=" javascript:alert(1)">x</a>')).not.toContain(
      "javascript:"
    );
  });

  it("strips HTML-entity-encoded javascript: URLs", () => {
    const out = sanitizeHtml('<a href="&#106;avascript:alert(1)">x</a>').toLowerCase();
    expect(out).not.toContain("javascript:");
    expect(out).not.toContain("avascript");
  });
});
