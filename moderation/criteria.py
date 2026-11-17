"""The moderation checklist, shared by checks, UI and exports."""

CRITERIA = [
    ("readable", "Document readable", "RA information"),
    ("identity", "Assessor is student", "RA information"),
    ("project", "Project details", "RA information"),
    ("location", "Specific area or activity", "RA information"),
    ("facilities", "Activities–facilities consistency", "Risk assessment"),
    ("risk_table", "Risk table completed", "Risk assessment"),
    ("example", "Example row removed", "Risk assessment"),
    ("hs_relevance", "H&S hazards only", "Risk assessment"),
    ("ratings", "Risk ratings completed", "Risk assessment"),
    ("risk_reduction", "Controls reduce risk rating", "Risk assessment"),
    ("admin", "Administrative questions", "Risk assessment"),
    ("specialists", "Specialist assessments", "Risk assessment"),
    ("student_ra", "Student risk sign-off", "Risk assessment sign-off"),
    ("supervisor_ra", "Supervisor risk sign-off", "Risk assessment sign-off"),
    ("entry_quality", "Appropriate field entries", "Risk assessment sign-off"),
    ("ethics_details", "Ethics information table", "Ethics"),
    ("low_risk", "Low Risk ethics only", "Ethics"),
    ("narrative", "Ethics responses", "Ethics"),
    ("word_limits", "Ethics word limits", "Ethics"),
    ("declarations", "Student declarations", "Ethics"),
    ("physical", "Risk assessment confirmed", "Ethics"),
    ("student_ethics", "Student ethics sign-off", "Ethics sign-off"),
    ("supervisor_ethics", "Supervisor ethics sign-off", "Ethics sign-off"),
    ("tutor", "Tutor checklist", "Ethics sign-off"),
    ("supervisor_statement", "Supervisor confirmation", "Ethics sign-off"),
]
REMINDER_CHECKS = {"word_limits"}
WORD_LIMIT_REMINDER = "Reminder only: keep the first three ethics responses within the form’s stated word limits. Word limits are not assessed by this tool or required in the audit."

BY_ID = {
    key: {"id": key, "label": label, "category": cat} for key, label, cat in CRITERIA
}
STATUSES = {
    "complete": "Complete",
    "skipped": "Skipped",
    "issue": "Issue found",
    "review": "Manual check",
    "supervisor": "Supervisor check",
    "moderator": "Needs moderator review",
    "unable": "Unable to check",
}


OVERALL_LABELS = {
    "complete": "Pass",
    "supervisor": "Pass — supervisor follow-up",
    "issue": "Fail — correction required",
    "review": "Needs moderator review",
    "moderator": "Needs moderator review",
    "unable": "Needs moderator review",
    "skipped": "Skipped",
    "pending": "Pending",
}


def result(key, status, message, evidence=None, source="Rule"):
    from .review_policy import checking_version

    return {
        "engine_version": checking_version(),
        **BY_ID[key],
        "status": status,
        "message": message,
        "evidence": evidence or [],
        "source": source,
        "decision": "",
        "note": "",
    }


def effective_status(check):
    if check.get("id") in REMINDER_CHECKS:
        return "skipped"
    if check["status"] == "skipped" and check.get("blocked_by"):
        return "skipped"
    if (
        check.get("id") == "specialists"
        and check.get("supporting_assessments")
        and check.get("decision") == "complete"
    ):
        return "supervisor"
    return check.get("decision") or check["status"]


def overall(checks):
    statuses = {effective_status(check) for check in checks}
    for status in ("issue", "unable", "moderator", "review", "supervisor"):
        if status in statuses:
            return status
    return "skipped" if statuses == {"skipped"} else "complete"


def ordered_checks(checks):
    """Present saved findings in current checklist order without changing results."""
    positions = {key: index for index, key in enumerate(BY_ID)}
    return [
        {
            **check,
            **BY_ID.get(check["id"], {}),
            **(
                {"status": "skipped", "message": WORD_LIMIT_REMINDER}
                if check["id"] in REMINDER_CHECKS
                else {}
            ),
        }
        for check in sorted(
            checks, key=lambda check: positions.get(check["id"], len(BY_ID))
        )
    ]
