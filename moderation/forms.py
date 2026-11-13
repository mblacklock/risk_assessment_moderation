import os

from django import forms

from .documents import MAX_ZIP


class UploadForm(forms.Form):
    title = forms.CharField(max_length=150, initial="KB6060 · Risk assessment & ethics")
    archive = forms.FileField(label="Turnitin / Blackboard ZIP")
    use_ai = forms.BooleanField(required=False, label="Include AI language checks")

    def clean_archive(self):
        file = self.cleaned_data["archive"]
        if not file.name.lower().endswith(".zip"):
            raise forms.ValidationError("Choose a ZIP file.")
        if file.size > MAX_ZIP:
            raise forms.ValidationError("ZIP must be 150 MB or smaller.")
        return file

    def clean_use_ai(self):
        value = self.cleaned_data["use_ai"]
        if value and not os.getenv("OPENAI_API_KEY"):
            raise forms.ValidationError(
                "Configure OPENAI_API_KEY in .env to enable AI checks."
            )
        return value


class DecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("", "Keep automated result"),
            ("complete", "Complete"),
            ("issue", "Issue found"),
            ("review", "Manual check"),
            ("unable", "Unable to check"),
        ],
        required=False,
    )
    note = forms.CharField(max_length=3000, required=False, widget=forms.Textarea)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("decision") and not cleaned.get("note", "").strip():
            self.add_error("note", "Record a note explaining your decision.")
        return cleaned
