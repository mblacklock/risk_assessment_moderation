"""One background worker per local process, with per-submission checkpoints."""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import store
from .ai import apply_ai, signature_scope_violation
from .checks import check_documents
from .criteria import CRITERIA, result
from .documents import archive_submissions, extract_document

logger = logging.getLogger(__name__)
EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moderation")
ACTIVE = {}


def create_review(data, title, use_ai):
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
        "ignored": ignored,
        "submissions": [],
        "error": "",
    }
    for group in groups:
        submission_id = str(uuid.uuid4())
        files = []
        for file in group.pop("files"):
            file_id = str(uuid.uuid4())
            path = directory / file_id
            path.write_bytes(file["data"])
            files.append(
                {"id": file_id, "name": file["name"], "size": len(file["data"])}
            )
        review["submissions"].append(
            {
                **group,
                "id": submission_id,
                "files": files,
                "state": "pending",
                "checks": [],
                "documents": [],
                "reader_version": 2,
                "area_activity_version": 2,
                "admin_check_version": 1,
                "ai": {"state": "pending" if use_ai else "off"},
            }
        )
    store.save(review)
    start(review_id)
    return review


def start(review_id):
    with store.LOCK:
        if review_id in ACTIVE and not ACTIVE[review_id].done():
            return
        ACTIVE[review_id] = EXECUTOR.submit(run, review_id)


def snapshot(review_id):
    with store.LOCK:
        review = store.load(review_id)
        changed = False
        for submission in review["submissions"]:
            for check in submission["checks"]:
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
                for key in ("decision", "note", "decided_at", "history"):
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
                for key in ("decision", "note", "decided_at", "history"):
                    if key in old:
                        replacement[key] = old[key]
                submission["checks"][index] = replacement
                break
            submission["admin_check_version"] = 1
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
        for submission in review["submissions"]:
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
                        "history",
                        "superseded_ai_finding",
                    ):
                        if key in previous[check["id"]]:
                            check[key] = previous[check["id"]][key]

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
