import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";

export function createJupyterSession(
  url: URL,
  headers: Record<string, string>,
): Promise<{ status: number; cookies: string[] }> {
  return new Promise((resolve, reject) => {
    // Native HTTP preserves Host. Node fetch replaces it with the internal DNS
    // name, which makes Jupyter sign an unusable browser cookie.
    const request = url.protocol === "https:" ? httpsRequest : httpRequest;
    const connection = request(
      url,
      { method: "GET", headers, signal: AbortSignal.timeout(5000) },
      (response) => {
        response.resume();
        resolve({
          status: response.statusCode || 502,
          cookies: response.headers["set-cookie"] || [],
        });
      },
    );
    connection.on("error", reject);
    connection.end();
  });
}
