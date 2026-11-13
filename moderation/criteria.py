"""The moderation checklist, shared by checks, UI and exports."""

CRITERIA = [
    ("readable", "Document readable", "Details"),
    ("identity", "Assessor is student", "Details"),
    ("project", "Project details", "Details"),
    ("location", "Specific area or activity", "Details"),
    ("risk_table", "Risk table completed", "Risk assessment"),
    ("ratings", "Risk ratings completed", "Risk assessment"),
    ("risk_reduction", "Controls reduce risk rating", "Risk assessment"),
    ("example", "Example row removed", "Risk assessment"),
    ("admin", "Administrative questions", "Risk assessment"),
    ("specialists", "Specialist assessments", "Specialist assessments"),
    ("student_ra", "Student risk sign-off", "Signatures"),
    ("supervisor_ra", "Supervisor risk sign-off", "Signatures"),
    ("ethics_details", "Ethics details", "Ethics"),
    ("low_risk", "Low Risk ethics only", "Ethics"),
    ("narrative", "Ethics responses", "Ethics"),
    ("word_limits", "Ethics word limits", "Ethics"),
    ("declarations", "Student declarations", "Ethics"),
    ("physical", "Risk assessment confirmed", "Ethics"),
    ("tutor", "Tutor checklist", "Ethics"),
    ("supervisor_statement", "Supervisor confirmation", "Ethics"),
    ("student_ethics", "Student ethics sign-off", "Signatures"),
    ("supervisor_ethics", "Supervisor ethics sign-off", "Signatures"),
    ("hs_relevance", "H&S hazards only", "Content review"),
    ("facilities", "Activities–facilities consistency", "Content review"),
    ("entry_quality", "Appropriate field entries", "Content review"),
]
BY_ID = {
    key: {"id": key, "label": label, "category": cat} for key, label, cat in CRITERIA
}
STATUSES = {
    "complete": "Complete",
    "issue": "Issue found",
    "review": "Manual check",
    "unable": "Unable to check",
}


def result(key, status, message, evidence=None, source="Rule"):
    return {
        **BY_ID[key],
        "status": status,
        "message": message,
        "evidence": evidence or [],
        "source": source,
        "decision": "",
        "note": "",
    }


def effective_status(check):
    return check.get("decision") or check["status"]


def overall(checks):
    statuses = {effective_status(check) for check in checks}
    for status in ("issue", "unable", "review"):
        if status in statuses:
            return status
    return "complete"
