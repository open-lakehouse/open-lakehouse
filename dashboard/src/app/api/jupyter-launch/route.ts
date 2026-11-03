import { NextRequest, NextResponse } from "next/server";
import { codeExecutionEnabled } from "@/lib/features";
import { createJupyterSession } from "@/lib/jupyter-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const privateHeaders = {
  "Cache-Control": "no-store",
  "Referrer-Policy": "no-referrer",
};

export async function POST(req: NextRequest) {
  const dashboard = new URL(req.url);
  const host = req.headers.get("host") || dashboard.host;
  // Only a local, same-origin form submission may mint a browser session.
  if (
    !/^(localhost|127\.0\.0\.1|\[::1\])(?::\d+)?$/.test(host) ||
    req.headers.get("origin") !== `${dashboard.protocol}//${host}` ||
    ![null, "same-origin"].includes(req.headers.get("sec-fetch-site"))
  ) {
    return NextResponse.json(
      { error: "Open Jupyter from the local dashboard." },
      { status: 403, headers: privateHeaders },
    );
  }

  let path = "";
  try {
    const form = await req.formData();
    const value = form.get("path");
    if (value !== null && typeof value !== "string") throw new Error();
    path = value || "";
    if (
      path.length > 4096 ||
      path.startsWith("/") ||
      /[\\\x00-\x1f]/.test(path) ||
      path.split("/").some((part) => part === ".." || part === ".")
    )
      throw new Error();
  } catch {
    return NextResponse.json(
      { error: "Invalid notebook path." },
      { status: 400, headers: privateHeaders },
    );
  }

  const errorPage = (reason: string) => {
    const url = new URL("/jupyter", `${dashboard.protocol}//${host}`);
    url.searchParams.set("error", reason);
    if (path) url.searchParams.set("path", path);
    return NextResponse.redirect(url, { status: 303, headers: privateHeaders });
  };
  if (
    process.env.DASHBOARD_ALLOW_JUPYTER_LAUNCH !== "true" &&
    !codeExecutionEnabled()
  ) {
    return errorPage("disabled");
  }
  const token = process.env.JUPYTER_TOKEN;
  if (!token) return errorPage("unconfigured");

  const publicUrl = new URL(`${dashboard.protocol}//${host}`);
  publicUrl.port = "8889";
  publicUrl.pathname = path
    ? `/lab/tree/${path.split("/").map(encodeURIComponent).join("/")}`
    : "/lab";
  const cookieName = `username-${publicUrl.host}`.replace(/[^A-Za-z0-9]/g, "-");
  const existing = req.headers
    .get("cookie")
    ?.split(";")
    .map((cookie) => cookie.trim())
    .find((cookie) => cookie.startsWith(`${cookieName}=`));
  try {
    const upstream = new URL(process.env.JUPYTER_URL || "http://jupyter:8889");
    // An authenticated API GET establishes Jupyter's signed browser cookie.
    // Host must match the browser URL because Jupyter includes it in the name.
    upstream.pathname = `${upstream.pathname.replace(/\/$/, "")}/api/contents`;
    upstream.search = "?content=0";
    const response = await createJupyterSession(upstream, {
      Authorization: `token ${token}`,
      Host: publicUrl.host,
      ...(existing ? { Cookie: existing } : {}),
    });
    if (response.status === 401 || response.status === 403)
      return errorPage("credentials");
    if (response.status < 200 || response.status >= 300)
      return errorPage("unavailable");
    const cookies = response.cookies.filter(
      (cookie) =>
        cookie.startsWith(`${cookieName}=`) &&
        /;\s*httponly(?:;|$)/i.test(cookie) &&
        !/;\s*domain=/i.test(cookie),
    );
    if (!cookies.length && !existing) return errorPage("credentials");
    const result = NextResponse.redirect(publicUrl, {
      status: 303,
      headers: privateHeaders,
    });
    for (const cookie of cookies) {
      // Retain Jupyter's signature and HttpOnly; make the local session host-only.
      result.headers.append(
        "Set-Cookie",
        /;\s*samesite=/i.test(cookie) ? cookie : `${cookie}; SameSite=Lax`,
      );
    }
    return result;
  } catch {
    // Do not serialize upstream URLs, credentials or error objects to the client.
    return errorPage("unavailable");
  }
}
