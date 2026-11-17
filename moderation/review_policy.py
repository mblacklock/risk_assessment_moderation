"""Explicit, version-bound automation approval; never inferred from test passes."""

import hashlib
import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def software_version():
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for name in (
        "checks.py",
        "criteria.py",
        "documents.py",
        "ai.py",
        "word_drawings.py",
        "legacy_word.py",
        "review_policy.py",
    ):
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def checking_version():
    return hashlib.sha256(
        (software_version() + os.getenv("OPENAI_MODEL", "gpt-5-mini")).encode()
    ).hexdigest()


def approval_key(check):
    return f"{check['id']}:{check.get('source', 'Rule')}"


def automatically_accepted(review, check):
    if review.get("review_mode", "validation") != "routine":
        return False
    if check.get("decision") or check.get("status") not in {"issue", "supervisor"}:
        return False
    version = checking_version()
    approval = review.get("automation_approvals", {}).get(approval_key(check), {})
    return bool(
        approval.get("reference")
        and approval.get("version") == version
        and check.get("engine_version") == version
    )
