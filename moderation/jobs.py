"""One background worker per local process, with per-submission checkpoints."""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import store
from .ai import (
    HS_EVIDENCE_FAILURE,
    apply_ai,
    dedicated_scope_violation,
    rating_scope_violation,
    signature_scope_violation,
)
from .attempts import select_attempts
from .checks import check_documents
from .criteria import CRITERIA, result
from .documents import archive_submissions, extract_document, word_limit_guidance
from .workflow import REVIEW_FIELDS, finding_fingerprint

logger = logging.getLogger(__name__)
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moderation")
ACTIVE = {}


def create_review(data, title, use_ai, latest_only=False):
    groups, ignored = archive_submissions(data)
    review_id = str(uuid.uuid4())
    directory = store.review_dir(review_id)
    directory.mkdir(parents=True)
    review = {
        "version": 1,
        "checklist_version": 3,
        "id": review_id,
        "title": title[:150],
        "created": store.now(),
        "updated": store.now(),
        "state": "queued",
        "use_ai": use_ai,
        "latest_only": latest_only,
        "ignored": ignored,
        "submissions": [],
        "error": "",
    }
    for group in groups:
        review["submissions"].append(imported_submission(group, directory, use_ai))
    store.save(review)
    start(review_id)
    return review


def imported_submission(group, directory, use_ai):
    group = dict(group)
    submission_id = str(uuid.uuid4())
    files = []
    for file in group.pop("files"):
        file_id = str(uuid.uuid4())
        path = directory / file_id
        path.write_bytes(file["data"])
        files.append({"id": file_id, "name": file["name"], "size": len(file["data"])})
    return {
        **group,
        "id": submission_id,
        "files": files,
        "state": "pending",
        "checks": [],
        "documents": [],
        "reader_version": 2,
        "area_activity_version": 2,
        "admin_check_version": 1,
        "job_title_version": 1,
        "computer_location_version": 2,
        "signoff_image_version": 2,
        "multi_rating_version": 2,
        "risk_completion_version": 2,
        "declarations_version": 1,
        "specialist_followup_version": 2,
        "ai": {"state": "pending" if use_ai else "off"},
    }


def start(review_id):
    with store.LOCK:
        if review_id in ACTIVE and not ACTIVE[review_id].done():
            return
        ACTIVE[review_id] = EXECUTOR.submit(run, review_id)


