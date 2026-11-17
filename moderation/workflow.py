"""Moderator progress is independent of student correction outcomes."""

import hashlib
import json

from .criteria import REMINDER_CHECKS, effective_status

FLAGGED = {"issue", "review", "unable", "supervisor", "moderator"}
REVIEW_FIELDS = ("reviewed_at", "reviewed_fingerprint")


def finding_fingerprint(check):
    payload = {
        key: check.get(key) for key in ("status", "source", "message", "evidence")
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def review_progress(check, review=None):
    reviewed = bool(check.get("reviewed_at")) and check.get(
        "reviewed_fingerprint"
    ) == finding_fingerprint(check)
    if check["id"] in REMINDER_CHECKS:
        reviewed = False
    from .review_policy import automatically_accepted

    automatic = automatically_accepted(review or {}, check) and not reviewed
    resolved = (reviewed or automatic) and effective_status(check) in {
        "complete",
        "issue",
        "supervisor",
    }
    flagged = check["id"] not in REMINDER_CHECKS and (
        check.get("status") in FLAGGED or effective_status(check) in FLAGGED
    )
    return {
        "reviewed": reviewed,
        "review_resolved": reviewed and resolved,
        "needs_review": flagged and not reviewed and not automatic,
        "automatic": automatic,
        "review_required": flagged and not automatic,
        "review_unresolved": flagged and reviewed and not resolved,
        "flagged": flagged,
        "review_label": (
            "Reminder only — not assessed"
            if check["id"] in REMINDER_CHECKS
            else "Skipped — prerequisite missing"
            if effective_status(check) == "skipped"
            else "Reviewed — supervisor follow-up"
            if reviewed and effective_status(check) == "supervisor"
            else "Reviewed — unresolved"
            if reviewed and not resolved
            else "Reviewed — result overridden"
            if reviewed
            and check.get("decision")
            and check["decision"] != check["status"]
            else "Reviewed — automated result confirmed"
            if reviewed
            else "Automatic — validated check"
            if automatic
            else "Not reviewed"
        ),
    }
