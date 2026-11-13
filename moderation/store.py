"""Local JSON storage with atomic writes. No database or browser cookie state."""

import json
import os
import threading
import uuid
from datetime import datetime, timezone

from django.conf import settings

LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def review_dir(review_id):
    # Canonical UUID validation prevents using a URL as a filesystem path.
    key = str(uuid.UUID(str(review_id)))
    return settings.REVIEW_ROOT / key


def load(review_id):
    with LOCK:
        return json.loads(
            (review_dir(review_id) / "review.json").read_text(encoding="utf-8")
        )


def save(review):
    with LOCK:
        directory = review_dir(review["id"])
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / (str(uuid.uuid4()) + ".tmp")
        temporary.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, directory / "review.json")


def update(review_id, change):
    with LOCK:
        review = load(review_id)
        change(review)
        review["updated"] = now()
        save(review)
        return review


def list_reviews():
    if not settings.REVIEW_ROOT.exists():
        return []
    reviews = []
    for path in settings.REVIEW_ROOT.glob("*/review.json"):
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
            reviews.append(
                {k: review[k] for k in ("id", "title", "created", "state")}
                | {"count": len(review["submissions"])}
            )
        except (ValueError, KeyError, OSError):
            continue
    return sorted(reviews, key=lambda review: review["created"], reverse=True)
