# Python API, signals & management command

## Service layer (`supchat.services`)

These functions are the stable integration point. Each one checks permissions with the `request` you pass in.

```python
from supchat.services import (
    get_or_create_conversation,   # (request, locale="") -> (Conversation, guest_id | None)
    send_message,                 # (request, conversation, text, *, upload=None, reply_to_id=None, internal=False) -> Message
    close_conversation,           # (request, conversation)
    reopen_conversation,          # (request, conversation)          staff only
    assign_operator,              # (request, conversation, operator=None)
    unassign_operator,            # (request, conversation)          staff only
    update_conversation,          # (request, conversation, subject=, priority=, ai_enabled=)
    set_conversation_tags,        # (request, conversation, tag_ids)
    toggle_reaction,              # (request, conversation, message_id, emoji)
    rate_conversation,            # (request, conversation, rating, comment="")
    update_visitor_profile,       # (request, conversation, name="", email="")
    block_visitor,                # (request, conversation, reason="")
    delete_conversation,          # (request, conversation)          staff only
    mark_messages_read,           # (request, conversation, message_ids=None) -> int
    post_bot_message,             # (conversation, text)             no request needed
)
```

`PermissionDenied` and `ValidationError` are raised on failure (`RateLimitExceeded` is a `PermissionDenied`).

## Signals (`supchat.signals`)

| Signal | Arguments |
|---|---|
| `conversation_started` | `conversation` (sent with its first visible message) |
| `message_created` | `message`, `conversation` |
| `messages_read` | `conversation`, `message_ids`, `reader` |
| `conversation_closed` | `conversation`, `closed_by` |
| `conversation_rated` | `conversation`, `rating` |
| `operator_online` / `operator_offline` | `operator` |

```python
from django.dispatch import receiver
from supchat.signals import message_created

@receiver(message_created)
def notify(sender, message, conversation, **kwargs):
    if message.sender_type in ("guest", "user") and not message.is_internal:
        ...  # e.g. push to your CRM
```

## Models

`Conversation`, `Message`, `Operator`, `Reaction`, `Tag`, `CannedResponse`, `WebhookEndpoint` and `BlockedVisitor` are all registered in the Django admin.

## Management command

```bash
python manage.py supchat_cleanup [--dry-run]
```

It closes open conversations idle for longer than `AUTO_CLOSE_AFTER_HOURS`, and deletes closed conversations (and their files) older than `RETENTION_DAYS`.

## AI helpers (`supchat.ai`)

`generate_reply(conversation) -> str` and `maybe_auto_reply(conversation_id, message_id)` let you run the assistant from your own task queue.
