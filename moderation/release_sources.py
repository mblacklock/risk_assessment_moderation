"""Decision-relevant source comparison, separate from strict live-preview tokens."""

import copy

from .criteria import REMINDER_CHECKS


def signature(bundle):
    from .release import PUBLIC_FIELDS, propose
    from .release_decisions import explicit_moderation

    result = copy.deepcopy(bundle)
    proposal = propose(bundle)
    resolved = {d["criterion"]: d for d in proposal.get("decisions", [])}
    for source in result.get("sources", []) + result.get("supplemental", []):
        # The resolved outcome below captures whether a validated finding is
        # accepted. Record policy provenance privately without treating an added
        # reference as a changed human judgement; withdrawal still restores gaps.
        source.pop("automatic_acceptances", None)
        checks = []
        for check in source["checks"]:
            if check["id"] in REMINDER_CHECKS:
                continue
            action = explicit_moderation(check)
            final = resolved.get(check["id"], {})
            human = bool(
                final.get("origin")
                and final["origin"] != "No recorded correction for this unflagged check"
                and final.get("proposed")
                in {"complete", "issue", "supervisor", "skipped"}
                and not final.get("gap")
            )
            checks.append(
                {
                    "id": check["id"],
                    "status": final["proposed"] if human else check["status"],
                    "source": "Recorded staff judgement"
                    if human
                    else check.get("source"),
                    "action": list(action[:2]) if action else None,
                    "decision": check.get("decision", ""),
                    "note": check.get("note", ""),
                    "history": check.get("history", []),
                }
            )
        source["checks"] = sorted(checks, key=lambda check: check["id"])
    # Changed row-specific instructions or new unresolved findings remain material,
    # even when the displayed check status has not changed.
    result["release_effect"] = {
        **{key: proposal[key] for key in PUBLIC_FIELDS},
        "decision_gaps": sorted(proposal.get("decision_gaps", [])),
        "wording_gaps": sorted(proposal.get("wording_gaps", [])),
    }
    return result


def changed(record, bundle):
    from .release import digest

    if record["source_fingerprint"] == digest(bundle):
        return False
    original = record.get("source_evidence")
    # A missing or inconsistent baseline cannot establish a harmless refresh.
    if not original or digest(original) != record["source_fingerprint"]:
        return True
    try:
        return digest(signature(original)) != digest(signature(bundle))
    except (KeyError, TypeError, ValueError):
        return True


def change_summary(record, bundle):
    if not changed(record, bundle):
        return []
    old = record.get("source_evidence", {})
    reasons = []
    if old.get("roster") != bundle.get("roster"):
        reasons.append("The selected submission, files or student identity changed.")
    before = {s["review_id"]: s for s in old.get("sources", [])}
    after = {s["review_id"]: s for s in bundle.get("sources", [])}
    if before.keys() != after.keys():
        reasons.append("The assessment source selection changed.")
    for key in before.keys() & after.keys():
        a, b = before[key], after[key]
        if a.get("attachment_hashes") != b.get("attachment_hashes") or a.get(
            "submitted"
        ) != b.get("submitted"):
            reasons.append("The assessment source files or submitted attempt changed.")
        checks = {c["id"]: c for c in a["checks"]}
        for check in b["checks"]:
            prior = checks.get(check["id"])
            if check["id"] in REMINDER_CHECKS or not prior:
                continue
            if check["status"] != prior["status"]:
                reasons.append(
                    f"{check['label']}: automated result changed from {prior['status']} to {check['status']}; this does not itself establish a student error."
                )
    return reasons or [
        "Recorded decisions, supporting sources or required feedback changed."
    ]
