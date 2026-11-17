"""Deterministic eLP feedback from completed moderation, never from internal notes."""

import hashlib
import json
import re
import uuid

from django import forms

from .ai import ai_work_counts
from .attempts import select_attempts
from .criteria import (
    CRITERIA,
    OVERALL_LABELS,
    REMINDER_CHECKS,
    effective_status,
    ordered_checks,
    overall,
)
from .workflow import review_progress

SUPERVISOR_OWNED = {
    "supervisor_ra",
    "supervisor_ethics",
    "supervisor_statement",
    "tutor",
}
INTERNAL = re.compile(
    r"PDF evidence|could not be read|could not be verified|unverified|AI conclusion|AI assessment|AI comparison|Inspect the original|Moderator to inspect|processing (?:failed|stopped|pending)|\bAPI\b",
    re.I,
)


def feedback_readiness(review, item):
    if item["id"] not in {s["id"] for s in select_attempts(review).active}:
        return False, "This earlier attempt is excluded from the current review."
    if review["state"] in {"queued", "running"} or item["state"] != "done":
        return False, "Wait for processing to finish before generating feedback."
    if not {key for key, _, _ in CRITERIA if key not in REMINDER_CHECKS}.issubset(
        {c["id"] for c in item["checks"]}
    ):
        return False, "Complete the missing checks before generating feedback."
    progress = [review_progress(c, review) for c in item["checks"]]
    remaining = sum(p["needs_review"] for p in progress)
    if remaining:
        return (
            False,
            f"Review the remaining {remaining} flagged check(s) before generating feedback.",
        )
    unresolved = sum(p["review_unresolved"] for p in progress)
    if unresolved:
        return (
            False,
            f"Resolve {unresolved} reviewed but unresolved check(s) to Complete, Issue found or Supervisor check before generating feedback.",
        )
    if ai_work_counts([item], review["use_ai"])[0]:
        return False, "Run the outstanding AI checks before generating feedback."
    if overall(item["checks"]) not in {"complete", "issue", "supervisor"}:
        return (
            False,
            "A final Pass, Supervisor check or Issue found outcome is required before generating feedback.",
        )
    return True, "Moderation complete. Feedback can now be generated."


def feedback_signature(item):
    records = [
        {
            key: c.get(key)
            for key in (
                "id",
                "status",
                "source",
                "message",
                "evidence",
                "decision",
                "decided_at",
                "reviewed_at",
                "reviewed_fingerprint",
                "blocked_by",
                "supporting_assessments",
            )
            if key != "supporting_assessments" or c.get("supporting_assessments")
        }
        for c in ordered_checks(item["checks"])
    ]
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def clean_message(message):
    message = message.split(" AI observation:", 1)[0]
    message = re.split(r"\s+Compared \d+ initial/final score pairs", message)[0]
    return " ".join(message.split()).strip()


def fallback_wording(check, status):
    if (
        status == "supervisor"
        and check["id"] == "specialists"
        and check.get("supporting_assessments")
    ):
        return (
            "Locate and review the supporting specialist assessments for "
            + joined(check["supporting_assessments"])
            + "."
        )
    # A confirmed Issue found supplies the judgement; known completion requirements
    # can supply the correction without exposing private notes or inventing details.
    if status == "issue" and check["id"] == "location":
        return "Complete or clarify Area/Activity or the dedicated Location field in each RA section. Identify the named room/laboratory or specific process/test procedure for physical work. A clear computer-based activity description is sufficient for computer-work sections. A building name alone is not specific enough for physical work."
    if (
        status == "issue"
        and check["id"] == "ethics_details"
        and check.get("missing_form")
    ):
        return "Upload the completed ethics form, including the required declarations and student/supervisor sign-offs."
    if status == "issue" and check["id"] == "low_risk":
        return "Retain or restore the Low Risk and Medium Risk selection boxes and clearly select Low Risk only, leaving Medium Risk unselected. Do not delete the options. If your project does not meet the Low Risk conditions, discuss the required changes with your supervisor before proceeding."
    # An override may identify a new issue without stating what needs correction.
    # Require explicit student-facing wording instead of reusing internal comments.
    if check["status"] != status:
        return ""
    message = clean_message(check["message"])
    if INTERNAL.search(message):
        return ""
    if status == "supervisor" and check["id"] == "specialists":
        match = re.search(r"supporting assessments:\s*([^.]+)\.", message, re.I)
        if match:
            return (
                "Locate and review the supporting specialist assessments for "
                + match[1]
                + "."
            )
    if status == "issue":
        if check["id"] in {
            "student_ra",
            "student_ethics",
            "supervisor_ra",
            "supervisor_ethics",
        }:
            missing = re.search(r"Missing:\s*([^.]*)", message, re.I)
            if missing:
                owner = (
                    "Ask your supervisor to add"
                    if check["id"].startswith("supervisor")
                    else "Add"
                )
                section = (
                    "risk assessment" if check["id"].endswith("ra") else "ethics form"
                )
                return f"{owner} the missing {missing[1]} in the {section} sign-off section."
        if check["id"] == "identity":
            return "Enter your own full name in the risk assessment Assessor field; the student undertaking the assessment must be recorded as assessor."
    return message


