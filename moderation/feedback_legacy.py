"""Version-one automatic wording used only to preserve prior moderator edits."""

import re

from .criteria import effective_status, ordered_checks


def legacy_suggested_wording(check, status, clean_message, INTERNAL):
    # A confirmed Issue found supplies the judgement; known completion requirements
    # can supply the correction without exposing private notes or inventing details.
    if status == "issue" and check["id"] == "location":
        return "Complete or clarify Area/Activity: identify the named room/laboratory or specific process/test procedure for the work. For computer-only work, identify the computer workstation/workspace or setup. A building name alone is not specific enough."
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


def legacy_feedback_items(item, clean_message, INTERNAL, SUPERVISOR_OWNED):
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
        wording = legacy_suggested_wording(check, status, clean_message, INTERNAL)
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
                wording,
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
            "label": check["label"],
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
    return entries
