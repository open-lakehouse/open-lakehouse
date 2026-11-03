import { createServer } from "node:http";
import { expect, it } from "vitest";
import { createJupyterSession } from "@/lib/jupyter-session";

it("preserves the public Host over a real HTTP connection", async () => {
  const server = createServer((req, res) => {
    expect(req.headers.host).toBe("localhost:8889");
    res.writeHead(200, {
      "Set-Cookie": "username-localhost-8889=signed; HttpOnly; Path=/",
    });
    res.end("{}");
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const address = server.address();
    if (!address || typeof address === "string")
      throw new Error("No test address");
    const result = await createJupyterSession(
      new URL(`http://127.0.0.1:${address.port}/api/contents`),
      { Host: "localhost:8889" },
    );
    expect(result).toEqual({
      status: 200,
      cookies: ["username-localhost-8889=signed; HttpOnly; Path=/"],
    });
  } finally {
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