FEEDBACK_FORMAT_VERSION = 2


def joined(values):
    values = list(values)
    return (
        values[0]
        if len(values) == 1
        else ", ".join(values[:-1]) + " and " + values[-1]
        if values
        else ""
    )


def rating_wording(check):
    groups = {}
    for match in re.finditer(
        r"Row (\d+): enter a numeric value for ([^.]+)\.", check["message"]
    ):
        groups.setdefault(match[2], []).append(match[1])
    if not groups:
        return ""
    actions = []
    for field, rows in groups.items():
        place = ("row " if len(rows) == 1 else "rows ") + joined(rows)
        if field == "Final Result (post-control score)":
            actions.append(
                f"Enter the post-control Final Result score in risk {place}."
            )
        else:
            actions.append(f"Enter numeric values for {field} in risk {place}.")
    if any("Final Result" in field for field in groups):
        actions.append(
            "This is the risk remaining after the listed controls. A score alone is sufficient; showing the multiplication is optional."
        )
    mismatch = re.search(
        r"Rating entry counts do not match\.(.*?)(?=Multiple or unclear|$)",
        check["message"],
    )
    if mismatch:
        actions.append("Rating entry counts do not match. " + mismatch[1].strip())
    unclear = re.search(
        r"Multiple or unclear rating entries.*?in rows: ([\d, ]+)", check["message"]
    )
    if unclear:
        rows = re.findall(r"\d+", unclear[1])
        actions.append(
            "In risk "
            + ("row " if len(rows) == 1 else "rows ")
            + joined(rows)
            + ", show each severity, likelihood, initial score and final score clearly, with one matching set per entry."
        )
    return " ".join(actions)


def tutor_wording(check, item):
    from .checks import selection

    labels = (
        "Ethics form complete",
        "Ethical concerns acknowledged",
        "Research tool(s) checked",
    )
    missing = []
    evidence = check.get("evidence", [])
    for label in labels:
        normal = re.sub(r"[^a-z]", "", label.casefold())
        chosen = None
        for index, extract in enumerate(evidence):
            if normal not in re.sub(r"[^a-z]", "", extract["text"].casefold()):
                continue
            for candidate in evidence[index : index + 2]:
                paragraph = {"text": candidate["text"], "states": []}
                ref = re.fullmatch(
                    r"Document (\d+), paragraph (\d+)", candidate.get("location", "")
                )
                if ref and item:
                    try:
                        paragraph = item["documents"][int(ref[1]) - 1]["paragraphs"][
                            int(ref[2]) - 1
                        ]
                    except (IndexError, KeyError):
                        pass
                chosen = selection(paragraph)
                if chosen is not None:
                    break
            break
        if chosen is not True:
            missing.append(label)
    if not missing:
        missing = list(labels)
    return (
        "Review and confirm:\n"
        + "\n".join("- " + label for label in missing)
        + "\nSelect the relevant boxes after checking each point."
    )


def suggested_wording(check, status, item=None):
    key = check["id"]
    if status == "issue":
        if key == "location":
            return fallback_wording(check, status)
        if key == "admin":
            questions = {
                "1": "Can this risk assessment be shared and labelled Generic to the University (is the activity also carried out in another faculty or department)?",
                "2": "Does a related risk assessment need review or updating following this assessment?",
            }
            match = re.search(
                r"question\(s\) ([\d, ]+) unanswered", check["message"], re.I
            )
            required = re.findall(r"\d+", match[1]) if match else ["1", "2"]
            return (
                "Answer the following at the end of the risk assessment:\n"
                + "\n".join("- " + questions[n] for n in required if n in questions)
            )
        if key == "ratings":
            wording = rating_wording(check)
            if wording:
                return wording
        if key == "specialists":
            match = re.search(
                r"Unanswered specialist questions: ([^.]+)\.", check["message"]
            )
            if match:
                return (
                    "Answer each category: "
                    + match[1]
                    + ". Add an assessment reference only where one is applicable."
                )
        if key == "physical":
            return 'Once the risk assessment is complete, select Yes for "Physical risk assessment form completed?" in the ethics form and leave No unselected.'
        if key == "tutor":
            return tutor_wording(check, item)
        if key == "supervisor_statement":
            return "Select the declaration in the ethics form's Supervisor Statement confirming that the supervisor has reviewed the form and agrees with the information provided."
        if key in {
            "student_ra",
            "student_ethics",
            "supervisor_ra",
            "supervisor_ethics",
        }:
            missing = re.search(r"Missing:\s*([^.]*)", check["message"], re.I)
            if missing:
                fields = [v.strip() for v in missing[1].split(",")]
                fields = [
                    "staff job title"
                    if v == "job title" and key.startswith("supervisor")
                    else v
                    for v in fields
                ]
                return "Add the missing " + joined(fields) + "."
    return fallback_wording(check, status)


