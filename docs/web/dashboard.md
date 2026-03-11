---
summary: "Gateway dashboard (Control UI) access and auth"
read_when:
  - Changing dashboard authentication or exposure modes
title: "Dashboard"
---

# Dashboard (Control UI)

The Gateway dashboard is the browser Control UI served at `/` by default
(override with `gateway.controlUi.basePath`).

Quick open (local Gateway):

- [http://127.0.0.1:18789/](http://127.0.0.1:18789/) (or [http://localhost:18789/](http://localhost:18789/))

Key references:

- [Control UI](/web/control-ui) for usage and UI capabilities.
- [Tailscale](/gateway/tailscale) for Serve/Funnel automation.
- [Web surfaces](/web) for bind modes and security notes.

Authentication is enforced at the WebSocket handshake via `connect.params.auth`
(token or password). See `gateway.auth` in [Gateway configuration](/gateway/configuration).

Security note: the Control UI is an **admin surface** (chat, config, exec approvals).
Do not expose it publicly. The UI keeps dashboard URL tokens in memory for the current tab
and strips them from the URL after load.
Prefer localhost, Tailscale Serve, or an SSH tunnel.

## Fast path (recommended)

- After onboarding, the CLI auto-opens the dashboard and prints a clean (non-tokenized) link.
- Re-open anytime: `openclaw dashboard` (copies link, opens browser if possible, shows SSH hint if headless).
- If the UI prompts for auth, paste the token from `gateway.auth.token` (or `OPENCLAW_GATEWAY_TOKEN`) into Control UI settings.

## Token basics (local vs remote)

- **Localhost**: open `http://127.0.0.1:18789/`.
- **Token source**: `gateway.auth.token` (or `OPENCLAW_GATEWAY_TOKEN`); `openclaw dashboard` can pass it via URL fragment for one-time bootstrap, but the Control UI does not persist gateway tokens in localStorage.
- If `gateway.auth.token` is SecretRef-managed, `openclaw dashboard` prints/copies/opens a non-tokenized URL by design. This avoids exposing externally managed tokens in shell logs, clipboard history, or browser-launch arguments.
- If `gateway.auth.token` is configured as a SecretRef and is unresolved in your current shell, `openclaw dashboard` still prints a non-tokenized URL plus actionable auth setup guidance.
- **Not localhost**: use Tailscale Serve (tokenless for Control UI/WebSocket if `gateway.auth.allowTailscale: true`, assumes trusted gateway host; HTTP APIs still need token/password), tailnet bind with a token, or an SSH tunnel. See [Web surfaces](/web).

## If you see “unauthorized” / 1008 / HTTP 401

- Ensure the gateway is reachable (local: `openclaw status`; remote: SSH tunnel `ssh -N -L 18789:127.0.0.1:18789 user@host` then open `http://127.0.0.1:18789/`).
- **Recommended:** run `openclaw dashboard --no-open` and open the **full** URL it prints (including `#token=...`) in the browser. If you open the base URL without the token, you get 401 unless you paste the token in Control UI settings and click Connect.
- If the CLI says "Token auto-auth unavailable": set a token with `openclaw config set gateway.auth.token "..."` (or export `OPENCLAW_GATEWAY_TOKEN`), **restart the gateway**, then run `openclaw dashboard --no-open` again.
- No token configured: `openclaw doctor --generate-gateway-token`, then set it in config and restart the gateway.
- See [Troubleshooting: HTTP 401](/gateway/troubleshooting#http-401-invalid-access-token-or-token-expired-control-ui) for a full checklist.