def snapshot(review_id):
    with store.LOCK:
        review = store.load(review_id)
        changed = False
        prior_checks = {
            (submission["id"], check["id"]): dict(check)
            for submission in review["submissions"]
            for check in submission["checks"]
        }
        for submission in review["submissions"]:
            if submission["state"] != "done" or not any(
                (doc["kind"] == "pdf" and doc.get("pdf_reader_version", 0) < 9)
                or (
                    doc["kind"] == "docx"
                    and (
                        doc.get("drawing_reader_version", 0) < 1
                        or doc.get("linebreak_reader_version", 0) < 1
                    )
                )
                for doc in submission["documents"]
            ):
                continue
            try:
                documents = [
                    extract_document(
                        (store.review_dir(review_id) / file["id"]).read_bytes(),
                        file["name"],
                    )
                    for file in submission["files"]
                ]
                refreshed, _ = check_documents(documents, submission)
            except Exception:
                logger.exception("Could not refresh document layout extraction")
                continue
            previous = {c["id"]: c for c in submission["checks"]}
            for index, check in enumerate(refreshed):
                old = previous.get(check["id"])
                if old is None:
                    continue
                if old["source"] == "AI":
                    refreshed[index] = old
                    continue
                check["superseded_pdf_finding"] = dict(old)
                check["pdf_refresh_history"] = old.get("pdf_refresh_history", []) + [
                    {
                        key: old[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                ]
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                    } or key.startswith("superseded_"):
                        check[key] = value
            tables_changed = [d["tables"] for d in submission["documents"]] != [
                d["tables"] for d in documents
            ]
            submission.update(documents=documents, checks=refreshed)
            if review["use_ai"] and tables_changed:
                submission["ai"]["facilities_pending"] = True
            changed = True
        for submission in review["submissions"]:
            if submission["state"] != "done" or not any(
                doc.get("highlight_reader_version", 0) < 1
                for doc in submission["documents"]
            ):
                continue
            try:
                documents = [
                    extract_document(
                        (store.review_dir(review_id) / file["id"]).read_bytes(),
                        file["name"],
                    )
                    for file in submission["files"]
                ]
                refreshed, _ = check_documents(documents, submission)
            except Exception:
                logger.exception("Could not refresh highlighted answers")
                continue
            replacements = {
                c["id"]: c for c in refreshed if c["id"] in {"admin", "specialists"}
            }
            for index, old in enumerate(submission["checks"]):
                if old["id"] not in replacements:
                    continue
                check = replacements[old["id"]]
                check["superseded_highlight_finding"] = dict(old)
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                    } or key.startswith("superseded_"):
                        check[key] = value
                submission["checks"][index] = check
            submission["documents"] = documents
            changed = True
        for submission in review["submissions"]:
            if submission["state"] != "done":
                continue
            for check in submission["checks"]:
                if (
                    check["id"] == "hs_relevance"
                    and check["source"] == "Rule"
                    and check["status"] == "review"
                    and "AI evidence could not be verified" in check["message"]
                    and not check.get("hs_relevance_evidence_version")
                ):
                    check["superseded_hs_evidence_finding"] = {
                        key: check[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                    check["message"] = (
                        check["message"].split(" AI evidence could not be verified", 1)[
                            0
                        ]
                        + " "
                        + HS_EVIDENCE_FAILURE
                        if check["message"].startswith("Potential non-H&S")
                        else HS_EVIDENCE_FAILURE
                    )
                    check["hs_relevance_evidence_version"] = 1
                    if review["use_ai"]:
                        submission["ai"]["hs_relevance_pending"] = True
                    changed = True
                if (
                    check["id"] == "hs_relevance"
                    and "Language review is pending." in check["message"]
                ):
                    check["message"] = check["message"].replace(
                        "Language review is pending.",
                        "A verified AI content assessment is not available; review manually.",
                    )
                    changed = True
                if (
                    check["id"] == "facilities"
                    and check["status"] == "review"
                    and not check.get("facilities_status_version")
                    and (
                        check["source"] == "AI"
                        or "AI evidence could not be verified" in check["message"]
                    )
                ):
                    check["superseded_facilities_status_finding"] = {
                        key: check[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                    check["facilities_status_version"] = 1
                    submission["ai"]["facilities_pending"] = True
                    changed = True
                if (
                    check["id"] == "entry_quality"
                    and check["status"] == "review"
                    and check["source"] == "Rule"
                    and any(
                        phrase in check["message"]
                        for phrase in (
                            "AI signature comments were excluded",
                            "AI risk-rating comments were excluded",
                            "AI required-field omissions were excluded",
                            "AI duplicate completion/identity findings were excluded",
                        )
                    )
                    and not submission["ai"].get("entry_quality_pending")
                ):
                    submission["ai"]["entry_quality_pending"] = True
                    check["message"] = check["message"].replace(
                        "Review other field entries manually.",
                        "No usable AI assessment of other field entries was retained. "
                        "Run pending AI checks to reassess them, or review manually; "
                        "this is not a student correction request.",
                    )
                    changed = True
                if (
                    check["id"] == "entry_quality"
                    and check["source"] == "AI"
                    and check["status"] in {"issue", "review"}
                    and check["evidence"]
                    and all(word_limit_guidance(e["text"]) for e in check["evidence"])
                ):
                    check["superseded_guidance_finding"] = {
                        key: check[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                    check.update(
                        status="review",
                        source="Rule",
                        evidence=[],
                        message="The previous AI finding cited only template word-limit "
                        "guidance, not a student answer, and has been withdrawn. Run "
                        "pending AI checks to assess the actual field entries, or review manually.",
                    )
                    submission["ai"]["entry_quality_pending"] = True
                    changed = True
                if (
                    check["id"] == "hs_relevance"
                    and check["status"] == "review"
                    and check["source"] == "Rule"
                    and check["message"].startswith("Potential non-H&S")
                    and "AI observation:" in check["message"]
                    and not check.get("hs_relevance_ai_version")
                    and not submission["ai"].get("hs_relevance_pending")
                ):
                    submission["ai"]["hs_relevance_pending"] = True
                    changed = True
        for submission in review["submissions"]:
            for check in submission["checks"]:
                if (
                    check["id"] == "entry_quality"
                    and check["source"] == "AI"
                    and dedicated_scope_violation(check["status"], check["message"])
                ):
                    previous_finding = {
                        key: check[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                    check.setdefault("superseded_completion_finding", previous_finding)
                    check["superseded_dedicated_finding"] = previous_finding
                    check.update(
                        status="review",
                        source="Rule",
                        evidence=[],
                        message="The previous AI field-entry finding duplicated a dedicated "
                        "completion or assessor-identity check and has been "
                        "withdrawn here. The dedicated result is unchanged. Run pending AI "
                        "checks to assess populated answers, or review their meaning and placement manually.",
                    )
                    submission["ai"]["entry_quality_pending"] = True
                    changed = True
                if (
                    check["id"] == "entry_quality"
                    and check["source"] == "AI"
                    and rating_scope_violation(check["status"], check["message"])
                ):
                    check["superseded_rating_finding"] = {
                        key: check[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                    check.update(
                        status="review",
                        source="Rule",
                        evidence=[],
                        message="The previous AI entry-quality finding assessed risk ratings "
                        "outside this check's scope and has been withdrawn. Initial and "
                        "post-control multipliers may differ. Dedicated rule checks assess "
                        "rating completion and score reduction. Run pending AI checks to "
                        "assess other field entries, or review them manually.",
                    )
                    submission["ai"]["entry_quality_pending"] = True
                    changed = True
                if (
                    check["id"] == "entry_quality"
                    and check["source"] == "AI"
                    and signature_scope_violation(check["status"], check["message"])
                ):
                    check["superseded_ai_finding"] = {
                        "status": check["status"],
                        "message": check["message"],
                        "evidence": check["evidence"],
                    }
                    check.update(
                        status="review",
                        source="Rule",
                        evidence=[],
                        message="The previous AI entry-quality finding concerned signature presence, "
                        "which is assessed separately and includes embedded images. That finding "
                        "has been withdrawn. Re-run pending AI checks or review other field entries manually.",
                    )
                    submission["ai"]["entry_quality_pending"] = True
                    changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("reader_version", 0) >= 2
            ):
                continue
            try:
                documents = [
                    extract_document(
                        (store.review_dir(review_id) / file["id"]).read_bytes(),
                        file["name"],
                    )
                    for file in submission["files"]
                ]
                refreshed, _ = check_documents(documents, submission)
            except Exception:
                logger.exception("Could not refresh Word numbering extraction")
                continue
            previous = {check["id"]: check for check in submission["checks"]}
            for index, check in enumerate(refreshed):
                old = previous.get(check["id"])
                if not old:
                    if check["id"] == "facilities" and review["use_ai"]:
                        submission["ai"]["facilities_pending"] = True
                    continue
                if old["source"] == "AI":
                    refreshed[index] = old
                else:
                    for key in (
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                        "superseded_ai_finding",
                    ):
                        if key in old:
                            check[key] = old[key]
            submission.update(documents=documents, checks=refreshed, reader_version=2)
            changed = True
        for submission in review["submissions"]:
            if submission["state"] != "done" or any(
                check["id"] == "facilities" for check in submission["checks"]
            ):
                continue
            if submission["documents"]:
                updated, _ = check_documents(submission["documents"], submission)
                added = next(check for check in updated if check["id"] == "facilities")
            else:
                added = result(
                    "facilities", "unable", "No readable activity/workspace evidence."
                )
            submission["checks"].append(added)
            if review["use_ai"]:
                submission["ai"]["facilities_pending"] = True
            changed = True
        for submission in review["submissions"]:
            for check in submission["checks"]:
                legacy = "AI comparison is pending; otherwise check manually."
                if check["id"] != "facilities" or legacy not in check["message"]:
                    continue
                message = check["message"].replace(legacy, "Manual review required.")
                if (
                    check["source"] == "Rule"
                    and submission["ai"]["state"] == "complete"
                    and "AI evidence could not be verified" not in message
                ):
                    message += (
                        " No AI conclusion is recorded for this check, although the "
                        "submission's other AI checks completed. Run pending AI "
                        "checks to obtain a comparison, or review manually."
                    )
                    submission["ai"]["facilities_pending"] = True
                check["message"] = message
                changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("area_activity_version", 0) >= 2
                or not submission["documents"]
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacement = next(c for c in refreshed if c["id"] == "location")
            for index, old in enumerate(submission["checks"]):
                if old["id"] != "location":
                    continue
                replacement["superseded_area_activity_finding"] = {
                    key: old[key] for key in ("status", "source", "message", "evidence")
                }
                for key in (
                    "decision",
                    "note",
                    "decided_at",
                    *REVIEW_FIELDS,
                    "history",
                ):
                    if key in old:
                        replacement[key] = old[key]
                submission["checks"][index] = replacement
                if review["use_ai"] and replacement["status"] == "review":
                    submission["ai"]["location_pending"] = True
                break
            submission["area_activity_version"] = 2
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("admin_check_version", 0) >= 1
                or not submission["documents"]
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacement = next(c for c in refreshed if c["id"] == "admin")
            for index, old in enumerate(submission["checks"]):
                if old["id"] != "admin":
                    continue
                for key in (
                    "decision",
                    "note",
                    "decided_at",
                    *REVIEW_FIELDS,
                    "history",
                ):
                    if key in old:
                        replacement[key] = old[key]
                submission["checks"][index] = replacement
                break
            submission["admin_check_version"] = 1
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("job_title_version", 0) >= 1
                or not submission["documents"]
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacement = next(c for c in refreshed if c["id"] == "entry_quality")
            for index, old in enumerate(submission["checks"]):
                if old["id"] != "entry_quality":
                    continue
                if replacement["status"] == "issue":
                    replacement["superseded_job_title_finding"] = dict(old)
                    for key in (
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                    ):
                        if key in old:
                            replacement[key] = old[key]
                    submission["checks"][index] = replacement
                elif review["use_ai"]:
                    submission["ai"]["entry_quality_pending"] = True
                break
            submission["job_title_version"] = 1
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("computer_location_version", 0) >= 2
            ):
                continue
            for check in submission["checks"]:
                if (
                    check["id"] == "location"
                    and check["source"] == "AI"
                    and check["status"] in {"complete", "issue", "review"}
                ):
                    previous_finding = {
                        key: check[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                    check.setdefault(
                        "superseded_computer_location_finding", previous_finding
                    )
                    check["superseded_workspace_specificity_finding"] = previous_finding
                    check.update(
                        status="review",
                        source="Rule",
                        message="Computer-only work must identify a workstation/workspace "
                        "such as a home office or PC at home, or a specific process/procedure "
                        "in Area/Activity itself. Bare home or Design/Simulation needs clarification. "
                        "The previous AI finding needs reassessment under this rule. "
                        "Run pending AI checks, or assess the location and activities manually.",
                    )
                    if review["use_ai"]:
                        submission["ai"]["location_pending"] = True
            submission["computer_location_version"] = 2
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("signoff_image_version", 0) >= 2
                or not submission["documents"]
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacements = {
                c["id"]: c
                for c in refreshed
                if c["id"]
                in {
                    "student_ra",
                    "supervisor_ra",
                    "student_ethics",
                    "supervisor_ethics",
                }
            }
            for index, old in enumerate(submission["checks"]):
                if old["id"] not in replacements:
                    continue
                check = replacements[old["id"]]
                check["superseded_signoff_finding"] = dict(old)
                check["signoff_refresh_history"] = old.get(
                    "signoff_refresh_history", []
                ) + [
                    {
                        key: old[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                ]
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                    } or key.startswith("superseded_"):
                        check[key] = value
                submission["checks"][index] = check
            submission["signoff_image_version"] = 2
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("multi_rating_version", 0) >= 2
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacements = {
                c["id"]: c
                for c in refreshed
                if c["id"] in {"ratings", "risk_reduction"}
            }
            for index, old in enumerate(submission["checks"]):
                if old["id"] not in replacements:
                    continue
                check = replacements[old["id"]]
                check["superseded_multi_rating_finding"] = dict(old)
                check["multi_rating_refresh_history"] = old.get(
                    "multi_rating_refresh_history", []
                ) + [
                    {
                        key: old[key]
                        for key in ("status", "source", "message", "evidence")
                    }
                ]
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                    }:
                        check[key] = value
                    elif key.startswith("superseded_"):
                        check.setdefault(key, value)
                submission["checks"][index] = check
            submission["multi_rating_version"] = 2
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("declarations_version", 0) >= 1
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacement = next(c for c in refreshed if c["id"] == "declarations")
            for index, old in enumerate(submission["checks"]):
                if old["id"] != "declarations":
                    continue
                replacement["superseded_declarations_finding"] = dict(old)
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                    }:
                        replacement[key] = value
                    elif key.startswith("superseded_"):
                        replacement.setdefault(key, value)
                submission["checks"][index] = replacement
            submission["declarations_version"] = 1
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or submission.get("specialist_followup_version", 0) >= 2
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacement = next(c for c in refreshed if c["id"] == "specialists")
            for index, old in enumerate(submission["checks"]):
                if old["id"] != "specialists":
                    continue
                replacement["superseded_specialist_finding"] = dict(old)
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        "history",
                        *REVIEW_FIELDS,
                    }:
                        replacement[key] = value
                    elif key.startswith("superseded_"):
                        replacement.setdefault(key, value)
                # Rewording the same follow-up must not undo completed moderation.
                if (
                    old["status"] == "review"
                    and replacement["status"] in {"supervisor", "moderator"}
                    and old.get("evidence") == replacement.get("evidence")
                    and (
                        old.get("reviewed_fingerprint") == finding_fingerprint(old)
                        or (old.get("decided_at") and "reviewed_fingerprint" not in old)
                    )
                ):
                    replacement.update(
                        reviewed_at=old.get("reviewed_at", old.get("decided_at")),
                        reviewed_fingerprint=finding_fingerprint(replacement),
                    )
                submission["checks"][index] = replacement
            submission["specialist_followup_version"] = 2
            changed = True
        for submission in review["submissions"]:
            if submission["state"] != "done" or not submission["documents"]:
                continue
            found = next(
                (c for c in submission["checks"] if c["id"] == "facilities"), None
            )
            if found is None or found.get("blocked_by") == "location":
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacement = next(c for c in refreshed if c["id"] == "facilities")
            if replacement["status"] != "skipped":
                continue
            replacement["superseded_blocked_facilities_finding"] = dict(found)
            for key in ("decision", "note", "decided_at", "history", *REVIEW_FIELDS):
                if key in found:
                    replacement[key] = found[key]
            submission["checks"][submission["checks"].index(found)] = replacement
            submission["ai"].pop("facilities_pending", None)
            if "needs_manual_review" in submission["ai"]:
                submission["ai"]["needs_manual_review"] = [
                    key
                    for key in submission["ai"]["needs_manual_review"]
                    if key != "facilities"
                ]
            changed = True
        for submission in review["submissions"]:
            if (
                submission["state"] != "done"
                or not submission["documents"]
                or submission.get("risk_completion_version", 0) >= 2
            ):
                continue
            refreshed, _ = check_documents(submission["documents"], submission)
            replacements = {
                c["id"]: c
                for c in refreshed
                if c["id"] in {"risk_table", "ratings", "risk_reduction"}
            }
            for index, old in enumerate(submission["checks"]):
                if old["id"] not in replacements:
                    continue
                check = replacements[old["id"]]
                check["superseded_risk_completion_finding"] = dict(old)
                for key, value in old.items():
                    if key in {
                        "decision",
                        "note",
                        "decided_at",
                        "history",
                        *REVIEW_FIELDS,
                    }:
                        check[key] = value
                    elif key.startswith("superseded_"):
                        check.setdefault(key, value)
                submission["checks"][index] = check
            submission["risk_completion_version"] = 2
            changed = True
        for submission in review["submissions"]:
            for check in submission["checks"]:
                if check.get("decided_at") and "reviewed_fingerprint" not in check:
                    old = prior_checks.get((submission["id"], check["id"]), check)
                    check.update(
                        reviewed_at=check["decided_at"],
                        reviewed_fingerprint=finding_fingerprint(old),
                    )
                    changed = True
        if changed:
            review["checklist_version"] = 3
            store.save(review)
        if review["state"] in {"queued", "running"} and (
            review_id not in ACTIVE or ACTIVE[review_id].done()
        ):
            review["state"] = "interrupted"
            review["error"] = (
                "Processing stopped. Resume to continue unfinished submissions."
            )
            store.save(review)
        return review


def run(review_id):
    try:
        store.update(review_id, lambda r: r.update(state="running", error=""))
        review = store.load(review_id)
        for submission in select_attempts(review).active:
            if submission["state"] == "done":
                continue
            documents, errors = [], []
            for file in submission["files"]:
                try:
                    documents.append(
                        extract_document(
                            (store.review_dir(review_id) / file["id"]).read_bytes(),
                            file["name"],
                        )
                    )
                except Exception:
                    logger.exception("Could not extract submission document")
                    errors.append(file["name"])
            if documents:
                checks, extracted = check_documents(documents, submission)
            else:
                checks = [
                    result(
                        key, "unable", "No readable documents. Inspect original files."
                    )
                    for key, _, _ in CRITERIA
                ]
                extracted = None
            if errors:
                checks[0]["status"] = "unable"
                checks[0]["message"] = "Could not read: " + "; ".join(errors)
            ai = {"state": "off"}
            if review["use_ai"] and extracted:
                try:
                    ai = apply_ai(checks, extracted, submission)
                except Exception:
                    logger.exception("AI review failed")
                    ai = {
                        "state": "failed",
                        "message": "AI check failed. Verify API configuration and retry; rule results are retained.",
                    }
            # If a previous run was interrupted, retain the moderator's decisions.
            previous = {c["id"]: c for c in submission["checks"]}
            for check in checks:
                if check["id"] in previous:
                    for key in (
                        "decision",
                        "note",
                        "decided_at",
                        *REVIEW_FIELDS,
                        "history",
                        "superseded_ai_finding",
                        "superseded_job_title_finding",
                        "superseded_rating_finding",
                        "superseded_computer_location_finding",
                        "superseded_workspace_specificity_finding",
                        "superseded_guidance_finding",
                        "superseded_pdf_finding",
                        "superseded_completion_finding",
                        "superseded_dedicated_finding",
                        "superseded_facilities_status_finding",
                        "pdf_refresh_history",
                        "superseded_highlight_finding",
                        "superseded_hs_evidence_finding",
                        "superseded_lab_context_finding",
                        "superseded_signoff_finding",
                        "signoff_refresh_history",
                        "superseded_multi_rating_finding",
                        "superseded_declarations_finding",
                        "superseded_specialist_finding",
                        "superseded_blocked_facilities_finding",
                        "superseded_risk_completion_finding",
                        "multi_rating_refresh_history",
                    ):
                        if key in previous[check["id"]]:
                            check[key] = previous[check["id"]][key]
                    if "excluded_entry_quality_assessments" in previous[check["id"]]:
                        check["excluded_entry_quality_assessments"] = previous[
                            check["id"]
                        ]["excluded_entry_quality_assessments"] + check.get(
                            "excluded_entry_quality_assessments", []
                        )
                    if "excluded_facilities_assessments" in previous[check["id"]]:
                        check["excluded_facilities_assessments"] = previous[
                            check["id"]
                        ]["excluded_facilities_assessments"] + check.get(
                            "excluded_facilities_assessments", []
                        )
                    if "excluded_hs_relevance_assessments" in previous[check["id"]]:
                        check["excluded_hs_relevance_assessments"] = previous[
                            check["id"]
                        ]["excluded_hs_relevance_assessments"] + check.get(
                            "excluded_hs_relevance_assessments", []
                        )

            def finish(
                r, sid=submission["id"], found=checks, docs=documents, ai_result=ai
            ):
                target = next(s for s in r["submissions"] if s["id"] == sid)
                target.update(
                    checks=found,
                    documents=docs,
                    ai=ai_result,
                    state="done",
                    reader_version=2,
                    area_activity_version=2,
                    admin_check_version=1,
                    job_title_version=1,
                    computer_location_version=2,
                    signoff_image_version=2,
                    multi_rating_version=2,
                    risk_completion_version=2,
                    declarations_version=1,
                    specialist_followup_version=2,
                )

            store.update(review_id, finish)
        store.update(review_id, lambda r: r.update(state="done"))
    except Exception:
        logger.exception("Review processing failed")
        store.update(
            review_id,
            lambda r: r.update(
                state="interrupted",
                error="Processing stopped unexpectedly. Resume to retry unfinished submissions.",
            ),
        )
