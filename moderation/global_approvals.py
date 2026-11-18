"""Shared staff decisions; checking provenance and audit snapshots stay unchanged."""

import copy
import json
import os
import uuid
from functools import lru_cache

from django.conf import settings

from . import store
from .review_policy import automatically_accepted as version_matched_acceptance
from .review_policy import checking_version


def registry_path():
    return settings.REVIEW_ROOT / "global-approvals.json"


@lru_cache(maxsize=8)
def _read(path, modified, size):
    return json.loads(path.read_text(encoding="utf-8"))


def load():
    """None means this workspace has not adopted shared approvals yet."""
    with store.LOCK:
        path = registry_path()
        try:
            stat = path.stat()
            data = _read(path, stat.st_mtime_ns, stat.st_size)
            if data.get("schema") != 1 or not isinstance(data.get("approvals"), dict):
                raise ValueError("Unsupported global approval registry.")
            return copy.deepcopy(data)
        except FileNotFoundError:
            return None


def revision():
    return (load() or {}).get("revision", "new")


def approvals(review=None):
    registry = load()
    if registry is not None:
        # An empty registry is authoritative: withdrawing a global decision must
        # never expose an old per-review approval and reactivate it.
        return registry["approvals"]
    return (review or {}).get("automation_approvals", {})


def current_approvals(review=None):
    version = checking_version()
    return {
        key: value
        for key, value in approvals(review).items()
        if value.get("version") == version and value.get("reference")
    }


def automatically_accepted(review, check):
    try:
        shared = approvals(review)
    except (OSError, ValueError, TypeError):
        # An unreadable registry must never silently restore local approvals.
        return False
    return version_matched_acceptance({**review, "automation_approvals": shared}, check)


def set_approval(
    key, action, version, reference="", note="", *, expected_revision=None, origin=None
):
    from .criteria import BY_ID, REMINDER_CHECKS

    criterion, separator, source = key.partition(":")
    if (
        not separator
        or criterion not in BY_ID
        or criterion in REMINDER_CHECKS
        or source not in {"Rule", "AI"}
        or action not in {"approve", "revoke"}
    ):
        raise ValueError("Choose a valid check, source and approval action.")
    if version != checking_version():
        raise ValueError("The checking version changed. Reload Global approvals.")
    if action == "approve" and not reference.strip():
        raise ValueError("Record the validation evidence supporting this approval.")
    if len(reference) > 4000 or len(note) > 5000:
        raise ValueError(
            "Keep evidence within 4,000 and notes within 5,000 characters."
        )
    with store.LOCK:
        data = load() or {
            "schema": 1,
            "revision": "new",
            "approvals": {},
            "history": [],
        }
        if expected_revision is not None and expected_revision != data["revision"]:
            raise ValueError("Approvals changed. Reload before saving your decision.")
        previous = copy.deepcopy(data["approvals"].get(key))
        if action == "approve":
            approval = {
                "version": version,
                "reference": reference.strip(),
                "note": note.strip(),
                "at": store.now(),
            }
            if origin:
                approval["origin"] = copy.deepcopy(origin)
            data["approvals"][key] = approval
        else:
            approval = None
            data["approvals"].pop(key, None)
        data["history"].append(
            {
                "key": key,
                "action": action,
                "version": version,
                "at": store.now(),
                "previous_approval": previous,
                "approval": approval,
            }
        )
        data["revision"] = str(uuid.uuid4())
        path = registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(str(uuid.uuid4()) + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        _read.cache_clear()
        return data
