from __future__ import annotations

from django import forms

from .services import sanitize_message_text


class SendMessageForm(forms.Form):
    text = forms.CharField(strip=False, required=False)

    def __init__(self, *args, allow_empty: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_empty = allow_empty

    def clean_text(self):
        return sanitize_message_text(self.cleaned_data.get("text") or "", allow_empty=self.allow_empty)


class MessageReadForm(forms.Form):
    message_ids = forms.JSONField(required=False)

    def clean_message_ids(self):
        ids = self.cleaned_data.get("message_ids")
        if ids in (None, ""):
            return None
        if not isinstance(ids, list) or not all(isinstance(item, int) for item in ids):
            raise forms.ValidationError("message_ids must be a list of integers.")
        return ids
