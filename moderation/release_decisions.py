"""Recover recorded academic judgements, separating them from tool routing."""

import re
from datetime import datetime

from .criteria import BY_ID, REMINDER_CHECKS, effective_status
from .feedback import FEEDBACK_EXCLUDED, INTERNAL, SUPERVISOR_OWNED, suggested_wording

DEFINITE = {"complete", "issue", "supervisor", "skipped"}
ROUTING = {"review", "moderator", "unable"}


def conversation_matches(source):
    recovered = source.get("conversation_decisions", {})
    return bool(
        recovered
        and recovered.get("attachment_hashes") == source.get("attachment_hashes")
        and recovered.get("submitted") == source.get("submitted")
    )


def stamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError, TypeError):
        return None


def latest_interpretations(source):
    # Audit revisions do not erase decisions tied to the earlier audit. A change
    # to another criterion must not resurrect a disagreement already settled.
    latest = {}
    for record in source.get("historical_adjudications", []):
        latest[record["check"]] = record
    for record in sorted(
        source.get("audit_adjudications", []), key=lambda r: r.get("at", "")
    ):
        latest[record["criterion"]] = record
    if conversation_matches(source):
        for record in sorted(
            source["conversation_decisions"].get("decisions", []), key=lambda r: r["at"]
        ):
            key = record["criterion"]
            prior = latest.get(key)
            if prior is None or (
                stamp(prior.get("at")) is not None
                and stamp(record["at"]) > stamp(prior["at"])
            ):
                latest[key] = record
    return latest


def final_audit_value(source, key, interpretation):
    audits = source.get("validation_audits", [])
    if not audits:
        return None, False
    value = audits[-1].get("findings", {}).get(key)
    if not interpretation or not interpretation.get("audit_at"):
        return value, False
    anchor = next(
        (a for a in audits if a.get("at") == interpretation["audit_at"]), None
    )
    if not anchor:
        return value, False
    previous = anchor.get("findings", {}).get(key)
    changed_after = False
    for audit in audits[audits.index(anchor) + 1 :]:
        changed = audit.get("findings", {}).get(key) != previous
        later = (
            stamp(audit.get("at")) is not None
            and stamp(interpretation.get("at")) is not None
            and stamp(audit["at"]) > stamp(interpretation["at"])
        )
        if changed and later:
            changed_after = True
        previous = audit.get("findings", {}).get(key)
    return value, changed_after


def explicit_moderation(check):
    from .release import human_action

    if check.get("blocked_by") and effective_status(check) == "skipped":
        return None  # Do not resurrect an obsolete unresolved prerequisite finding.
    if human_action(check):
        return (
            effective_status(check),
            check.get("decided_at") or check.get("reviewed_at"),
            "Saved moderation decision",
        )
    # Explicit historical overrides are meaningful without a current queue
    # fingerprint; empty acknowledgements need their original finding snapshot.
    snapshots = [check] + [
        v
        for k, v in check.items()
        if k.startswith("superseded_") and isinstance(v, dict)
    ]
    from .workflow import finding_fingerprint

    for action in reversed(check.get("history", [])):
        if action.get("decision") in DEFINITE:
            return action["decision"], action.get("at"), "Saved moderation history"
        if action.get("decision") == "" and action.get("finding_fingerprint"):
            original = next(
                (
                    v
                    for v in snapshots
                    if all(
                        k in v
                        for k in ["id", "status", "source", "message", "evidence"]
                    )
                    and finding_fingerprint(v) == action["finding_fingerprint"]
                ),
                None,
            )
            if original:
                return (
                    effective_status(original),
                    action.get("at"),
                    "Confirmed original finding",
                )
    return None


