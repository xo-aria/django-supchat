# Changelog

## 2.0.0

### Added
- Redesigned operator workspace (single-page app with real URLs):
  - routes for every chat, analytics and each settings tab, with Back/Forward and deep links
  - cursor-based pagination with infinite scroll, stable while new messages arrive
  - theme-aware custom select, tabbed settings, consistent spacing
  - five panes: rail, inbox, conversations, chat, details; live updates, filters, search
  - internal notes, quick replies (`/shortcut`), tags, priority, assignment
  - visitor blocking, transcripts, SVG analytics, desktop notifications, keyboard shortcuts
  - fixed language and theme buttons
- Widget:
  - replies, reactions, emoji picker, attachments with lightbox
  - quick replies, pre-chat form, rating, transcripts
  - skeleton loading, WebAudio message sounds, fixed language button, light/dark/auto theme
- AI auto-replies:
  - OpenAI-compatible APIs, Anthropic, or a custom callable
  - human handoff and loop prevention
- Webhooks: Slack, Discord, and generic JSON signed with HMAC, with an SSRF guard.
- Eight UI languages: en, fa, ar, tr, es, de, fr, ru.
- Header-token authentication and documented REST/SSE API for native clients.
- Optional WebSocket transport (`supchat.contrib.channels`, `pip install django-supchat[channels]`).
- `supchat_cleanup` management command (auto-close and retention).
- New settings, models (`Reaction`, `Tag`, `CannedResponse`, `WebhookEndpoint`, `BlockedVisitor`) and migration `0002_features`.
- A test suite with 230+ tests and CI.

### Changed
- CSRF is enforced on the visitor API. It was previously exempt.
- The visitor message list returns the latest page, with `has_more` and `?before=`.
- The operator API returns JSON `401`/`403` instead of redirects.
- SSE events are audience-scoped, and operators use a single staff stream.
- `X-Forwarded-For` is ignored unless `TRUST_PROXY_HEADERS` is set.
- Visitors can now send typing indicators. That endpoint was previously staff-only.
- Higher-contrast colors in both themes.

### Removed
- The Chart.js CDN dependency in the operator panel.
