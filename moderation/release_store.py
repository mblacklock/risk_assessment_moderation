"""Private release records, deliberately separate from moderation review files."""

import json
import os
import uuid

from django.conf import settings

from . import store


def path():
    return settings.REVIEW_ROOT / "feedback-release" / "register.json"


def load():
    with store.LOCK:
        try:
            data = json.loads(path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if data.get("schema") != 1 or not isinstance(data.get("records"), dict):
            raise ValueError("Unsupported feedback release register.")
        return data


def save(data):
    with store.LOCK:
        destination = path()
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(str(uuid.uuid4()) + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, destination)


def update(revision, change):
    with store.LOCK:
        data = load()
        if not data or data["revision"] != revision:
            raise ValueError("The register changed. Reload before saving.")
        change(data)
        data.update(revision=uuid.uuid4().hex, updated=store.now())
        save(data)
        return data
