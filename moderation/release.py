"""Release proposals from saved human evidence; never runs checking or AI."""

import copy
import hashlib
import io
import json
import re
import uuid

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from . import release_store, store
from .attempts import select_attempts, submission_timestamp
from .criteria import BY_ID, REMINDER_CHECKS, effective_status
from .feedback import INTERNAL, SUPERVISOR_OWNED, suggested_wording
from .validation import historical_adjudications
from .workflow import finding_fingerprint

OUTCOMES = {
    "complete": "Pass",
    "supervisor": "Pass — supervisor follow-up",
    "issue": "Fail — correction required",
}
PUBLIC_FIELDS = (
    "outcome",
    "student_corrections",
    "supervisor_completion",
    "supervisor_followup",
)
UNSUITABLE = re.compile(
    r"rating entry counts|\bextract(?:ion)?\b|\bparser\b|\bAI\b|manual check|moderator review|"
    r"\b(?:unverified|superseded|adjudication|audit)\b|could not|cannot compare|unable to|no readable",
    re.I,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def student_key(number):
    value = number.strip().casefold()
    if not re.fullmatch(r"w\d{7,10}", value):
        raise ValueError(
            "A reliable student number is required for every roster entry."
        )
    return value


def selected(review):
    selection = select_attempts({**review, "latest_only": True})
    if selection.warnings:
        raise ValueError(
            "Resolve ambiguous latest attempts before creating or refreshing the release roster."
        )
    numbers = [student_key(s["number"]) for s in selection.active]
    if len(numbers) != len(set(numbers)):
        raise ValueError(
            "The cohort has duplicate students or separate assessments. Resolve the roster first."
        )
    return selection.active


def attachment_hashes(review, item):
    return sorted(
        hashlib.sha256(
            (store.review_dir(review["id"]) / f["id"]).read_bytes()
        ).hexdigest()
        for f in item["files"]
    )


def item_evidence(review, item):
    return {
        "review_id": review["id"],
        "batch": review["title"],
        "submission_id": item["id"],
        "name": item["name"],
        "number": item["number"],
        "submitted": item.get("submitted", ""),
        "attempt": item.get("attempt", ""),
        "files": item["files"],
        "attachment_hashes": attachment_hashes(review, item),
        "checks": item.get("checks", []),
        "validation_audits": item.get("validation_audits", []),
        "audit_adjudications": item.get("audit_adjudications", []),
        "elp_feedback": item.get("elp_feedback", {}),
        "feedback_history": item.get("feedback_history", []),
        "ai_state": item.get("ai", {}).get("state"),
    }


def evidence_bundle(config):
    """Read originals directly: jobs.snapshot can refresh old checking results."""
    cohort = store.load(config["cohort_review_id"])
    roster = selected(cohort)
    if len(roster) != config["expected_count"]:
        raise ValueError(
            f"Expected {config['expected_count']} unique selected students; found {len(roster)}."
        )
    sources, supplemental = {}, {}
    for destination, identifiers in [
        (sources, config["source_review_ids"]),
        (supplemental, config.get("supplemental_review_ids", [])),
    ]:
        for review_id in identifiers:
            review = store.load(review_id)
            historical = historical_adjudications(review)
            for item in select_attempts(review).active:
                if destination is supplemental and not any(
                    human_action(c) for c in item.get("checks", [])
                ):
                    continue
                number = student_key(item["number"])
                evidence = item_evidence(review, item)
                evidence["historical_adjudications"] = [
                    x for x in historical if x["student_number"].casefold() == number
                ]
                destination.setdefault(number, []).append(evidence)
    result = {}
    for item in roster:
        key = student_key(item["number"])
        canonical = item_evidence(cohort, item)
        # The cohort supplies identity/attempt only; its raw automated conclusions
        # must not replace the independently moderated source decisions.
        canonical = {
            k: canonical[k]
            for k in (
                "review_id",
                "batch",
                "submission_id",
                "name",
                "number",
                "submitted",
                "attempt",
                "files",
                "attachment_hashes",
            )
        }
        result[key] = {
            "roster": canonical,
            "sources": sources.get(key, []),
            "supplemental": supplemental.get(key, []),
        }
    outside = sorted(set(sources) - set(result))
    if outside:
        raise ValueError(
            "An assessment source contains students outside the selected cohort. Resolve the source selection first."
        )
    return result


def same_attempt(source, roster):
    return (
        source["attachment_hashes"] == roster["attachment_hashes"]
        and submission_timestamp(source) is not None
        and submission_timestamp(source) == submission_timestamp(roster)
    )


def human_action(check):
    return bool(check.get("decision")) or bool(
        check.get("reviewed_at")
        and check.get("reviewed_fingerprint") == finding_fingerprint(check)
    )


def adjudicated_status(record):
    """Only explicit recorded outcomes; never infer an outcome from a classification."""
    if record.get("agreed_outcome") in {
        "complete",
        "issue",
        "supervisor",
        "review",
        "skipped",
    }:
        return record["agreed_outcome"]
    reason = record.get("reason", "") or ""
    marker = r"Staff-agreed (?:final outcome remains|outcome:|prerequisite policy:)|Agreed outcome:"
    if (record.get("criterion") or record.get("check")) == "facilities":
        marker += r"|Agreed facilities outcome:"
    match = re.search(
        r"(?:^|[.!?]\s+)(?:" + marker + r")\s*"
        r"(Issue found|Supervisor check|Skipped|Pass|Needs moderator review)\b",
        reason,
        re.I,
    )
    if match:
        return {
            "issue found": "issue",
            "supervisor check": "supervisor",
            "skipped": "skipped",
            "pass": "complete",
            "needs moderator review": "review",
        }[match[1].casefold()]
    return None


def recorded_waiver(record):
    # These are explicit staff classifications in the historical decision log,
    # not a heuristic over arbitrary free-text notes or an inferred new waiver.
    return bool(
        re.search(
            r"would waive resubmission|cleanup would be waived",
            record.get("classification", ""),
            re.I,
        )
    )


def safe_wording(check, status):
    if check["id"] == "location" and status == "issue":
        return "Identify the approved work area or activity clearly in the Area/Activity field."
    if check["id"] == "tutor" and status == "issue":
        return "Ask your supervisor to complete the outstanding tutor checklist items in the ethics form."
    if check["id"] == "hs_relevance" and status == "issue":
        return "Remove project/data-management consequences from the hazard list, retaining the relevant health-and-safety hazards and consequences."
    # A human confirmation of the outcome does not make raw AI prose suitable
    # for publication. Retain separately saved public wording instead, if any.
    if check.get("source") == "AI":
        return ""
    if effective_status(check) != status:
        return ""
    text = suggested_wording(check, status)
    return "" if INTERNAL.search(text) or UNSUITABLE.search(text) else text


def propose(bundle):
    sources = bundle["sources"]
    issues, waivers, entries, decisions = [], [], [], []
    fields = {
        "outcome": "",
        "student_corrections": "",
        "supervisor_completion": "",
        "supervisor_followup": "",
    }
    if not sources:
        return {
            **fields,
            "issues": ["Awaiting independent moderator feedback."],
            "waivers": [],
            "decisions": [],
            "source_batch": "Independent moderator",
            "original_feedback": [],
        }
    if len(sources) != 1:
        return {
            **fields,
            "issues": [
                "Multiple assessment sources require an explicit choice; no judgements were combined."
            ],
            "waivers": [],
            "decisions": [],
            "source_batch": "; ".join(s["batch"] for s in sources),
            "original_feedback": [
                s["elp_feedback"] for s in sources if s["elp_feedback"]
            ],
        }
    source = sources[0]
    if not same_attempt(source, bundle["roster"]):
        return {
            **fields,
            "issues": [
                "The assessment source does not match the selected cohort attempt. Resolve before release."
            ],
            "waivers": [],
            "decisions": [],
            "source_batch": source["batch"],
            "original_feedback": [],
        }
    audit = (source["validation_audits"] or [{}])[-1]
    latest = {}
    for record in source["historical_adjudications"]:
        latest[record["check"]] = record
    for record in source["audit_adjudications"]:
        if record.get("audit_at") == audit.get("at"):
            latest[record["criterion"]] = record
    saved = source["elp_feedback"]
    if saved:
        issues.append(
            "Previously generated feedback may be stale. Its wording is retained below for explicit confirmation."
        )
    unconfirmed = []
    for check in source["checks"]:
        key = check["id"]
        if key in REMINDER_CHECKS:
            continue
        status = effective_status(check)
        origin = "Unconfirmed automated finding"
        known = False
        action_statuses = []
        for candidate in [source] + bundle["supplemental"]:
            if not same_attempt(candidate, bundle["roster"]):
                continue
            other = next((c for c in candidate["checks"] if c["id"] == key), None)
            if other and human_action(other):
                action_statuses.append(effective_status(other))
        if len(set(action_statuses)) > 1:
            issues.append(
                f"{check['label']}: contradictory saved moderation decisions; no automatic merge."
            )
            status = "review"
        elif action_statuses:
            status, known, origin = (
                action_statuses[0],
                True,
                "Saved moderation decision",
            )
            if key in latest:
                agreed = (
                    "complete"
                    if recorded_waiver(latest[key])
                    else adjudicated_status(latest[key])
                )
                if agreed and agreed != status:
                    issues.append(
                        f"{check['label']}: the agreed interpretation and saved moderation disagree. Resolve which is final."
                    )
                    status, origin = (
                        agreed,
                        "Latest agreed interpretation — conflicting moderation retained for resolution",
                    )
        elif key in latest:
            record = latest[key]
            if recorded_waiver(record):
                waivers.append({"criterion": key, "record": record})
                if record.get("agreed_outcome") in {"issue", "complete"}:
                    status, known, origin = "complete", True, "Recorded staff waiver"
                else:
                    status = "review"
                    issues.append(
                        f"{check['label']}: the recorded cleanup waiver does not establish the final criterion outcome. Confirm it explicitly."
                    )
            else:
                agreed = adjudicated_status(record)
                if agreed:
                    status, known, origin = (
                        agreed,
                        True,
                        "Explicit agreed interpretation",
                    )
                else:
                    status = "review"
                    issues.append(
                        f"{check['label']}: the agreed interpretation has no unambiguous final release outcome."
                    )
        elif key in audit.get("findings", {}):
            status, known, origin = (
                audit["findings"][key],
                True,
                "Independent audit proposal (not final moderation)",
            )
            if (
                status in OUTCOMES
                and effective_status(check) in OUTCOMES
                and status != effective_status(check)
            ):
                issues.append(
                    f"{check['label']}: the audit and automated outcome differ without a recorded agreed interpretation."
                )
        elif status in {"review", "moderator", "unable", "issue", "supervisor"}:
            unconfirmed.append(check["label"])
        if status not in {"complete", "issue", "supervisor", "skipped"}:
            issues.append(f"{check['label']}: a final judgement is required.")
        decisions.append(
            {
                "criterion": key,
                "label": check["label"],
                "proposed": status,
                "origin": origin,
            }
        )
        if status not in {"issue", "supervisor"}:
            continue
        wording = saved.get("wording", {}).get(key, "")
        if not wording:
            wording = safe_wording(check, status) if known else ""
        if not wording:
            issues.append(
                f"{check['label']}: enter a specific student-facing action or record a waiver."
            )
        audience = (
            "supervisor_followup"
            if status == "supervisor"
            else "supervisor_completion"
            if key in SUPERVISOR_OWNED
            else "student_corrections"
        )
        entries.append(
            {"criterion": key, "text": wording, "audience": audience, "check": check}
        )
    if unconfirmed:
        issues.append(
            "Saved operational confirmation is missing for: "
            + ", ".join(unconfirmed)
            + ". Reuse existing judgements; do not rerun AI."
        )
    # Consolidate only wording about the SAME absent/vague location. Never hide
    # a distinct incompatibility finding just because a location issue exists.
    location = next((e for e in entries if e["criterion"] == "location"), None)
    facilities = next((e for e in entries if e["criterion"] == "facilities"), None)
    if (
        location
        and facilities
        and re.search(
            r"not specific|generic|does not clearly identify|insufficient|vague",
            facilities["check"].get("message", ""),
            re.I,
        )
        and not re.search(
            r"incompatib|not permitted|cannot be|not allowed",
            facilities["check"].get("message", ""),
            re.I,
        )
    ):
        entries.remove(facilities)
        issues = [
            x
            for x in issues
            if not x.startswith(facilities["check"]["label"] + ": enter")
        ]
    for audience in (
        "student_corrections",
        "supervisor_completion",
        "supervisor_followup",
    ):
        texts = []
        for entry in entries:
            if entry["audience"] != audience or not entry["text"]:
                continue
            label = BY_ID[entry["criterion"]]["label"]
            text = label + ": " + entry["text"]
            if text not in texts:
                texts.append(text)
        fields[audience] = "\n\n".join(texts)
    statuses = [d["proposed"] for d in decisions]
    missing = set(BY_ID) - REMINDER_CHECKS - {c["id"] for c in source["checks"]}
    if missing:
        issues.append(
            "The source has missing criteria; confirm the complete final outcome rather than assuming a Pass."
        )
        statuses.append("review")
    fields["outcome"] = (
        "issue"
        if "issue" in statuses
        else ""
        if any(x not in {"complete", "supervisor", "skipped"} for x in statuses)
        else "supervisor"
        if "supervisor" in statuses
        else "complete"
    )
    return {
        **fields,
        "issues": list(dict.fromkeys(issues)),
        "waivers": waivers,
        "decisions": decisions,
        "source_batch": source["batch"],
        "original_feedback": [saved] if saved else [],
    }


def new_record(number, bundle):
    proposal = propose(bundle)
    return {
        "number": number,
        "name": bundle["roster"]["name"],
        "source_batch": proposal["source_batch"],
        "attempt": bundle["roster"]["submitted"],
        **{key: proposal[key] for key in PUBLIC_FIELDS},
        "moderator": "",
        "original_moderator_feedback": "",
        "resolution": "",
        "status": "proposed" if bundle["sources"] else "awaiting_feedback",
        "final_text": "",
        "finalised_at": "",
        "source_fingerprint": digest(bundle),
        "source_evidence": bundle,
        "proposal": proposal,
        "history": [],
    }


def create(cohort_id, source_ids, supplemental_ids=(), expected_count=106):
    if cohort_id in source_ids or len(source_ids) != len(set(source_ids)):
        raise ValueError(
            "Choose distinct assessment sources separate from the cohort roster."
        )
    config = {
        "cohort_review_id": str(cohort_id),
        "source_review_ids": list(source_ids),
        "supplemental_review_ids": list(supplemental_ids),
        "expected_count": expected_count,
    }
    bundles = evidence_bundle(config)
    with store.LOCK:
        if release_store.load() is not None:
            raise ValueError(
                "A release register already exists; use Refresh sources instead."
            )
        data = {
            "schema": 1,
            "id": uuid.uuid4().hex,
            "revision": uuid.uuid4().hex,
            "created": store.now(),
            "updated": store.now(),
            **config,
            "records": {
                key: new_record(key, bundle) for key, bundle in bundles.items()
            },
            "history": [],
        }
        release_store.save(data)
        return data


def source_state(register):
    bundles = evidence_bundle(register)
    if set(bundles) != set(register["records"]):
        raise ValueError(
            "The cohort roster changed. Resolve the roster before continuing release."
        )
    return bundles


def release_valid(record, bundle):
    return bool(
        record["status"] == "finalised"
        and record.get("final_text")
        and record["source_fingerprint"] == digest(bundle)
    )


def paragraph_actions(value):
    # One action per blank-line-separated paragraph; embedded bullet lines stay
    # with their action, allowing the existing style of tutor-checklist feedback.
    return [
        re.sub(r"^\d+[.)]\s*", "", text.strip())
        for text in re.split(r"\n\s*\n", value.strip())
        if text.strip()
    ]


def format_feedback(fields):
    outcome = fields.get("outcome")
    if outcome not in OUTCOMES:
        return "Select a final outcome to preview student-facing feedback."
    lines = ["Result: " + OUTCOMES[outcome], ""]
    if outcome == "issue":
        lines += [
            "Address every required correction below, then resubmit the corrected forms.",
            "",
        ]
    else:
        lines += [
            "Your submission has passed the completion and consistency review. This does not constitute approval of the adequacy of the safety controls.",
            "",
        ]
    for heading, key in [
        ("Student corrections", "student_corrections"),
        ("Supervisor completion required before resubmission", "supervisor_completion"),
        ("Supervisor follow-up (non-blocking)", "supervisor_followup"),
    ]:
        actions = paragraph_actions(fields.get(key, ""))
        if not actions:
            continue
        lines.append(heading)
        for index, action in enumerate(actions, 1):
            lines.append(f"{index}. " + action.replace("\n", "\n   "))
        lines.append("")
    return "\n".join(lines).strip()


def validate_final(fields):
    outcome = fields.get("outcome")
    if outcome not in OUTCOMES:
        raise ValueError(
            "Choose an explicit final outcome; an outcome is never inferred from free text."
        )
    required = bool(
        fields["student_corrections"].strip() or fields["supervisor_completion"].strip()
    )
    followup = bool(fields["supervisor_followup"].strip())
    if outcome == "issue" and not required:
        raise ValueError(
            "Fail requires a specific student correction or required supervisor completion."
        )
    if outcome != "issue" and required:
        raise ValueError(
            "A Pass cannot contain required corrections. Resolve or explicitly waive them first."
        )
    if outcome == "supervisor" and not followup:
        raise ValueError(
            "Pass — supervisor follow-up requires a specific non-blocking supervisor action."
        )
    if outcome == "complete" and followup:
        raise ValueError(
            "Select Pass — supervisor follow-up when non-blocking follow-up is included."
        )
    if not fields.get("moderator", "").strip():
        raise ValueError(
            "Record the moderator responsible for finalising this feedback."
        )
    for key in PUBLIC_FIELDS[1:]:
        if INTERNAL.search(fields[key]) or UNSUITABLE.search(fields[key]):
            raise ValueError(
                "Replace internal checking, AI or parser terminology with an actionable public instruction."
            )
    if len(format_feedback(fields)) > 32767:
        raise ValueError(
            "Shorten the feedback to fit an Excel feedback cell (32,767 characters)."
        )


def save_record(
    register_revision,
    number,
    fields,
    *,
    finalise=False,
    confirm=False,
    replace=False,
    resolve=False,
    source_token="",
):
    number = student_key(number)

    def change(data):
        if number not in data["records"]:
            raise ValueError("This student is not in the selected cohort roster.")
        record = data["records"][number]
        bundle = source_state(data)[number]
        current_token = digest(bundle)
        if source_token != current_token:
            raise ValueError(
                "Source evidence changed while the editor was open. Reload and review it."
            )
        if record["status"] == "finalised" and not replace:
            raise ValueError(
                "Explicitly confirm replacement of the existing finalised record before editing it."
            )
        if finalise:
            if not confirm:
                raise ValueError(
                    "Explicitly confirm the final outcome and student-facing feedback."
                )
            validate_final(fields)
            needs_resolution = bool(
                any(
                    x != "Awaiting independent moderator feedback."
                    for x in record["proposal"]["issues"]
                )
                or record["source_fingerprint"] != current_token
            )
            if needs_resolution and not (
                resolve and fields.get("resolution", "").strip()
            ):
                raise ValueError(
                    "Review the unresolved source decisions and record how they were resolved or waived."
                )
        previous = copy.deepcopy(
            {key: value for key, value in record.items() if key != "history"}
        )
        record.update(
            {
                key: fields.get(key, "").strip()
                for key in (
                    *PUBLIC_FIELDS,
                    "moderator",
                    "original_moderator_feedback",
                    "resolution",
                )
            }
        )
        record.update(
            status="finalised" if finalise else "draft",
            final_text=format_feedback(fields) if finalise else "",
            finalised_at=store.now() if finalise else "",
        )
        # A draft does not approve refreshed evidence; preserve the old baseline
        # until the moderator explicitly finalises against the current sources.
        if finalise:
            record.update(
                source_fingerprint=current_token,
                source_evidence=bundle,
                name=bundle["roster"]["name"],
                attempt=bundle["roster"]["submitted"],
            )
        record["history"].append(
            {
                "at": store.now(),
                "action": "finalise" if finalise else "save_draft",
                "moderator": fields.get("moderator", ""),
                "previous": previous,
            }
        )

    return release_store.update(register_revision, change)


def refresh(revision):
    def change(data):
        bundles = source_state(data)
        for number, record in data["records"].items():
            bundle = bundles[number]
            # Preserve every existing draft and final text. Surface the fresh
            # proposal as reference only, never replace staff-entered content.
            record["refreshed_proposal"] = propose(bundle)
        data["history"].append({"at": store.now(), "action": "refresh_sources"})

    return release_store.update(revision, change)


def export_xlsx(register, bundles, finalised_only=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Student feedback"
    sheet.append(
        [
            "Student number",
            "Student name",
            "Final outcome for eLP",
            "Final student-facing feedback",
            "Finalisation status",
        ]
    )
    for number, record in sorted(register["records"].items()):
        valid = release_valid(record, bundles[number])
        if finalised_only and not valid:
            continue
        status = (
            "Finalised"
            if valid
            else "Source changed — review required"
            if record["status"] == "finalised"
            else "Not finalised"
        )
        values = [
            number,
            record["name"],
            ("Fail" if record["outcome"] == "issue" else "Pass") if valid else "",
            record["final_text"] if valid else "",
            status,
        ]
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            # Force text: moderator-entered content must never become a formula.
            cell.data_type = "s"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="173D38")
    for column, width in [("A", 20), ("B", 30), ("C", 24), ("D", 100), ("E", 34)]:
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
