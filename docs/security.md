# Security

| Threat | Protection |
|---|---|
| Cross-site request forgery | Every cookie-authenticated POST is CSRF-protected. Native clients use a signed header token, which browsers cannot send cross-site. |
| Guest impersonation | Guest ids live in a **signed**, HttpOnly, `SameSite=Lax` cookie (`Secure` when `SESSION_COOKIE_SECURE`). Tampered or expired tokens are ignored. |
| Reading other people's chats | Every endpoint, stream and attachment checks conversation ownership. Unknown and foreign ids return the same error. |
| Leaking internal notes | Events are audience-scoped. Notes, tags, assignments and AI hand-offs are delivered only to staff streams, and are excluded from visitor message lists and transcripts. Visitors cannot reply to or react on notes. |
| XSS | Messages are stripped of HTML and control characters server-side, and both UIs render text with `textContent`. Links are created as `rel="noopener noreferrer nofollow"` anchors. |
| Malicious uploads | Extension allowlist, size cap, magic-byte check (PNG/JPEG/GIF/WebP/PDF/ZIP/Office, and text without NUL bytes). SVG, HTML, JS and executables are always refused. Stored names are random. Files are served through an access-checked view with `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'; sandbox`. Only raster images are inline. |
| Spam & abuse | Per-user or per-IP rate limits for messages, uploads, typing, reactions, profile and transcripts. A blocked-word list, open conversations per IP, and messages per conversation are also capped. Operators can block a guest (guest id plus a salted IP hash) or a logged-in account (the account only). Raw IPs are never stored. |
| Transcript email as a spam relay | Transcripts go only to the email attached to the conversation, and a guest cannot change it once set. Sending is rate limited per visitor (`TRANSCRIPT_RATE_LIMIT`). Each new conversation also counts against `MAX_OPEN_PER_IP`. |
| SSRF via webhooks | Only `http(s)`. Private, loopback and link-local targets are refused by default. Redirects are not followed. |
| Spoofed client IPs | `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS = True`. Behind a reverse proxy you **must** enable it; see [realtime.md](realtime.md#reverse-proxies). |
| Secrets | AI keys are read from settings only and never reach the page or the logs. |
| Data retention | `supchat_cleanup` auto-closes idle chats and deletes old closed conversations, including their files. |

## Recommendations

- Serve over HTTPS and set `SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True`.
- Do not serve `MEDIA_ROOT/supchat/` directly from your web server. Let the attachment view do the access checks.
- Use a shared cache (Redis or Memcached) in production so rate limits hold across workers.
- Mention chat storage and any AI provider in your privacy policy, and set `RETENTION_DAYS`.

Please report vulnerabilities privately (see the README contact). Do not open public issues for them.
