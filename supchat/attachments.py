"""Attachment validation: extension allowlist, size cap and magic-byte sniffing (no Pillow needed)."""
from __future__ import annotations

import os
import re

from django.core.exceptions import ValidationError

from .conf import supchat_settings

_MAGIC: dict[str, tuple[bytes, ...]] = {
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "gif": (b"GIF87a", b"GIF89a"),
    "webp": (b"RIFF",),
    "pdf": (b"%PDF-",),
    "zip": (b"PK\x03\x04",),
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
}
_TEXT_EXT = {"txt", "csv", "log"}
IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "pdf": "application/pdf", "txt": "text/plain", "csv": "text/csv",
    "zip": "application/zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
# Never allowed, whatever the settings say: these execute in a browser or on a server.
_FORBIDDEN = {"svg", "html", "htm", "xhtml", "js", "mjs", "php", "exe", "bat", "cmd", "sh", "py", "dll", "jar", "xml"}


def clean_filename(name: str) -> str:
    name = os.path.basename(name or "file").replace("\x00", "")
    name = re.sub(r"[\r\n\t\\/]", "_", name).strip() or "file"
    return name[:120]


def extension_of(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def mime_for(ext: str) -> str:
    return _MIME.get(ext, "application/octet-stream")


def validate_upload(upload) -> tuple[str, str, int]:
    """Return (clean_name, ext, size) or raise ValidationError."""
    if not supchat_settings.get("ATTACHMENTS"):
        raise ValidationError("Attachments are disabled.")
    name = clean_filename(getattr(upload, "name", ""))
    ext = extension_of(name)
    allowed = {e.lower().lstrip(".") for e in supchat_settings.get("ATTACHMENT_EXTENSIONS")}
    if not ext or ext in _FORBIDDEN or ext not in allowed:
        raise ValidationError("This file type is not allowed.")
    limit = int(float(supchat_settings.get("ATTACHMENT_MAX_MB")) * 1024 * 1024)
    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0:
        raise ValidationError("The file is empty.")
    if size > limit:
        raise ValidationError(f"File is too large (max {supchat_settings.get('ATTACHMENT_MAX_MB')} MB).")
    head = upload.read(16)
    upload.seek(0)
    if ext in _MAGIC:
        if not any(head.startswith(sig) for sig in _MAGIC[ext]):
            raise ValidationError("File content does not match its extension.")
        if ext == "webp":
            upload.seek(8)
            tag = upload.read(4)
            upload.seek(0)
            if tag != b"WEBP":
                raise ValidationError("File content does not match its extension.")
    elif ext in _TEXT_EXT:
        if b"\x00" in upload.read(4096):
            upload.seek(0)
            raise ValidationError("File content does not match its extension.")
        upload.seek(0)
    return name, ext, size
