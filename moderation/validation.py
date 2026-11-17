"""Keep batch comparisons hidden until all selected submissions are audited."""

import hashlib
import json
from collections import Counter

from .attempts import select_attempts
from .criteria import CRITERIA, REMINDER_CHECKS, STATUSES

ADJUDICATIONS = {
    "human_error": "Human error caught by the tool",
    "tool_error": "Tool error",
    "interpretation": "Rubric / interpretation disagreement",
    "audit_mapping": "Audit recording / category mapping gap",
    "unresolved": "Unresolved",
    "agreement": "Confirmed agreement",
}


def historical_adjudications(review):
    """Read the earlier private evaluation log without converting or rewriting it."""
    from . import store

    path = store.review_dir(review["id"]) / "evaluation-decisions.json"
    if not path.exists():
        return []
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Evaluation decision log exceeds the read limit.")
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or data.get("review_id") != review["id"]
            or not isinstance(data.get("adjudications"), list)
        ):
            raise ValueError("Evaluation decision log has an unexpected structure.")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "The earlier evaluation decision log could not be read."
        ) from error
    return [
        record
        for record in data["adjudications"]
        if isinstance(record, dict)
        and all(
            isinstance(record.get(key), str)
            for key in ("student_number", "check", "classification")
        )
        and (record.get("reason") is None or isinstance(record["reason"], str))
    ]


def audit_overview(review):
    rows = []
    allowed = {"complete", "issue", "supervisor", "review", "skipped"}
    for item in select_attempts(review).active:
        history = item.get("validation_audits", [])
        audit = history[-1] if history else None
        complete = bool(audit) and all(
            audit.get("findings", {}).get(key) in allowed
            for key, _, _ in CRITERIA
            if key not in REMINDER_CHECKS
        )
        rows.append({"submission": item, "audit": audit, "audited": complete})
    count = sum(row["audited"] for row in rows)
    return {
        "audit_rows": rows,
        "batch_auditor": review.get("audit_details", {}).get("auditor", ""),
        "audited_count": count,
        "audit_total": len(rows),
        "comparison_ready": bool(rows)
        and count == len(rows)
        and review["state"] not in {"queued", "running"}
        and all(row["submission"]["state"] == "done" for row in rows),
    }


def comparison_rows(audit):
    automated = {check["id"]: check for check in audit["automated_snapshot"]}
    return [
        {
            "id": key,
            "label": label,
            "source": automated.get(key, {}).get("source", "Not recorded"),
            "version": automated.get(key, {}).get("engine_version", ""),
            "model": audit.get("ai_metadata", {}).get("model", "Not recorded")
            if automated.get(key, {}).get("source") == "AI"
            else "Not applicable",
            "category": category,
            "human_status": audit["findings"].get(key, "unable"),
            "tool_status": automated.get(key, {}).get("status", "unable"),
            "human": STATUSES.get(audit["findings"].get(key), "Not recorded"),
            "tool": STATUSES.get(automated.get(key, {}).get("status"), "Not available"),
            "message": automated.get(key, {}).get("message", ""),
            "same": audit["findings"].get(key) == automated.get(key, {}).get("status"),
        }
        for key, label, category in CRITERIA
        if key not in REMINDER_CHECKS
    ]


def summarise_cases(cases):
    """Descriptive comparison with the auditor, not adjudicated accuracy."""
    definite = {"complete", "issue", "supervisor"}
    pairs = [
        c
        for c in cases
        if c["human_status"] in definite and c["tool_status"] in definite
    ]
    agreed = sum(c["same"] for c in pairs)
    tool_definite = sum(c["tool_status"] in definite for c in cases)
    skipped = sum("skipped" in {c["human_status"], c["tool_status"]} for c in cases)
    historical = Counter(
        c["historical_decision"]["classification"]
        for c in cases
        if c.get("historical_decision")
    )
    return {
        "total": len(cases),
        "compared": len(pairs),
        "agreed": agreed,
        "tool_definite": tool_definite,
        "coverage": f"{tool_definite}/{len(cases)} ({100 * tool_definite / len(cases):.1f}%)"
        if cases
        else "No audited cases",
        "agreement": f"{agreed}/{len(pairs)} ({100 * agreed / len(pairs):.1f}%)"
        if pairs
        else "No definite pairs",
        "audit_issues": sum(c["human_status"] == "issue" for c in cases),
        "possible_missed": sum(
            c["human_status"] == "issue"
            and c["tool_status"] in {"complete", "supervisor"}
            for c in cases
        ),
        "possible_extra": sum(
            c["human_status"] in {"complete", "supervisor"}
            and c["tool_status"] == "issue"
            for c in cases
        ),
        "followup_differences": sum(
            {c["human_status"], c["tool_status"]} == {"complete", "supervisor"}
            for c in cases
        ),
        "tool_uncertain": sum(
            c["tool_status"] not in definite | {"skipped"} for c in cases
        ),
        "audit_uncertain": sum(
            c["human_status"] not in definite | {"skipped"} for c in cases
        ),
        "skipped": skipped,
        "adjudicated": sum(bool(c.get("adjudication")) for c in cases),
        "historical_adjudicated": sum(historical.values()),
        "historical_counts": [
            {"label": label, "count": count}
            for label, count in sorted(historical.items())
        ],
        "adjudication_counts": [
            {
                "classification": key,
                "label": label,
                "count": sum(
                    c.get("adjudication", {}).get("classification") == key
                    for c in cases
                ),
            }
            for key, label in ADJUDICATIONS.items()
        ],
    }


def check_statistics(comparisons):
    statistics = []
    for key, label, category in CRITERIA:
        if key in REMINDER_CHECKS:
            continue
        cases = [
            {**result, "submission": comparison["submission"]}
            for comparison in comparisons
            for result in comparison["rows"]
            if result["id"] == key
        ]
        groups = {}
        for case in cases:
            identity = (case["source"], case["version"], case["model"])
            groups.setdefault(identity, []).append(case)
        strata = [
            {
                "source": source,
                "version": version,
                "model": model,
                **summarise_cases(group),
            }
            for (source, version, model), group in groups.items()
        ]
        statistics.append(
            {
                "id": key,
                "label": label,
                "category": category,
                **summarise_cases(cases),
                "strata": strata,
                "cases": cases,
                "mixed_versions": len(groups) > 1,
                "unknown_versions": sum(not c["version"] for c in cases),
            }
        )
    return statistics


def comparison_token(review):
    state = audit_overview(review)
    evidence = {
        "review": review["id"],
        "details": review.get("audit_details", {}),
        "audits": [
            {
                "submission": row["submission"]["id"],
                "audit": row["audit"],
                "adjudications": row["submission"].get("audit_adjudications", []),
            }
            for row in state["audit_rows"]
        ],
    }
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
