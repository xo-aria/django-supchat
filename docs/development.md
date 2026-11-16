# Development & testing

```bash
git clone https://github.com/xo-aria/django-supchat.git
cd django-supchat
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[test]"
pytest --cov=supchat
```

The suite (230+ tests) covers:

- settings, models, sanitization and permissions
- the visitor API: CSRF, header tokens, pagination, attachments, reactions, ratings, transcripts, blocking, rate limits
- the operator API: filters, notes, assignment, tags, quick replies, analytics, webhooks
- SSE audience scoping and the broadcast hook
- AI providers (mocked HTTP), handoff and loop prevention
- webhooks (signatures, SSRF guard, delivery)
- the WebSocket adapter (skipped without Channels)
- the cleanup command, admin pages, the template tag, and i18n key parity

No test makes a real network call.

CI runs the suite on Python 3.10–3.13 with Django 4.2, 5.1 and 5.2 (`.github/workflows/tests.yml`).

## Running a demo locally

```bash
django-admin startproject demo && cd demo
pip install -e ../django-supchat
```

Add `"supchat"` to `INSTALLED_APPS`, include `supchat.urls` at `/supchat/`, add `{% load supchat %}{% supchat %}` to a template, then:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open the page in one browser as a visitor, and `/supchat/operator/` in another browser (or a private window) as the superuser.

To try AI replies without an API key, use a custom provider:

```python
# demo/bot.py
def reply(messages, conversation):
    return "Echo: " + messages[-1]["content"]

SUPCHAT = {"AI": {"ENABLED": True, "PROVIDER": "custom", "CALLABLE": "bot.reply"}}
```

## Guidelines

- Keep the core free of runtime dependencies.
- Render user content with `textContent` only.
- Every new endpoint needs a permission test and a CSRF-aware test.
- Add new UI strings to `i18n.js` in **both** `en` and `fa`. The test suite checks this.
- Run `black` and `ruff` (`line-length = 100`).
