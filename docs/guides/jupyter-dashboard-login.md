# Open Jupyter from the dashboard

The dashboard can open the configured running Jupyter server and sign the browser
in using Jupyter's normal signed session cookie. The token stays on the server;
it is not placed in links, browser URLs or client-side configuration.

Enable the local handoff in `.env`:

```dotenv
DASHBOARD_ALLOW_JUPYTER_LAUNCH=true
```

Keep the same nonempty `JUPYTER_TOKEN` configured for both notebook and dashboard
containers, then start/recreate those two services:

```bash
./lakehouse start notebooks
docker compose -f docker-compose-dashboard.yml up -d --build dashboard
```

Click **Jupyter Notebook** under Quick Access, or the Jupyter action in Getting
Started. Notebook-specific buttons open the selected notebook. If the server is
stopped or the token is missing/out of sync, a page explains what needs attention
and offers a retry and a normal sign-in link.

The dashboard checks its configured `JUPYTER_URL` (default `http://jupyter:8889`);
it does not scan other servers, read Docker sockets, scrape logs or start services
automatically. A randomly minted Jupyter token must first be configured explicitly
in the dashboard. This flow supports the stack's root-path server published on
port 8889, with the dashboard and Jupyter opened on the same loopback hostname.

Automatic sign-in is off by default. It is also available when the existing
`DASHBOARD_ALLOW_CODE_EXECUTION=true` setting is explicitly enabled. The separate
launch setting does not enable dashboard notebook execution or pipeline writes.
Keep the dashboard on its default loopback binding: it has no independent user
authentication. Launch requires a POST from the same local origin and preserves
Jupyter's authentication and XSRF checks.

The session request uses native Node HTTP with the browser's public Host header;
Node fetch replaces this header with the internal hostname. Jupyter includes
that hostname and port in its signed cookie name, so preserving it is required.

Validate with:

```bash
cd dashboard && npm test && npx tsc --noEmit --incremental false
cd ..
LAKEHOUSE_TEST_JUPYTER_LAUNCH=1 poetry run pytest tests/integration/test_jupyter_browser_launch.py -s
```

The opt-in integration test uses a temporary token and notebook, requires port
8889 to be free, and removes only its own containers/network. It checks real
cookie authentication, notebook navigation, cross-origin rejection and stopped
server handling without mounting existing data.
