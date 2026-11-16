# Installation

## Requirements

- Python 3.9+
- Django 4.2+ (CI runs 4.2 and 5.1; developed against 6.1)
- Any database Django supports
- A cache backend for rate limits. The default `LocMemCache` works on one process; use Redis or Memcached with several workers.

There are no other runtime dependencies.

## 1. Install

```bash
pip install django-supchat
# optional WebSocket transport:
pip install "django-supchat[channels]"
```

## 2. Settings

```python
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "supchat",
]

# Attachments are stored with your default storage (FileSystemStorage, S3, ...)
MEDIA_ROOT = BASE_DIR / "media"

SUPCHAT = {
    "TITLE": "Acme Support",
}
```

`django.middleware.csrf.CsrfViewMiddleware`, `SessionMiddleware` and `AuthenticationMiddleware` must be enabled. They are on by default in new projects.

Attachments are always served through an access-checked view (`/supchat/attachments/<id>/`). You do **not** need to expose `MEDIA_URL` publicly for them. In fact you should not serve `MEDIA_ROOT/supchat/` directly in production.

## 3. URLs

```python
from django.urls import include, path

urlpatterns = [
    path("supchat/", include("supchat.urls")),
]
```

Any prefix works. The widget discovers its endpoints with `reverse()`.

## 4. Migrate

```bash
python manage.py migrate
```

## 5. Render the widget

```django
{% load supchat %}
<!doctype html>
<html lang="en">
  <body>
    ...
    {% supchat %}
  </body>
</html>
```

Render it inside a template that has `request` in its context, which is the default with `django.template.context_processors.request`.

## 6. Operators

Any **staff** user can open `/supchat/operator/`. An `Operator` profile is created on their first visit. You can also create `Operator` rows in the Django admin, or with:

```python
from supchat.models import Operator
Operator.objects.create(user=user)
```

## Upgrading from 1.x

- Run `python manage.py migrate` (migration `0002_features` adds new fields and models; existing data is kept).
- **CSRF is now enforced** on the visitor API. The bundled widget already sends the token. Custom clients must send `X-CSRFToken`, or use the [header token](api.md#native--mobile-clients).
- The operator JSON API now answers `401`/`403` JSON instead of redirecting to the admin login. The HTML page still redirects.
- The operator panel no longer loads Chart.js from a CDN. Charts are inline SVG.
- `GET /conversations/<id>/messages/` now returns the **latest** 50 messages plus `has_more`. Page backwards with `?before=<id>`.
