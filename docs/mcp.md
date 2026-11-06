# Connect an MCP application

MCP lets an AI assistant read and modify your OpenDiving content with permissions you choose.
The server runs inside the API. No extra service or public port is required.

Set `MCP_ENABLED=true` in `.env`, then recreate the API and worker containers with
`docker compose up -d api worker`. Set `FRONTEND_URL` to the HTTPS origin you use in your browser.
Local development may use HTTP on localhost. Other HTTP origins are refused when MCP starts.

Add `https://your-domain/api/v1/mcp` as a Streamable HTTP server in your client. The client
registers as a public OAuth application, opens OpenDiving sign-in, and asks you to approve
permissions. Read permissions are selected initially. Writing and deleting are separate choices.
Profile and preferences are optional, separate permissions. Check-in link sharing has its own
permission. Ordinary content permissions cannot manage credentials, change your sign-in email,
delete your account or administer the instance.

Revoke access in **Settings > Authentication > Connected applications**. Revocation takes effect
on the app's next request. Access tokens last 15 minutes. Refresh tokens rotate on use and expire
after 30 days. Reusing a spent refresh token revokes the connection.

## Proxy configuration

The bundled Caddy routes MCP and OAuth discovery directly to the API. With the Next.js proxy,
use the updated web image, which includes both discovery routes. A custom reverse proxy must
forward these paths without buffering event streams:

- `/api/v1/mcp` and its children
- `/.well-known/oauth-protected-resource/api/v1/mcp`
- `/.well-known/oauth-authorization-server/api/v1/mcp/oauth`

`MCP_ALLOWED_HOSTS` names additional exact Host headers from internal proxy hops. The public
hostname from `FRONTEND_URL` is always allowed. If a browser-based MCP client sends an Origin,
add its exact origin to `MCP_ALLOWED_ORIGINS`. Native clients normally omit Origin.

## Files and imports

Upload a file with `POST /api/v1/mcp/files`, using the connection's bearer token and a multipart
`file` part. Give the resulting handle to an upload tool. Each file is at most 10 MiB. Handles
expire after one hour and each account may hold 50 MiB of temporary files. They are private to
the app that created them. Delete unused handles with `DELETE /api/v1/mcp/files/{handle}`.

Import tools retain the preview and apply workflow. Apply takes the same staged files and the
preview token. Export and attachment tools return a private download handle. Fetch its URL with
the same MCP bearer token. Download URLs do not contain credentials.

The server uses the official Python SDK and supports MCP 2026-07-28 with its 2025-11-25
compatibility transport. OAuth uses authorization codes with PKCE S256 and resource indicators.
Clients must send `resource=https://your-domain/api/v1/mcp` on authorization and token requests.
HTTPS client ID metadata documents are supported. Fetches use public DNS addresses pinned through
the connection, verify TLS for the original hostname, reject redirects and cap responses at 32 KiB.
Public client registration is also available for compatibility.
