# REST, SSE & mobile API

The bundled widget uses the same public API that is documented here, so you can build your own UI or a native app on top of it. All paths are relative to where you include `supchat.urls` (e.g. `/supchat/`).

## Authentication

| Client | Identity | CSRF |
|---|---|---|
| Browser, logged-in user | Django session | `X-CSRFToken` header required |
| Browser, guest | Signed HttpOnly cookie `supchat_guest` (set by `start/`) | `X-CSRFToken` header required |
| Native / mobile app | `X-Supchat-Guest: <token>` header | Not needed (a browser page cannot set this header cross-site) |

### Native / mobile clients

1. `POST start/` with the header `X-Supchat-Client: ios` (any value). The JSON response then includes `guest_token`.
2. Store the token securely (Keychain / Keystore) and send it on every request as `X-Supchat-Guest`.
3. For realtime, open `GET conversations/<id>/events/` with an SSE library that can send custom headers, or use the [WebSocket adapter](realtime.md#websocket-adapter-optional).

Tokens are signed with your `SECRET_KEY` and expire after `GUEST_COOKIE_AGE`.

## Visitor endpoints

| Method & path | Body | Response |
|---|---|---|
| `GET config/` | – | Public widget configuration: title, languages, quick replies, attachments, AI flag, `operators_online`. |
| `POST start/` | `{"locale": "fa"}` (optional) | `{"conversation": {...}}` and, for native clients, `guest_token`. Reuses the open conversation. |
| `GET conversations/<id>/messages/?before=<msg id>` | – | The latest 50 messages, oldest first, plus `has_more`. Internal notes are never included. |
| `POST conversations/<id>/messages/` | JSON `{"text", "reply_to"}`, or multipart with `file` | `201 {"message": {...}}` |
| `POST conversations/<id>/read/` | `{"message_ids": [..]}` (optional) | `{"count": n}` |
| `POST conversations/<id>/typing/` | `{"is_typing": true}` | `{"ok": true}` |
| `POST conversations/<id>/react/` | `{"message_id": 1, "emoji": "👍"}` | Toggles the reaction and returns the summary. |
| `POST conversations/<id>/profile/` | `{"name", "email"}` | Updated conversation. |
| `POST conversations/<id>/close/` | – | Closed conversation. |
| `POST conversations/<id>/rate/` | `{"rating": 1-5, "comment"}` | Once per conversation. |
| `GET conversations/<id>/transcript/` | – | `text/plain` download. |
| `POST conversations/<id>/transcript/email/` | `{"email"}` (only if none is stored yet) | Sent to the conversation's address only. |
| `GET attachments/<message id>/` | – | The file, access-checked. Add `?download=1` to force a download. |
| `GET conversations/<id>/events/` | – | SSE stream (see below). |

Errors look like `{"ok": false, "error": "..."}` with status `400` (validation), `403` (permission or rate limit) or `404`.

### Message object

```json
{
  "id": 42, "conversation": "1b8e...", "sender_type": "guest|user|operator|bot|system",
  "sender_name": "Aria", "text": "Hello", "is_read": false, "is_internal": false,
  "created_at": "2026-11-16T09:40:00+00:00",
  "reply_to": {"id": 41, "text": "...", "sender_type": "guest"},
  "attachment": {"name": "invoice.png", "type": "image/png", "size": 2048, "url": "/supchat/attachments/42/", "is_image": true},
  "reactions": [{"emoji": "🙏", "count": 1, "by": ["visitor"]}]
}
```

## SSE events (visitor stream)

| Event | Data |
|---|---|
| `connected` | `{"conversation"}` |
| `message.created` | message object |
| `message.read` | `{"conversation", "message_ids"}` |
| `reaction.updated` | `{"conversation", "message_id", "reactions"}` |
| `typing.start` / `typing.stop` | `{"conversation", "sender_type"}` |
| `conversation.closed` / `conversation.reopened` | `{"conversation"}` |
| `operator.online` / `operator.offline` | `{"operator"}` |

Visitors **never** receive internal events (notes, tags, assignment, AI hand-off).

## Operator API

These endpoints are under `operator/`. They need a staff session plus CSRF, and return `401`/`403` JSON otherwise.

| Method & path | Purpose |
|---|---|
| `GET api/bootstrap/` | Current operator, operators, tags, quick replies, languages, AI status, webhooks (superuser), blocked list |
| `POST api/heartbeat/` | Mark online |
| `GET conversations/` | Inbox and counters. Filters: `status` (`open`/`closed`/`all`), `assigned` (`me`/`unassigned`), `unread=1`, `priority=high`, `tag=<id>`, `q=<text>`. Paging: `limit` (default 40) and `cursor` (the previous response's `next_cursor`) |
| `GET conversations/<id>/?before=<msg id>` | Conversation and messages (including notes); marks visitor messages read |
| `POST conversations/<id>/send/` | `text`, `internal`, `reply_to`, `file` |
| `POST conversations/<id>/close/` · `reopen/` · `delete/` · `block/` | Actions |
| `POST conversations/<id>/assign/` | `{}` assigns to me, `{"operator_id": 3}` assigns to operator 3, `{"operator_id": null}` unassigns |
| `POST conversations/<id>/update/` | `subject`, `priority` (`low`/`normal`/`high`), `ai_enabled` |
| `POST conversations/<id>/tags/` | `{"tag_ids": [1, 2]}` |
| `POST conversations/<id>/react/` · `typing/` | Same as the visitor endpoints |
| `GET conversations/<id>/transcript/?notes=1` · `POST .../transcript/email/` | Transcripts |
| `POST api/tags/` · `api/tags/<id>/delete/` | Tags |
| `POST api/canned/` · `api/canned/<id>/delete/` | Quick replies (`shortcut`, `title`, `text`) |
| `POST api/blocked/<id>/delete/` | Unblock |
| `POST api/webhooks/<id>/test/` | Send a test event (superuser) |
| `GET api/analytics/?days=7` | Chart data |
| `GET api/stream/` | SSE firehose of every event in every conversation, plus `conversation.created/updated/deleted` and `ai.handoff` |

## Example: a minimal native client

The sketch below shows the flow in pseudo-code. It is not a packaged SDK.

```text
POST /supchat/start/           headers: X-Supchat-Client: android
  -> {conversation: {id}, guest_token}
POST /supchat/conversations/{id}/messages/   headers: X-Supchat-Guest: {guest_token}
  body: {"text": "Hi from the app"}
GET  /supchat/conversations/{id}/events/     headers: X-Supchat-Guest: {guest_token}
  -> text/event-stream
```
