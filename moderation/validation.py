"""Keep batch comparisons hidden until all selected submissions are audited."""

import hashlib
import json

from .attempts import select_attempts
from .criteria import CRITERIA, REMINDER_CHECKS, STATUSES


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
    skipped = sum("skipped" in {c["human_status"], c["tool_status"]} for c in cases)
    return {
        "total": len(cases),
        "compared": len(pairs),
        "agreed": agreed,
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
            {"submission": row["submission"]["id"], "audit": row["audit"]}
            for row in state["audit_rows"]
        ],
    }
    return hashlib.sha256(
        json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
