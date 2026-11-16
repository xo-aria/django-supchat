"""Tiny background runner so AI calls, webhooks and email never slow down or break a send."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from django.db import close_old_connections, transaction

from .conf import supchat_settings

log = logging.getLogger("supchat")


def _safe(fn: Callable, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:  # background work must never raise into the request
        log.exception("supchat background task %s failed", getattr(fn, "__name__", fn))
    finally:
        close_old_connections()


def run_after_commit(fn: Callable, *args, **kwargs) -> None:
    """Run ``fn`` after the current transaction commits, off the request thread.

    ``SUPCHAT["BACKGROUND"] = "sync"`` runs inline (tests, or if you prefer Celery:
    point it at your own scheduler by wrapping the call sites with signals).
    """

    def launch() -> None:
        if supchat_settings.get("BACKGROUND") == "sync":
            _safe(fn, *args, **kwargs)
            return
        threading.Thread(target=_safe, args=(fn, *args), kwargs=kwargs, daemon=True).start()

    transaction.on_commit(launch)
