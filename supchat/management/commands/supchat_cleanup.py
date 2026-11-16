from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from supchat.conf import supchat_settings
from supchat.models import Conversation
from supchat.services import delete_conversation


class _Staff:
    """Minimal stand-in so the service layer's staff check passes for maintenance jobs."""
    is_authenticated = True
    is_staff = True
    pk = None


class Command(BaseCommand):
    help = "Auto-close idle conversations (AUTO_CLOSE_AFTER_HOURS) and purge old closed ones (RETENTION_DAYS)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        now = timezone.now()
        dry = opts["dry_run"]
        closed = purged = 0
        hours = int(supchat_settings.get("AUTO_CLOSE_AFTER_HOURS"))
        if hours > 0:
            idle = Conversation.objects.filter(status="open", last_message_at__lt=now - timedelta(hours=hours))
            closed = idle.count()
            if not dry:
                idle.update(status="closed", closed_at=now)
        days = int(supchat_settings.get("RETENTION_DAYS"))
        if days > 0:
            old = Conversation.objects.filter(status="closed", closed_at__lt=now - timedelta(days=days))
            purged = old.count()
            if not dry:
                for conv in old:
                    for m in conv.messages.exclude(attachment="").exclude(attachment__isnull=True):
                        m.attachment.delete(save=False)
                    conv.delete()
        self.stdout.write(f"{'[dry-run] ' if dry else ''}closed={closed} purged={purged}")