def resolve(check, source, bundle, interpretation):
    from .release import adjudicated_status, recorded_waiver, same_attempt

    key = check["id"]
    audit, amended = final_audit_value(source, key, interpretation)
    ops = []
    for priority, candidate in enumerate([source] + bundle.get("supplemental", [])):
        if not same_attempt(candidate, bundle["roster"]):
            continue
        other = next((c for c in candidate["checks"] if c["id"] == key), None)
        action = explicit_moderation(other) if other else None
        if action:
            ops.append(
                {
                    "status": action[0],
                    "at": action[1],
                    "origin": action[2],
                    "priority": priority,
                }
            )
    status, origin, gap = None, "", ""
    most_recent_evaluation = max(
        [stamp(a.get("at")) or 0 for a in source.get("validation_audits", [])]
        + [stamp((interpretation or {}).get("at")) or 0]
    )
    later_operational = any(
        (stamp(op["at"]) or 0) > most_recent_evaluation for op in ops
    )
    if ops and (source.get("assessment_kind") != "validation" or later_operational):
        # Primary saved moderation takes precedence over independent pilot audits.
        # Multiple saved operational decisions use a recorded chronology, not a
        # preference for whichever outcome happens to be Pass.
        primary = [x for x in ops if x["priority"] == 0]
        candidates = primary or ops
        dated = [x for x in candidates if stamp(x["at"]) is not None]
        if len({x["status"] for x in candidates}) > 1 and len(dated) != len(candidates):
            gap = "Conflicting saved moderation decisions have no reliable final ordering."
        else:
            last = max(dated, key=lambda x: stamp(x["at"])) if dated else candidates[0]
            tied = [x for x in dated if stamp(x["at"]) == stamp(last["at"])]
            if len({x["status"] for x in tied}) > 1:
                gap = "Contradictory saved moderation decisions share the final decision time."
            else:
                status, origin = last["status"], last["origin"]
    if status is None and not gap and audit in DEFINITE:
        status, origin = audit, "Recorded staff audit"
    if interpretation and not gap and not later_operational:
        classification = interpretation.get("classification", "").casefold()
        if classification == "unresolved" or interpretation.get(
            "release_decision_pending"
        ):
            status, gap = (
                None,
                "The saved judgement explicitly leaves the academic decision unresolved.",
            )
        elif recorded_waiver(interpretation):
            # Scope is important: a waived unused-row cleanup is not a missing
            # rating judgement. The record explicitly says the rating flag was wrong.
            if (
                interpretation.get("agreed_outcome") in {"issue", "complete"}
                or "wrong tool correction" in classification
            ):
                status, origin = (
                    "complete",
                    "Explicit recorded waiver / corrected category mapping",
                )
        elif not amended:
            agreed = adjudicated_status(interpretation)
            technical_only = (
                "technical answer-placement defect" in classification
                and "moderator discretion" in classification
            )
            if agreed in DEFINITE and not technical_only:
                status, origin = agreed, "Latest agreed staff judgement"
            elif technical_only:
                # This records a self-checker/rubric defect, not an instruction to
                # reverse the operational Pass or the original staff audit.
                origin = (
                    origin
                    or "Recorded operational judgement; technical annotation retained"
                )
            elif agreed in ROUTING and status not in DEFINITE:
                gap = "The saved interpretation requests a manual judgement, but no subsequent human outcome was found."
            # Automatic Manual check/referral is not a new human academic
            # judgement. Retain a definite audit outcome instead of losing it.
    if amended and audit in DEFINITE and not later_operational:
        status, origin = audit, "Later criterion-specific audit correction"
    if status is None and not gap:
        if audit in ROUTING:
            gap = "The saved staff audit leaves this judgement open and no later final decision was found."
        elif (
            source.get("manual_moderation", {}).get("outcome") == "complete"
            and not interpretation
        ):
            status, origin = (
                "complete",
                "Explicit operational Pass in original moderator sheet",
            )
        elif source.get("assessment_kind") == "moderation" and key in source.get(
            "automatic_acceptances", {}
        ):
            status, origin = (
                source["automatic_acceptances"][key]["status"],
                "Validated finding accepted under routine moderation policy",
            )
        elif check["status"] in {"complete", "skipped"} and audit is None:
            status, origin = (
                check["status"],
                "No recorded correction for this unflagged check",
            )
        else:
            gap = (
                "No saved final moderation decision was found for this flagged finding."
            )
    if status in ROUTING:
        gap = (
            gap or "The saved moderation outcome still requires an academic judgement."
        )
        status = None
    return {
        "criterion": key,
        "label": check["label"],
        "proposed": status or "",
        "origin": origin,
        "gap": gap,
        "interpretation": interpretation,
        "recorded_audit": audit,
        "waived": bool(interpretation and recorded_waiver(interpretation)),
    }