def feedback_items(item):
    entries = []
    issues = {c["id"]: c for c in item["checks"] if effective_status(c) == "issue"}
    for check in ordered_checks(item["checks"]):
        status = effective_status(check)
        if status not in {"issue", "supervisor"}:
            continue
        if (
            check["id"] == "risk_reduction"
            and "ratings" in issues
            and "Final ratings must be lower" not in check["message"]
        ):
            # The rating-completion finding already explains mismatched entries.
            if "Rating entry counts do not match" in check["message"]:
                continue
        wording = suggested_wording(check, status, item)
        if check["id"] == "risk_reduction" and wording:
            wording = re.split(
                r"Rating entry counts do not match|Comparison skipped", wording
            )[0].strip()
            if wording:
                wording += " Review the scores and controls with your supervisor; the final score must reflect the risk remaining after controls."
        # A combined specialist finding may contain both a student omission and a supervisor task.
        specialist_followup = ""
        if check["id"] == "specialists" and wording and status == "issue":
            match = re.search(
                r"Supervisor to locate and review supporting assessments: ([^.]+)\.",
                check["message"],
            )
            if match:
                specialist_followup = (
                    "Locate and review the supporting specialist assessments for "
                    + match[1]
                    + "."
                )
                wording = (
                    wording.replace(match[0], "")
                    .replace(
                        "A Yes answer identifies follow-up, not a student completion error.",
                        "",
                    )
                    .strip()
                )
        audience = (
            "supervisor"
            if status == "supervisor" or check["id"] in SUPERVISOR_OWNED
            else "student"
        )
        entry = {
            "key": check["id"],
            "label": {
                "location": "Area/Activity",
                "ratings": "Risk ratings",
                "admin": "Risk assessment questions",
                "physical": "Ethics risk-assessment confirmation",
                "supervisor_ra": "Risk assessment",
                "supervisor_ethics": "Ethics form",
                "student_ra": "Your risk assessment sign-off",
                "student_ethics": "Your ethics sign-off",
                "supervisor_statement": "Supervisor declaration",
            }.get(check["id"], check["label"]),
            "audience": audience,
            "text": wording,
            "correction_required": status == "issue",
        }
        # Merge rating completion and score reduction under one student action.
        previous = next(
            (
                e
                for e in entries
                if e["key"] == "ratings" and e["audience"] == "student"
            ),
            None,
        )
        if check["id"] == "risk_reduction" and previous and audience == "student":
            previous["label"] = "Risk ratings"
            previous["text"] = (
                (previous["text"] + " " + wording).strip()
                if previous["text"] and wording
                else ""
            )
        elif not any(
            e["audience"] == audience
            and e["label"] == entry["label"]
            and e["text"] == wording
            for e in entries
        ):
            entries.append(entry)
        if specialist_followup:
            entries.append(
                {
                    "key": "specialists_followup",
                    "label": "Specialist assessments",
                    "audience": "supervisor",
                    "text": specialist_followup,
                    "correction_required": False,
                }
            )
    saved = item.get("elp_feedback", {})
    if saved.get("format_version") == 1 and saved.get(
        "signature"
    ) == feedback_signature(item):
        from .feedback_legacy import legacy_feedback_items

        previous_defaults = {
            e["key"]: e["text"]
            for e in legacy_feedback_items(
                item, clean_message, INTERNAL, SUPERVISOR_OWNED
            )
        }
        for entry in entries:
            previous = saved.get("wording", {}).get(entry["key"])
            if previous and previous != previous_defaults.get(entry["key"]):
                entry["text"] = previous
    return entries


