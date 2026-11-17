"""Select Blackboard attempts without deleting originals or relying on file dates."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MONTHS = {
    name: index
    for index, name in enumerate(
        "january february march april may june july august september october november december".split(),
        1,
    )
}


def submission_timestamp(item):
    """Read Date Submitted first, then Blackboard's timestamped attempt filename."""
    raw = item.get("submitted", "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is None:
        match = re.search(
            r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+(\d{2}):(\d{2}):(\d{2})",
            raw,
        )
        if match and match[2].casefold() in MONTHS:
            try:
                parsed = datetime(
                    int(match[3]),
                    MONTHS[match[2].casefold()],
                    int(match[1]),
                    int(match[4]),
                    int(match[5]),
                    int(match[6]),
                )
            except ValueError:
                return None
            zone = re.search(r"\b(BST|GMT|UTC)\b", raw, re.I)
            if zone:
                parsed = parsed.replace(
                    tzinfo=timezone(
                        timedelta(hours=1 if zone[1].upper() == "BST" else 0)
                    )
                )
    if parsed is None:
        match = re.search(
            r"_attempt_(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})(?:\D|$)",
            item.get("attempt", ""),
            re.I,
        )
        if match:
            try:
                parsed = datetime.strptime(match[1], "%Y-%m-%d-%H-%M-%S")
            except ValueError:
                return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        london = ZoneInfo("Europe/London")
        first, second = (
            parsed.replace(tzinfo=london, fold=0),
            parsed.replace(tzinfo=london, fold=1),
        )
        if first.utcoffset() != second.utcoffset():
            return None  # Ambiguous or nonexistent local clock time.
        parsed = first
    return parsed.astimezone(timezone.utc)


@dataclass
class AttemptSelection:
    active: list
    earlier: list
    warnings: list


def select_attempts(review):
    submissions = review["submissions"]
    if not review.get("latest_only", False):
        return AttemptSelection(list(submissions), [], [])
    groups, warnings = {}, []
    keep = set()
    for index, item in enumerate(submissions):
        number = item.get("number", "").strip().casefold()
        if not re.fullmatch(r"w\d{7,10}", number):
            keep.add(index)
            warning = "Submissions without a reliable student number were retained for analysis."
            if warning not in warnings:
                warnings.append(warning)
            continue
        # A ZIP can contain separate assessments; never replace one with another.
        match = re.search(
            r"^(.*?)_w\d{7,10}(?:_attempt|\.txt)", item.get("attempt", ""), re.I
        )
        assessment = match[1].casefold() if match else ""
        groups.setdefault((number, assessment), []).append(index)
    for (number, _), indices in groups.items():
        if len(indices) == 1:
            keep.update(indices)
            continue
        timestamps = [submission_timestamp(submissions[index]) for index in indices]
        if any(stamp is None for stamp in timestamps):
            keep.update(indices)
            warnings.append(
                f"Could not determine the latest attempt for {number}: a submission timestamp is missing or unreadable. All its attempts were retained for analysis."
            )
            continue
        newest = max(timestamps)
        latest = [
            index
            for index, stamp in zip(indices, timestamps, strict=True)
            if stamp == newest
        ]
        keep.update(latest)
        if len(latest) > 1:
            warnings.append(
                f"Multiple attempts for {number} share the latest submission timestamp. All tied latest attempts were retained for analysis."
            )
    return AttemptSelection(
        [item for index, item in enumerate(submissions) if index in keep],
        [item for index, item in enumerate(submissions) if index not in keep],
        warnings,
    )