def item_reference(text):
    match = re.search(
        r"\bitems?\s+(\d+(?:(?:\s*(?:,|and|&)\s*|\s*[-–]\s*)\d+)*)", text, re.I
    )
    return (
        (" for item" + ("s " if re.search(r"and|,|[-–]", match[1]) else " ") + match[1])
        if match
        else ""
    )


def relevant_manual_text(key, text):
    patterns = {
        "identity": r"assessor",
        "location": r"area|activity|location|KB6060|workshop.*vague",
        "hs_relevance": r"H\s*&\s*S|H&S",
        "ratings": r"final result|final rating|rating.*numer|less final",
        "risk_reduction": r"reduc|initial.*final",
        "admin": r"administrative|related risk|generic to",
        "specialists": r"speci?f(?:ic|c)|specfic|DSEAR|COSHH|PUWER|manual handling",
        "entry_quality": r"job title|typo|inconsisten|dates?",
        "narrative": r"anonym|research question|data.manag",
    }
    pattern = patterns.get(key)
    return " ".join(
        x
        for x in re.split(r"(?<=[.!?])\s*|\n+", text)
        if pattern and re.search(pattern, x, re.I)
    )


def public_action(check, decision, source):
    """Controlled instructions from accepted human findings, never raw private prose."""
    from .release import UNSUITABLE

    key, status = check["id"], decision["proposed"]
    saved = source.get("elp_feedback", {}).get("wording", {}).get(key, "")
    if (
        saved
        and effective_status(check) == status
        and not INTERNAL.search(saved)
        and not UNSUITABLE.search(saved)
    ):
        return saved
    recovered_wording = (decision.get("interpretation") or {}).get("public_wording", "")
    if (
        recovered_wording
        and not INTERNAL.search(recovered_wording)
        and not UNSUITABLE.search(recovered_wording)
    ):
        return recovered_wording
    manual = relevant_manual_text(
        key, source.get("manual_moderation", {}).get("feedback", "")
    )
    reason = (decision.get("interpretation") or {}).get("reason", "") or ""
    if status == "supervisor":
        assessments = check.get("supporting_assessments", [])
        if not assessments:
            match = re.search(
                r"supporting assessments:\s*([^.]+)", check.get("message", ""), re.I
            )
            if match:
                assessments = [match[1].strip()]
        return (
            "Locate and review the supporting specialist assessments for "
            + ", ".join(assessments)
            + "."
            if assessments
            else "Ask your supervisor to review the supporting specialist assessments indicated as required in the risk assessment."
        )
    reference = item_reference(manual)
    if key == "identity":
        return "Enter your own full name in the risk assessment Assessor field; the student undertaking the assessment is the assessor."
    if key == "location":
        return "Complete Area/Activity so it clearly identifies the approved work area or specific activity/test procedure. For physical work, identify the relevant laboratory or workshop; a building or campus name alone is insufficient."
    if key == "facilities":
        return "Agree an appropriate workspace with your supervisor for the stated activities and make the work area and planned activities consistent in the forms."
    if key == "hs_relevance":
        return (
            "Remove the project/data-management consequences"
            + reference
            + " from the hazard list, retaining the relevant health-and-safety hazards and consequences."
        )
    if key == "risk_reduction":
        recorded_context = reason or check.get("message", "")
        recorded_context = " ".join(
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+", recorded_context)
            if not re.search(
                r"guidance|footer|artefact|artifact|counts do not match|not independently validated",
                sentence,
                re.I,
            )
        )
        rows = re.search(
            r"(?:rows?:\s*|rows?\s+)(\d+(?:\s*(?:,|and)\s*\d+)*)",
            recorded_context,
            re.I,
        )
        place = (
            (
                " for risk row"
                + ("s " if re.search(r",|and", rows[1]) else " ")
                + rows[1]
            )
            if rows
            else reference
        )
        return (
            "Review the controls and ratings"
            + place
            + " with your supervisor. The final score must record the risk remaining after controls and be lower than the initial score."
        )
    if key == "ratings":
        if re.search(r"blank Final Result for transporting fixtures", reason, re.I):
            return "In the Instron assessment, enter the missing post-control Final Result score for transporting fixtures. A final score alone is sufficient; showing multiplication is optional."
        # Use recorded row/field instructions only when they are clear. Do not
        # repeat a parser's entry-count assertion as a new student error.
        candidate = suggested_wording(check, "issue")
        if re.search(
            r"Row \d+: enter|Enter the post-control|Enter numeric values", candidate
        ) and not UNSUITABLE.search(candidate):
            return candidate
        return (
            "Enter one clear numeric post-control Final Result score for each assessed hazard"
            + reference
            + ", aligned with its initial rating. A score alone is sufficient; showing multiplication is optional."
        )
    if key == "specialists":
        if re.search(r"DSEAR.*(?:delet|not answer)", manual, re.I):
            return "Restore and answer the DSEAR Yes/No question in the specialist-assessment section."
        return "Select one clear Yes or No in the primary answer field for each specialist-assessment category: Manual Handling, COSHH, PUWER, DSEAR, Young Persons, and New & Expectant Mothers. Add supporting references where applicable."
    if key in {"student_ra", "supervisor_ra", "student_ethics", "supervisor_ethics"}:
        section = "risk assessment" if key.endswith("ra") else "ethics form"
        owner = (
            "Ask your supervisor to complete"
            if key.startswith("supervisor")
            else "Complete"
        )
        missing = re.search(r"Missing:\s*([^.]*)", check.get("message", ""), re.I)
        if (
            missing
            and check.get("status") == "issue"
            and not INTERNAL.search(check["message"])
        ):
            return (
                f"{owner} the missing {missing[1]} in the {section} sign-off section."
            )
        return f"{owner} and date the {section} sign-off, including the required signature."
    if key == "entry_quality":
        if re.search(
            r"job.?title|role content",
            reason + " " + manual + " " + check.get("message", ""),
            re.I,
        ):
            return "Enter Student (or the equivalent student role) as your job title, rather than the project title."
        if re.search(
            r"date|year", reason + " " + manual + " " + check.get("message", ""), re.I
        ):
            return "Correct the inconsistent sign-off dates so each form records the intended date and year accurately."
        if re.search(
            r"lab.code|laboratory.code|room.code|typo", reason + " " + manual, re.I
        ):
            return "Correct the inconsistent laboratory/room reference so the intended location is recorded consistently throughout the forms."
        return ""
    if key == "risk_table":
        if re.search(
            r"persons.*(?:numbers|counts)|count.*identify|numbers only", reason, re.I
        ):
            return "Identify the person or group at risk in the relevant rows, for example Student or Technician, rather than entering counts alone."
        if re.search(r"missing control|omitted control", reason, re.I):
            return (
                "Add the missing control measures for the populated Laptop/PC hazard row."
                if "Laptop/PC" in reason
                else "Complete the missing control measures for the populated hazard rows."
            )
        return "Complete the missing activity, hazard, persons-at-risk and control-measure information in the assessed rows."
    if key == "ethics_details":
        if re.search(
            r"no ethics|ethics (?:form|document).*absent",
            source.get("manual_moderation", {}).get("feedback", "") + " " + reason,
            re.I,
        ) or check.get("missing_form"):
            return "Upload the completed ethics form, including the required declarations and student/supervisor sign-offs."
        missing = re.search(
            r"Missing(?: ethics (?:details|fields))?:\s*([^.]*)",
            check.get("message", ""),
            re.I,
        )
        return (
            "Complete the missing ethics information: " + missing[1] + "."
            if missing
            else "Complete the missing project title and supervisor information in the ethics information table."
        )
    if key == "narrative":
        return "Answer the ethics question about anonymisation of samples/data. Explain how it applies to your project, or state why it is not applicable."
    if key == "tutor":
        return "Ask your supervisor to review and complete the outstanding tutor checklist selections in the ethics form."
    if key == "declarations":
        return "Select all three required student declarations in the ethics form."
    if key == "example":
        return "Remove the retained example row from the risk assessment."
    if key == "supervisor_statement":
        return "Ask your supervisor to select the ethics Supervisor Statement confirming that they have reviewed and agree with the information provided."
    if key == "physical":
        return 'Complete the ethics confirmation consistently with the supplied risk assessment: select Yes for "Physical risk assessment form completed?" and leave No unselected.'
    if key == "low_risk":
        return "Clearly select Low Risk only in the ethics form, leaving Medium Risk unselected. If the project does not meet the Low Risk conditions, discuss the required changes with your supervisor before proceeding."
    if key == "project":
        return "Complete the risk assessment title and assessment date."
    if key == "readable":
        return "Provide a complete, legible copy of the required forms."
    if key == "admin":
        return suggested_wording(check, "issue")
    return ""