class FeedbackWordingForm(forms.Form):
    def __init__(self, entries, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for entry in entries:
            self.fields[entry["key"]] = forms.CharField(
                label=f"{entry['label']} — {'student correction' if entry['audience'] == 'student' else 'supervisor follow-up'}",
                initial=entry["text"],
                required=True,
                max_length=5000,
                help_text="Use specific feedback for the student/supervisor. Internal moderation notes are not copied. To remove a finding, change its moderation outcome first.",
                widget=forms.Textarea(attrs={"rows": 4}),
            )


def render_feedback(item, entries, wording):
    outcome = overall(item["checks"])
    lines = ["Result: " + OVERALL_LABELS[outcome], ""]
    if outcome == "issue":
        lines += [
            "Address every correction below, then resubmit the corrected forms.",
            "",
        ]
    else:
        lines += [
            "Your risk assessment and ethics submission has passed the completion and consistency review.",
            "",
        ]
    groups = (
        ("Student corrections", [e for e in entries if e["audience"] == "student"]),
        (
            "Supervisor completion required before resubmission",
            [
                e
                for e in entries
                if e["audience"] == "supervisor" and e["correction_required"]
            ],
        ),
        (
            "Supervisor follow-up",
            [
                e
                for e in entries
                if e["audience"] == "supervisor" and not e["correction_required"]
            ],
        ),
    )
    for heading, selected in groups:
        if not selected:
            continue
        lines.append(heading)
        if heading == "Student corrections" and any(
            e["key"] in {"admin", "specialists"} for e in selected
        ):
            lines.append(
                "For Yes/No questions, give one clear answer in the answer field. Leaving Y/N unchanged or entering the answer in a reference field does not answer the question."
            )
        number = 0
        signoffs = [
            e for e in selected if e["key"] in {"supervisor_ra", "supervisor_ethics"}
        ]
        for entry in selected:
            if entry in signoffs and len(signoffs) > 1:
                if entry is not signoffs[0]:
                    continue
                number += 1
                lines.append(f"{number}. Supervisor sign-off:")
                for signoff in signoffs:
                    lines.append(
                        f"   - {signoff['label']}: {wording[signoff['key']].strip()}"
                    )
                continue
            number += 1
            body = wording[entry["key"]].strip().replace("\n", "\n   ")
            lines.append(f"{number}. {entry['label']}: {body}")
        lines.append("")
    return "\n".join(lines).strip()


def new_feedback_record(item, wording, generated_at):
    entries = feedback_items(item)
    return {
        "id": uuid.uuid4().hex,
        "format_version": FEEDBACK_FORMAT_VERSION,
        "signature": feedback_signature(item),
        "generated_at": generated_at,
        "result": OVERALL_LABELS[overall(item["checks"])],
        "text": render_feedback(item, entries, wording),
        "wording": wording,
    }


def current_feedback(review, item):
    saved = item.get("elp_feedback", {})
    return bool(
        feedback_readiness(review, item)[0]
        and saved.get("signature") == feedback_signature(item)
        and saved.get("format_version") == FEEDBACK_FORMAT_VERSION
        and saved.get("id")
    )


def bulk_feedback_state(review):
    active = {s["id"] for s in select_attempts(review).active}
    generated, waiting, excluded, earlier = [], [], [], []
    for item in sorted(
        review["submissions"],
        key=lambda s: (s["name"].casefold(), s["number"], s["submitted"], s["id"]),
    ):
        if item["id"] not in active:
            earlier.append(item)
            continue
        ready, reason = feedback_readiness(review, item)
        if not ready:
            excluded.append(
                {"submission": item, "reason": reason, "wording_needed": False}
            )
        elif current_feedback(review, item):
            generated.append({"submission": item, "feedback": item["elp_feedback"]})
        else:
            entries = feedback_items(item)
            form = FeedbackWordingForm(entries, {e["key"]: e["text"] for e in entries})
            if not form.is_valid():
                excluded.append(
                    {
                        "submission": item,
                        "reason": "Moderation is complete, but specific student/supervisor feedback wording is required.",
                        "wording_needed": True,
                    }
                )
            else:
                waiting.append(item)
    token = hashlib.sha256(
        json.dumps(
            {
                "active": sorted(active),
                "records": [
                    (
                        row["submission"]["id"],
                        row["feedback"]["id"],
                        row["feedback"]["signature"],
                    )
                    for row in generated
                ],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "generated": generated,
        "waiting": waiting,
        "excluded": excluded,
        "earlier": earlier,
        "batch_version": token,
        "selected_count": len(active),
    }


def generate_bulk_feedback(review, generated_at):
    """Generate eligible feedback only, keeping current edited wording untouched."""
    created = []
    for item in bulk_feedback_state(review)["waiting"]:
        entries = feedback_items(item)
        form = FeedbackWordingForm(entries, {e["key"]: e["text"] for e in entries})
        if not form.is_valid():
            continue
        record = new_feedback_record(item, form.cleaned_data, generated_at)
        item["elp_feedback"] = record
        item.setdefault("feedback_history", []).append(record)
        created.append(item["id"])
    if created:
        review.setdefault("bulk_feedback_history", []).append(
            {"generated_at": generated_at, "submissions": created}
        )
    return created
