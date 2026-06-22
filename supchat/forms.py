from __future__ import annotations

from django import forms

from .conf import supchat_settings
from .services import sanitize_message_text


class SendMessageForm(forms.Form):
    text = forms.CharField(strip=False)

    def clean_text(self):
        return sanitize_message_text(self.cleaned_data["text"])


class MessageReadForm(forms.Form):
    message_ids = forms.JSONField(required=False)

    def clean_message_ids(self):
        ids = self.cleaned_data.get("message_ids")
        if ids in (None, ""):
            return None
        if not isinstance(ids, list) or not all(isinstance(item, int) for item in ids):
            raise forms.ValidationError("message_ids must be a list of integers.")
        return ids


class WidgetSettingsForm(forms.Form):
    title = forms.CharField(initial=supchat_settings.get("TITLE"), required=False)