def reconstruct(bundle):
    from .release import same_attempt

    source_list = bundle.get("sources", [])
    fields = {
        "outcome": "",
        "student_corrections": "",
        "supervisor_completion": "",
        "supervisor_followup": "",
    }
    base = {
        "waivers": [],
        "decisions": [],
        "issues": [],
        "decision_gaps": [],
        "wording_gaps": [],
        "annotations": [],
        "original_feedback": [],
        "reconciliation_version": 2,
    }
    if not source_list:
        return {
            **base,
            **fields,
            "source_batch": "Independent moderator",
            "issues": ["Awaiting independent moderator feedback."],
        }
    if len(source_list) != 1 or not same_attempt(source_list[0], bundle["roster"]):
        message = (
            "Multiple assessment sources require an explicit source decision."
            if len(source_list) != 1
            else "The assessment source does not match the selected attempt; an explicit source decision is required."
        )
        return {
            **base,
            **fields,
            "source_batch": "; ".join(s["batch"] for s in source_list),
            "issues": [message],
            "decision_gaps": [message],
        }
    source = source_list[0]
    latest = latest_interpretations(source)
    working = {c["id"]: c for c in source["checks"]}
    audit = (source.get("validation_audits") or [{}])[-1]
    snapshot = {c["id"]: c for c in audit.get("automated_snapshot", [])}
    for key, value in audit.get("findings", {}).items():
        if key in BY_ID and key not in REMINDER_CHECKS and key not in working:
            working[key] = snapshot.get(key) or {
                "id": key,
                "label": BY_ID[key]["label"],
                "category": BY_ID[key]["category"],
                "status": value,
                "source": "Staff",
                "message": "Recorded staff finding.",
                "evidence": [],
                "decision": "",
            }
    decisions = [
        resolve(c, source, bundle, latest.get(c["id"]))
        for c in working.values()
        if c["id"] not in REMINDER_CHECKS
    ]
    if source.get("manual_moderation", {}).get("outcome") == "complete":
        for decision in decisions:
            # An explicitly recorded operational Pass is not overturned merely
            # because the independent technical rubric marks an entry defective.
            # Preserve that technical finding; only a later explicit agreed
            # correction judgement can replace the recorded Pass for release.
            if decision["proposed"] == "issue" and decision["origin"] not in {
                "Latest agreed staff judgement",
                "Later criterion-specific audit correction",
                "Saved moderation decision",
                "Saved moderation history",
            }:
                decision["technical_outcome"] = "issue"
                decision.update(
                    proposed="complete",
                    origin="Explicit recorded operational Pass; technical audit finding retained",
                )
    by_key = {d["criterion"]: d for d in decisions}
    missing = set(BY_ID) - REMINDER_CHECKS - FEEDBACK_EXCLUDED - set(by_key)
    gaps = [
        f"{d['label']}: {d['gap']}"
        for d in decisions
        if d["gap"] and d["criterion"] not in FEEDBACK_EXCLUDED
    ]
    for d in decisions:
        if d["criterion"] in FEEDBACK_EXCLUDED:
            d["feedback_excluded"] = True
    if source.get("conversation_decisions") and not conversation_matches(source):
        gaps.append(
            "The recovered conversation decisions refer to different source files or a different submitted attempt."
        )
    manual = source.get("manual_moderation", {})
    if manual.get("outcome_original") and not manual.get("outcome"):
        gaps.append(
            "The original manual moderation sheet has no unambiguous Pass or Fail outcome."
        )
    if missing:
        gaps.append(
            "Final judgements are absent for: "
            + ", ".join(BY_ID[k]["label"] for k in sorted(missing))
            + "."
        )
    entries = []
    wording_gaps = []
    raw_manual = source.get("manual_moderation", {}).get("feedback", "")
    missing_ethics = bool(
        re.search(
            r"\bno ethics(?:\s+(?:document|form))?(?:\s|[.!]|$)", raw_manual, re.I
        )
    )
    if missing_ethics:
        for decision in decisions:
            if decision["criterion"] in {
                "low_risk",
                "narrative",
                "declarations",
                "physical",
                "student_ethics",
                "supervisor_ethics",
                "tutor",
                "supervisor_statement",
            }:
                decision.update(
                    proposed="skipped",
                    origin="Dependent check: recorded missing ethics form",
                )
    for check in working.values():
        if check["id"] in FEEDBACK_EXCLUDED:
            continue
        d = by_key.get(check["id"])
        if not d or d["proposed"] not in {"issue", "supervisor"}:
            continue
        text = public_action(check, d, source)
        if not text:
            wording_gaps.append(
                f"{d['label']}: correction judgement is recorded; specific public wording needs completion."
            )
        audience = (
            "supervisor_followup"
            if d["proposed"] == "supervisor"
            else "supervisor_completion"
            if check["id"] in SUPERVISOR_OWNED
            else "student_corrections"
        )
        entries.append({"criterion": check["id"], "text": text, "audience": audience})
    # A recorded vague/missing-location correction owns the duplicated facilities
    # wording. Retain a real incompatibility decision (e.g. tests in a workshop).
    if by_key.get("location", {}).get("proposed") == "issue":
        facility = next((c for c in source["checks"] if c["id"] == "facilities"), {})
        reason = (latest.get("facilities") or {}).get("reason", "") or ""
        if not re.search(
            r"incompatib|not permitted|not allowed|cannot be used",
            reason + " " + facility.get("message", ""),
            re.I,
        ):
            entries = [e for e in entries if e["criterion"] != "facilities"]
    # Preserve extra written academic requirements that had no rubric checkbox.
    if re.search(r"hazards are too vague", raw_manual, re.I):
        entries.append(
            {
                "criterion": "manual_hazards",
                "audience": "student_corrections",
                "text": "Describe the hazards specifically for the activities being assessed.",
            }
        )
    if re.search(r"project cannot proceed", raw_manual, re.I):
        entries.append(
            {
                "criterion": "manual_stop",
                "audience": "student_corrections",
                "text": "Do not proceed with the project until the outstanding post-control risk-rating concerns have been resolved with your supervisor.",
            }
        )
    if re.search(r"provided template not used", raw_manual, re.I):
        entries.append(
            {
                "criterion": "manual_template",
                "audience": "student_corrections",
                "text": "Use the provided risk-assessment template, retaining the relevant assessed information.",
            }
        )
    for audience in fields.keys() - {"outcome"}:
        texts = []
        for entry in entries:
            if (
                entry["audience"] == audience
                and entry["text"]
                and entry["text"] not in texts
            ):
                texts.append(entry["text"])
        fields[audience] = "\n\n".join(texts)
    statuses = [
        d["proposed"] for d in decisions if d["criterion"] not in FEEDBACK_EXCLUDED
    ]
    fields["outcome"] = (
        "issue"
        if "issue" in statuses
        or any(
            e["audience"] in {"student_corrections", "supervisor_completion"}
            for e in entries
        )
        else ""
        if gaps
        else "supervisor"
        if "supervisor" in statuses
        else "complete"
    )
    saved = source.get("elp_feedback", {})
    annotations = []
    if saved:
        annotations.append(
            "Previously edited public wording retained where consistent with the recorded final judgements; checksum/format changes alone do not reopen academic decisions."
        )
    for d in decisions:
        if (
            d.get("interpretation")
            and d["interpretation"].get("agreed_outcome") in ROUTING
        ):
            annotations.append(
                f"{d['label']}: automatic referral retained as technical history; the recorded staff judgement was used for release."
            )
    return {
        **base,
        **fields,
        "source_batch": source["batch"],
        "issues": gaps + wording_gaps,
        "decision_gaps": gaps,
        "wording_gaps": wording_gaps,
        "annotations": annotations,
        "decisions": decisions,
        "waivers": [
            {"criterion": d["criterion"], "record": d["interpretation"]}
            for d in decisions
            if d["waived"]
        ],
        "original_feedback": [saved] if saved else [],
        "manual_moderation": source.get("manual_moderation", {}),
        "conversation_acceptance": source.get("conversation_decisions", {}).get(
            "acceptance", {}
        ),
    }
