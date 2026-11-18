import copy
import mimetypes
import os
import re
import zipfile
from urllib.parse import urlencode

from django import forms
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import global_approvals as shared_approvals
from . import jobs, store
from .ai import ai_work_counts, eligible_ai_checks
from .attempts import select_attempts
from .criteria import (
    BY_ID,
    CRITERIA,
    OVERALL_LABELS,
    REMINDER_CHECKS,
    STATUSES,
    WORD_LIMIT_REMINDER,
    effective_status,
    ordered_checks,
    overall,
)
from .documents import bounded_zip
from .exports import csv_bytes, xlsx_bytes
from .feedback import (
    FeedbackWordingForm,
    bulk_feedback_state,
    current_feedback,
    feedback_items,
    feedback_readiness,
    feedback_signature,
    generate_bulk_feedback,
    new_feedback_record,
)
from .forms import DecisionForm, UploadForm
from .review_policy import checking_version
from .validation import (
    audit_overview,
    check_statistics,
    comparison_rows,
    comparison_token,
)
from .word_drawings import word_drawing_png
from .workflow import finding_fingerprint, review_progress


def get_review(review_id):
    try:
        return jobs.snapshot(str(review_id))
    except (OSError, ValueError, KeyError):
        raise Http404("Review not found.") from None


def get_submission(review, submission_id):
    item = next(
        (s for s in review["submissions"] if s["id"] == str(submission_id)), None
    )
    if not item:
        raise Http404("Submission not found.")
    return item


def decorated(check, review=None):
    if check["id"] in REMINDER_CHECKS:
        check = {**check, "status": "skipped", "message": WORD_LIMIT_REMINDER}
    return {
        **check,
        **review_progress(check, review),
        "blocked": check["id"] in REMINDER_CHECKS
        or (check["status"] == "skipped" and bool(check.get("blocked_by"))),
        "effective": effective_status(check),
        "status_label": STATUSES[effective_status(check)],
        "automated_label": STATUSES[check["status"]],
    }


def index(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            review = jobs.create_review(
                form.cleaned_data["archive"].read(),
                form.cleaned_data["title"],
                form.cleaned_data["use_ai"],
                form.cleaned_data["latest_only"],
            )
            return redirect("moderation:review", review_id=review["id"])
        except (ValueError, zipfile.BadZipFile, OSError, RuntimeError) as error:
            form.add_error(
                "archive",
                str(error)
                if isinstance(error, ValueError)
                else "Could not read this ZIP. Check the archive and available disk space.",
            )
    return render(
        request,
        "moderation/index.html",
        {
            "form": form,
            "reviews": store.list_reviews(),
            "ai_ready": bool(os.getenv("OPENAI_API_KEY")),
            "checklist_count": sum(
                key not in REMINDER_CHECKS for key, _, _ in CRITERIA
            ),
        },
    )


def grid_context(data, params):
    selection = select_attempts(data)
    total_attempts = len(data["submissions"])
    data = {**data, "submissions": selection.active}
    category = params.get("category", "")
    if category in {
        "Submission details",
        "Project and submission details",
        "Risk assessment details",
    }:
        category = "RA information"
    status = params.get("status", "")
    criterion = params.get("criterion", "")
    if criterion not in BY_ID or (
        category and BY_ID[criterion]["category"] != category
    ):
        criterion = ""
    query = params.get("q", "").strip()
    sort = params.get("sort", "name")
    descending = params.get("direction") == "desc"
    columns = [
        BY_ID[key]
        for key, _, cat in CRITERIA
        if (not category or category == cat) and (not criterion or criterion == key)
    ]
    needs_review = params.get("needs_review") == "on"
    unresolved_only = params.get("needs_review") == "unresolved"
    rows = []
    totals = {key: 0 for key in STATUSES}
    overall_totals = {key: 0 for key in OVERALL_LABELS}
    for item in data["submissions"]:
        state = overall(item["checks"]) if item["checks"] else "pending"
        overall_totals[state] += 1
        present = {effective_status(c) for c in item["checks"]}
        for outcome in present - {"complete"}:
            totals[outcome] += 1
        if state == "complete":
            totals["complete"] += 1
        checks = {
            c["id"]: decorated({**c, **BY_ID[c["id"]]}, data) for c in item["checks"]
        }
        cells = [
            checks.get(
                col["id"],
                {
                    "id": col["id"],
                    "category": col["category"],
                    "effective": "pending",
                    "status_label": "Pending",
                },
            )
            for col in columns
        ]
        if (
            query
            and query.casefold()
            not in (
                item["name"]
                + " "
                + item["number"]
                + " ".join(f["name"] for f in item["files"])
            ).casefold()
        ):
            continue
        for cell in cells:
            cell["progress_match"] = (
                cell.get("review_unresolved")
                if unresolved_only
                else cell.get("needs_review")
            )
        if unresolved_only and not any(
            c.get("review_unresolved") and (not status or c["effective"] == status)
            for c in cells
        ):
            continue
        if needs_review and not any(
            c.get("needs_review") and (not status or c["effective"] == status)
            for c in cells
        ):
            continue
        if status and not any(c["effective"] == status for c in cells):
            continue
        row_flagged = [
            c for c in item["checks"] if review_progress(c, data)["review_required"]
        ]
        row_reviewed = sum(review_progress(c, data)["reviewed"] for c in row_flagged)
        row_review_complete = bool(row_flagged) and row_reviewed == len(row_flagged)
        row_review_label = (
            "Awaiting checks"
            if item["state"] != "done"
            else "Reviewed"
            if row_review_complete
            else (
                "No review required"
                if data.get("review_mode") == "routine"
                else "No flagged checks"
            )
            if not row_flagged
            else f"{row_reviewed} of {len(row_flagged)} reviewed"
            if row_reviewed
            else "Not reviewed"
        )
        first_unreviewed = next(
            (
                c
                for c in ordered_checks(item["checks"])
                if review_progress(c, data)["needs_review"]
            ),
            None,
        )
        row_review_url = (
            finding_url(data["id"], item["id"], first_unreviewed["id"], params)
            if first_unreviewed
            and item["state"] == "done"
            and data["state"] not in {"running", "queued"}
            else ""
        )
        rows.append(
            {
                **item,
                "row_review_url": row_review_url,
                "row_review_label": row_review_label,
                "row_review_complete": row_review_complete,
                "cells": cells,
                "outcome": state,
                "outcome_label": OVERALL_LABELS.get(state, "Pending"),
                "flag_count": len(row_flagged),
            }
        )

    def sorting(row):
        if sort == "overall":
            return {
                "issue": 0,
                "unable": 1,
                "moderator": 1,
                "review": 1,
                "supervisor": 2,
                "complete": 3,
                "skipped": 4,
                "pending": 5,
            }.get(row["outcome"], 5), row["name"].casefold()
        if sort == "issues":
            return row["flag_count"], row["name"].casefold()
        if sort in BY_ID:
            cell = next((c for c in row["checks"] if c["id"] == sort), None)
            return (
                {
                    "issue": 0,
                    "unable": 1,
                    "moderator": 2,
                    "review": 3,
                    "supervisor": 4,
                    "complete": 5,
                }.get(effective_status(cell), 4)
                if cell
                else 4,
                row["name"].casefold(),
            )
        return row.get(
            sort if sort in {"name", "number", "submitted"} else "name", ""
        ).casefold()

    rows.sort(key=sorting, reverse=descending)
    flagged = [
        c
        for item in data["submissions"]
        for c in item["checks"]
        if review_progress(c, data)["review_required"]
    ]
    pending_ai_count, unverified_ai_checks = ai_work_counts(
        data["submissions"], data["use_ai"]
    )
    return {
        "review": data,
        "needs_review": needs_review,
        "unresolved_only": unresolved_only,
        "progress_filtered": needs_review or unresolved_only,
        "supervisor_count": sum(effective_status(c) == "supervisor" for c in flagged),
        "unresolved_count": sum(
            review_progress(c, data)["review_unresolved"] for c in flagged
        ),
        "automatic_count": sum(
            review_progress(c, data)["automatic"]
            for item in data["submissions"]
            for c in item["checks"]
        ),
        "flagged_count": len(flagged),
        "reviewed_count": sum(review_progress(c, data)["reviewed"] for c in flagged),
        "remaining_count": sum(
            review_progress(c, data)["needs_review"] for c in flagged
        ),
        "total_attempts": total_attempts,
        "earlier_attempts": selection.earlier,
        "attempt_warnings": selection.warnings,
        "unprocessed_count": sum(s["state"] != "done" for s in selection.active),
        "rows": rows,
        "columns": columns,
        "totals": totals,
        "overall_totals": overall_totals,
        "overall_moderation_count": sum(
            overall_totals[key] for key in ("review", "moderator", "unable")
        ),
        "categories": list(dict.fromkeys(cat for _, _, cat in CRITERIA)),
        "criteria": [
            c for c in BY_ID.values() if not category or c["category"] == category
        ],
        "statuses": STATUSES,
        "category": category,
        "status": status,
        "criterion": criterion,
        "q": query,
        "sort": sort,
        "direction": "desc" if descending else "asc",
        "done_count": sum(s["state"] == "done" for s in data["submissions"]),
        "processing": data["state"] in {"running", "queued"},
        "ai_ready": bool(os.getenv("OPENAI_API_KEY")),
        "pending_ai_count": pending_ai_count,
        "unverified_ai_checks": unverified_ai_checks,
    }


GRID_KEYS = (
    "category",
    "status",
    "criterion",
    "q",
    "sort",
    "direction",
    "needs_review",
)


def grid_params(raw):
    parsed = QueryDict(raw[:8000])
    result = QueryDict(mutable=True)
    for key in GRID_KEYS:
        if key in parsed:
            result[key] = parsed[key]
    return result


def review_queue(context, params):
    return [
        (row["id"], cell["id"])
        for row in context["rows"]
        for cell in row["cells"]
        if cell.get("needs_review")
        and (not params.get("status") or cell["effective"] == params["status"])
    ]


def finding_url(review_id, submission_id, criterion, params):
    return (
        reverse("moderation:submission", args=[review_id, submission_id])
        + "?"
        + urlencode({"grid": params.urlencode()})
        + "#"
        + criterion
    )


def grid_url(review_id, params):
    path = reverse("moderation:review", args=[review_id])
    return path + ("?" + params.urlencode() if params else "")


@require_GET
def review(request, review_id):
    params = grid_params(request.GET.urlencode())
    context = grid_context(get_review(review_id), params)
    queue = review_queue(context, params)
    next_params = params
    next_all = False
    if not queue and context["remaining_count"]:
        next_params = grid_params("")
        for key in ("sort", "direction"):
            if key in params:
                next_params[key] = params[key]
        next_params["needs_review"] = "on"
        queue = review_queue(grid_context(context["review"], next_params), next_params)
        next_all = bool(queue)
    context.update(
        next_review_url=finding_url(review_id, *queue[0], next_params)
        if queue and not context["processing"]
        else "",
        next_review_all=next_all,
    )
    saved = request.GET.get("saved", "")
    context.update(
        grid_query=params.urlencode(),
        saved_cell=saved,
        saved_notice=bool(re.fullmatch(r"[0-9a-f-]{36}:[a-z_]+", saved)),
    )
    return render(request, "moderation/review.html", context)


@require_GET
def progress(request, review_id):
    data = get_review(review_id)
    active = select_attempts(data).active
    return JsonResponse(
        {
            "state": data["state"],
            "done": sum(s["state"] == "done" for s in active),
            "total": len(active),
            "updated": data["updated"],
        }
    )


@require_GET
def submission(request, review_id, submission_id):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
    feedback_ready, feedback_reason = feedback_readiness(data, item)
    documents = []
    paragraph_images = {}
    for idx, doc in enumerate(item["documents"]):
        image_paths = list(
            dict.fromkeys(path for p in doc["paragraphs"] for path in p["images"])
        )
        documents.append(
            {
                **doc,
                "images": [
                    reverse(
                        "moderation:image",
                        kwargs={
                            "review_id": review_id,
                            "submission_id": submission_id,
                            "doc_index": idx,
                            "image_index": image_idx,
                        },
                    )
                    for image_idx in range(len(image_paths))
                ],
            }
        )
        image_urls = dict(zip(image_paths, documents[-1]["images"]))
        for number, paragraph in enumerate(doc["paragraphs"], 1):
            paragraph_images[f"Document {idx + 1}, paragraph {number}"] = [
                image_urls[path] for path in dict.fromkeys(paragraph["images"])
            ]
    checks = []
    for check in ordered_checks(item["checks"]):
        extracts = []
        for extract in check["evidence"]:
            displayed = {
                **extract,
                "images": paragraph_images.get(extract["location"], []),
            }
            if displayed not in extracts:
                extracts.append(displayed)
        checks.append({**decorated(check, data), "evidence": extracts})
    return render(
        request,
        "moderation/submission.html",
        {
            "review": data,
            "submission": item,
            "feedback_ready": feedback_ready,
            "feedback_reason": feedback_reason,
            "feedback_signature": feedback_signature(item),
            "grid_query": grid_params(request.GET.get("grid", "")).urlencode(),
            "grid_url": grid_url(review_id, grid_params(request.GET.get("grid", ""))),
            "excluded_attempt": any(
                s["id"] == item["id"] for s in select_attempts(data).earlier
            ),
            "checks": checks,
            "documents": documents,
            "editable": data["state"] not in {"running", "queued"},
            "statuses": STATUSES,
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def feedback(request, review_id, submission_id):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
    ready, reason = feedback_readiness(data, item)
    signature = feedback_signature(item)
    saved = item.get("elp_feedback", {})
    current = current_feedback(data, item)
    if request.method == "GET" and "verify" in request.GET:
        response = JsonResponse(
            {
                "current": bool(
                    current
                    and request.GET["verify"] == signature
                    and request.GET.get("version") == saved.get("id")
                )
            }
        )
        response["Cache-Control"] = "no-store"
        return response
    if not ready:
        return HttpResponse(reason, status=409)
    if request.method == "POST" and request.POST.get("signature") != signature:
        return HttpResponse(
            "The findings changed. Return to the submission, finish its review and generate feedback again.",
            status=409,
        )
    entries = feedback_items(item)
    params = grid_params(request.POST.get("grid", request.GET.get("grid", "")))
    context = {
        "review": data,
        "submission": item,
        "signature": signature,
        "grid_query": params.urlencode(),
        "feedback": saved if current else None,
    }
    if request.method == "POST":
        if request.POST.get("action") == "edit":
            context.update(
                form=FeedbackWordingForm(
                    entries, initial=saved.get("wording", {}) if current else None
                ),
                feedback=None,
            )
        else:
            confirmed = request.POST.get("action") == "confirm"
            if confirmed:
                form = FeedbackWordingForm(entries, request.POST)
            elif all(entry["text"] for entry in entries):
                form = FeedbackWordingForm(
                    entries, {entry["key"]: entry["text"] for entry in entries}
                )
            else:
                form = FeedbackWordingForm(entries)
                context.update(form=form, feedback=None, wording_needed=True)
                return render(request, "moderation/feedback.html", context)
            if not form.is_valid():
                context.update(form=form, feedback=None, wording_needed=True)
                return render(request, "moderation/feedback.html", context, status=400)
            record = new_feedback_record(item, form.cleaned_data, store.now())

            def save(review):
                target = get_submission(review, submission_id)
                allowed, _ = feedback_readiness(review, target)
                if not allowed or feedback_signature(target) != signature:
                    raise ValueError("Findings changed during feedback generation.")
                target["elp_feedback"] = record
                target.setdefault("feedback_history", []).append(record)

            try:
                store.update(str(review_id), save)
            except ValueError:
                return HttpResponse(
                    "The review changed. Complete moderation and generate feedback again.",
                    status=409,
                )
            return redirect(
                reverse("moderation:feedback", args=[review_id, submission_id])
                + "?"
                + urlencode({"grid": params.urlencode()})
            )
    elif not current:
        context.update(form=FeedbackWordingForm(entries), feedback=None)
    response = render(request, "moderation/feedback.html", context)
    response["Cache-Control"] = "no-store"
    return response


@never_cache
@require_http_methods(["GET", "POST"])
def bulk_feedback(request, review_id):
    data = get_review(review_id)
    params = grid_params(request.POST.get("grid", request.GET.get("grid", "")))
    if request.method == "POST":
        with store.LOCK:
            latest = store.load(str(review_id))
            if latest["state"] in {"queued", "running"}:
                return HttpResponse(
                    "Wait for processing to finish before generating bulk feedback.",
                    status=409,
                )
            created = generate_bulk_feedback(latest, store.now())
            if created:
                latest["updated"] = store.now()
                store.save(latest)
        return redirect(
            reverse("moderation:bulk_feedback", args=[review_id])
            + "?"
            + urlencode({"grid": params.urlencode()})
        )
    state = bulk_feedback_state(data)
    return render(
        request,
        "moderation/bulk_feedback.html",
        {
            "review": data,
            **state,
            "grid_query": params.urlencode(),
            "grid_url": grid_url(review_id, params),
            "processing": data["state"] in {"queued", "running"},
        },
    )


@never_cache
@require_GET
def download_feedback(request, review_id):
    data = get_review(review_id)
    state = bulk_feedback_state(data)
    if not state["generated"] or request.GET.get("version") != state["batch_version"]:
        return HttpResponse(
            "The feedback selection changed or nothing is ready to download. Open bulk eLP feedback, finish any required review and generate again.",
            status=409,
        )
    try:
        payload = xlsx_bytes(data)
    except ValueError as error:
        return HttpResponse(str(error), status=400)
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="moderation-{review_id}.xlsx"'
    )
    return response


@require_POST
def decide(request, review_id, submission_id, criterion):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
    if data["state"] in {"running", "queued"}:
        return HttpResponse(
            "Wait for processing to finish before recording decisions.", status=409
        )
    if criterion not in {c["id"] for c in item["checks"]}:
        raise Http404("Criterion not found.")
    target_check = next(c for c in item["checks"] if c["id"] == criterion)
    if target_check["id"] in REMINDER_CHECKS:
        return HttpResponse(
            "This is a reminder only and does not require a moderation decision.",
            status=409,
        )
    if target_check["status"] == "skipped" and target_check.get("blocked_by"):
        return HttpResponse(
            "This check is skipped until its prerequisite is completed.", status=409
        )
    form = DecisionForm(request.POST)
    if not form.is_valid():
        return HttpResponse(
            "Choose a valid outcome and keep any optional note within 3,000 characters.",
            status=400,
        )

    params = grid_params(request.POST.get("grid", ""))
    queue = review_queue(grid_context(data, params), params)

    def change(review):
        target = get_submission(review, submission_id)
        check = next(c for c in target["checks"] if c["id"] == criterion)
        check.setdefault("history", []).append(
            {
                "decision": form.cleaned_data["decision"],
                "note": form.cleaned_data["note"],
                "at": store.now(),
                "finding_fingerprint": finding_fingerprint(check),
            }
        )
        check.update(
            decision=form.cleaned_data["decision"],
            note=form.cleaned_data["note"],
            decided_at=store.now(),
            reviewed_at=store.now(),
            reviewed_fingerprint=finding_fingerprint(check),
        )

    updated = store.update(str(review_id), change)
    current = (str(submission_id), criterion)
    if request.POST.get("action") == "next":
        position = queue.index(current) if current in queue else -1
        for sid, key in queue[position + 1 :] + queue[: position + 1]:
            if (sid, key) == current:
                continue
            candidate = next(
                c for c in get_submission(updated, sid)["checks"] if c["id"] == key
            )
            if review_progress(candidate, updated)["needs_review"]:
                return redirect(finding_url(review_id, sid, key, params))
    result_params = params.copy()
    result_params["saved"] = f"{submission_id}:{criterion}"
    return redirect(grid_url(review_id, result_params))


@require_POST
def attempt_selection(request, review_id):
    def change(review):
        if review["state"] in {"running", "queued"}:
            return
        review["latest_only"] = request.POST.get("latest_only") == "on"

    store.update(str(get_review(review_id)["id"]), change)
    return redirect("moderation:review", review_id=review_id)


@never_cache
@require_http_methods(["GET", "POST"])
def review_process(request, review_id):
    data = get_review(review_id)
    error = ""
    if request.method == "POST":
        mode = request.POST.get("mode")
        if mode not in {"validation", "routine"}:
            return HttpResponse(
                "Choose Validate the tool or Moderate submissions.", status=400
            )

        def change(review):
            if review["state"] in {"running", "queued"}:
                raise ValueError(
                    "Wait for processing to finish before changing workflow."
                )
            review.setdefault("review_process_history", []).append(
                {
                    "mode": mode,
                    "previous_mode": review.get("review_mode", "validation"),
                    "at": store.now(),
                    "action": "choose_workflow",
                }
            )
            review["review_mode"] = mode

        try:
            store.update(str(review_id), change)
        except ValueError as exc:
            error = str(exc)
        else:
            return redirect(
                "moderation:validation_list"
                if mode == "validation"
                else "moderation:review",
                review_id=review_id,
            )
    return render(
        request,
        "moderation/review_process.html",
        {
            "review": data,
            "error": error,
            "approved_count": sum(
                value.get("version") == checking_version()
                for value in shared_approvals.approvals(data).values()
            ),
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def study_settings(request, review_id):
    # Keep saved links working; approvals now have one workspace-wide owner.
    return redirect("moderation:global_approvals")


@never_cache
@require_http_methods(["GET", "POST"])
def global_approvals(request):
    version = checking_version()
    error = ""
    try:
        registry = shared_approvals.load()
    except (OSError, ValueError, TypeError):
        return HttpResponse(
            "Global approvals could not be read. Restore the registry before editing approvals. Findings still require confirmation.",
            status=503,
        )
    if request.method == "POST":
        try:
            shared_approvals.set_approval(
                request.POST.get("key", ""),
                request.POST.get("action", ""),
                request.POST.get("version", ""),
                request.POST.get("reference", ""),
                request.POST.get("note", ""),
                expected_revision=request.POST.get("revision", ""),
            )
        except ValueError as exception:
            error = str(exception)
        else:
            return redirect(reverse("moderation:global_approvals") + "?saved=1")
    registry = shared_approvals.load() or {
        "approvals": {},
        "history": [],
        "revision": "new",
    }
    rows = []
    for criterion, label, category in CRITERIA:
        if criterion in REMINDER_CHECKS:
            continue
        sources = []
        for source in ("Rule", "AI"):
            key = f"{criterion}:{source}"
            record = registry["approvals"].get(key, {})
            sources.append(
                {
                    "key": key,
                    "source": source,
                    "record": record,
                    "approved": bool(
                        record.get("reference") and record.get("version") == version
                    ),
                    "stale": bool(record and record.get("version") != version),
                }
            )
        rows.append({"label": label, "category": category, "sources": sources})
    return render(
        request,
        "moderation/global_approvals.html",
        {
            "rows": rows,
            "error": error,
            "checking_version": version,
            "revision": registry["revision"],
            "saved": request.GET.get("saved") == "1",
            "approved_count": len(shared_approvals.current_approvals()),
            "history": list(reversed(registry["history"]))[:50],
            "initialised": shared_approvals.load() is not None,
        },
        status=400 if error else 200,
    )


class ValidationAuditForm(forms.Form):
    notes = forms.CharField(required=False, max_length=5000, widget=forms.Textarea)
    other_corrections = forms.CharField(
        required=False,
        max_length=5000,
        label="Other corrections not covered by the checks",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Record additional feedback, unused-row cleanup or a correction that did not fit an audit category. This does not change the selected check outcomes.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label, _ in CRITERIA:
            self.fields[f"audit_{key}"] = forms.ChoiceField(
                label=label,
                widget=forms.RadioSelect,
                disabled=key in REMINDER_CHECKS,
                initial="skipped" if key in REMINDER_CHECKS else None,
                choices=[
                    ("complete", "Complete"),
                    ("issue", "Correction required"),
                    ("supervisor", "Supervisor follow-up"),
                    ("review", "Unresolved / uncertain"),
                    ("skipped", "Not applicable"),
                ],
            )


class AuditDetailsForm(forms.Form):
    auditor = forms.CharField(max_length=150, label="Auditor name")
    minutes = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=8,
        decimal_places=2,
        label="Total time taken (minutes)",
    )
    comments = forms.CharField(
        required=False, max_length=5000, widget=forms.Textarea(attrs={"rows": 3})
    )


@never_cache
@require_http_methods(["GET", "POST"])
def validation_list(request, review_id):
    data = get_review(review_id)
    form = AuditDetailsForm(
        request.POST if request.method == "POST" else None,
        initial=data.get("audit_details", {}),
    )
    if request.method == "POST" and form.is_valid():

        def change(review):
            details = {
                "auditor": form.cleaned_data["auditor"],
                "minutes": str(form.cleaned_data["minutes"])
                if form.cleaned_data["minutes"] is not None
                else "",
                "comments": form.cleaned_data["comments"],
                "at": store.now(),
            }
            review["audit_details"] = details
            review.setdefault("audit_details_history", []).append(
                copy.deepcopy(details)
            )

        store.update(str(review_id), change)
        return redirect(
            reverse("moderation:validation_list", args=[review_id]) + "?saved=1"
        )
    return render(
        request,
        "moderation/validation_list.html",
        {
            "review": data,
            **audit_overview(data),
            "form": form,
            "audit_saved": request.GET.get("audit_saved") == "1",
            "details_saved": request.GET.get("saved") == "1",
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def validation_audit(request, review_id, submission_id):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
    if request.GET.get("compare") == "1":
        return redirect("moderation:validation_comparison", review_id=review_id)
    latest = (
        item.get("validation_audits", [])[-1] if item.get("validation_audits") else None
    )
    initial = (
        {f"audit_{key}": value for key, value in latest.get("findings", {}).items()}
        if latest
        else {}
    )
    if latest:
        initial["notes"] = latest.get("notes", "")
        initial["other_corrections"] = latest.get("other_corrections", "")
    form = ValidationAuditForm(
        request.POST if request.method == "POST" else None, initial=initial
    )
    if request.method == "POST" and form.is_valid():

        def change(review):
            if review["state"] in {"running", "queued"}:
                raise ValueError(
                    "Wait for processing to finish before recording the comparison."
                )
            auditor = review.get("audit_details", {}).get("auditor", "")
            target = get_submission(review, submission_id)
            history = target.setdefault("validation_audits", [])
            previous = history[-1] if history else None
            history.append(
                {
                    "at": store.now(),
                    "reviewer": auditor,
                    "audit_details_snapshot": copy.deepcopy(
                        review.get("audit_details", {})
                    ),
                    "notes": form.cleaned_data["notes"],
                    "other_corrections": form.cleaned_data["other_corrections"],
                    "version": checking_version(),
                    "findings": {
                        key: form.cleaned_data[f"audit_{key}"] for key, _, _ in CRITERIA
                    },
                    "automated_snapshot": copy.deepcopy(
                        previous["automated_snapshot"] if previous else target["checks"]
                    ),
                    "ai_metadata": copy.deepcopy(
                        previous.get("ai_metadata", {})
                        if previous
                        else target.get("ai", {})
                    ),
                    "revision_of": previous["at"] if previous else None,
                }
            )

        try:
            store.update(str(review_id), change)
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            return redirect(
                reverse("moderation:validation_list", args=[review_id])
                + "?audit_saved=1"
            )
    return render(
        request,
        "moderation/validation_audit.html",
        {
            "review": data,
            "submission": item,
            "form": form,
            "editing_audit": bool(latest),
            "audit_fields": [
                {
                    "category": category,
                    "field": form[f"audit_{key}"],
                    "reminder": key in REMINDER_CHECKS,
                }
                for key, _, category in CRITERIA
            ],
        },
    )


def validation_comparisons(state, historical=()):
    comparisons = []
    for row in state["audit_rows"]:
        rows = comparison_rows(row["audit"])
        for result in rows:
            earlier = [
                d
                for d in historical
                if d["student_number"] == row["submission"]["number"]
                and d["check"] == result["id"]
            ]
            if earlier:
                result["historical_history"] = earlier
                result["historical_decision"] = earlier[-1]
            decisions = [
                d
                for d in row["submission"].get("audit_adjudications", [])
                if d["audit_at"] == row["audit"]["at"]
                and d["criterion"] == result["id"]
            ]
            if decisions:
                from .validation import ADJUDICATIONS

                result["adjudication"] = decisions[-1]
                result["adjudication_label"] = ADJUDICATIONS.get(
                    decisions[-1]["classification"], "Unresolved"
                )
            result["submission_id"] = row["submission"]["id"]
        comparisons.append(
            {
                **row,
                "rows": rows,
                "different_results": [result for result in rows if not result["same"]],
                "matching_results": [result for result in rows if result["same"]],
                "differences": sum(not result["same"] for result in rows),
            }
        )
    return comparisons


@never_cache
@require_POST
def adjudicate_audit(request, review_id, submission_id, criterion):
    from .validation import ADJUDICATIONS

    classification = request.POST.get("classification", "")
    reason = request.POST.get("reason", "").strip()
    if (
        criterion not in BY_ID
        or criterion in REMINDER_CHECKS
        or classification not in ADJUDICATIONS
        or not reason
        or len(reason) > 5000
    ):
        return HttpResponse(
            "Choose a classification and give a reason for an assessed check.",
            status=400,
        )

    def change(review):
        if not audit_overview(review)["comparison_ready"] or request.POST.get(
            "basis"
        ) != comparison_token(review):
            raise ValueError(
                "The comparison changed. Reload before saving the decision."
            )
        item = get_submission(review, submission_id)
        audit = item["validation_audits"][-1]
        item.setdefault("audit_adjudications", []).append(
            {
                "at": store.now(),
                "audit_at": audit["at"],
                "criterion": criterion,
                "classification": classification,
                "reason": reason,
            }
        )

    try:
        store.update(str(review_id), change)
    except ValueError as error:
        return HttpResponse(str(error), status=409)
    return redirect(
        reverse("moderation:validation_comparison", args=[review_id])
        + "#comparison-"
        + str(submission_id)
    )


@never_cache
@require_GET
def validation_comparison(request, review_id):
    data = get_review(review_id)
    state = audit_overview(data)
    if not state["comparison_ready"]:
        return render(
            request,
            "moderation/validation_comparison.html",
            {
                "review": data,
                **state,
            },
            status=403,
        )
    from .validation import historical_adjudications

    historical_error = ""
    try:
        historical = historical_adjudications(data)
    except ValueError as error:
        historical = []
        historical_error = str(error)
    comparisons = validation_comparisons(state, historical)
    statistics = check_statistics(comparisons)
    version = checking_version()
    for stat in statistics:
        for stratum in stat["strata"]:
            approval = shared_approvals.approvals(data).get(
                f"{stat['id']}:{stratum['source']}", {}
            )
            stratum["approved"] = bool(
                approval.get("version") == version
                and approval.get("reference")
                and stratum["version"] == version
            )
            stratum["can_approve"] = (
                stratum["source"] in {"Rule", "AI"}
                and stratum["version"] == version
                and stratum["compared"] > 0
                and (
                    stratum["source"] != "AI"
                    or stratum["model"] == os.getenv("OPENAI_MODEL", "gpt-5-mini")
                )
            )
        stat["has_approval"] = any(group["approved"] for group in stat["strata"])
    return render(
        request,
        "moderation/validation_comparison.html",
        {
            "review": data,
            **state,
            "comparisons": comparisons,
            "historical_error": historical_error,
            "check_statistics": statistics,
            "comparison_token": comparison_token(data),
            "approval_saved": request.GET.get("approval") in {"approve", "revoke"},
            "difference_count": sum(row["differences"] for row in comparisons),
            "check_count": sum(len(row["rows"]) for row in comparisons),
        },
    )


@require_POST
def approve_check(request, review_id, criterion):
    data = get_review(review_id)
    if criterion not in BY_ID or criterion in REMINDER_CHECKS:
        raise Http404("Check not available for validation approval.")
    source = request.POST.get("source")
    action = request.POST.get("action")
    version = request.POST.get("version")
    basis = request.POST.get("basis")
    note = request.POST.get("note", "").strip()
    if (
        source not in {"Rule", "AI"}
        or action not in {"approve", "revoke"}
        or len(note) > 2000
    ):
        return HttpResponse(
            "Choose a valid approval action and keep the note within 2,000 characters.",
            status=400,
        )

    def change(review):
        state = audit_overview(review)
        if (
            not state["comparison_ready"]
            or version != checking_version()
            or basis != comparison_token(review)
        ):
            raise ValueError(
                "The audit selection, results or checking version changed. Reload the comparison before recording approval."
            )
        statistic = next(
            stat
            for stat in check_statistics(validation_comparisons(state))
            if stat["id"] == criterion
        )
        groups = [
            group
            for group in statistic["strata"]
            if group["source"] == source and group["version"] == version
        ]
        if not groups or (
            action == "approve"
            and not any(
                group["compared"] > 0
                and (
                    source != "AI"
                    or group["model"] == os.getenv("OPENAI_MODEL", "gpt-5-mini")
                )
                for group in groups
            )
        ):
            raise ValueError(
                "Approval requires audited definite outcomes for this source and the current checking version/model. Older or unversioned results cannot approve the current version."
            )
        key = f"{criterion}:{source}"
        approvals = review.setdefault("automation_approvals", {})
        previous = copy.deepcopy(approvals.get(key))
        if action == "revoke":
            if not previous:
                return
            approvals.pop(key)
        else:
            if (
                previous
                and previous.get("version") == version
                and previous.get("basis") == basis
                and previous.get("note", "") == note
            ):
                return
            reference = f"Independent audits in batch {review['id']}; {criterion} ({source}); evidence {basis}."
            approvals[key] = {
                "version": version,
                "reference": reference,
                "at": store.now(),
                "basis": basis,
                "note": note,
            }
        review.setdefault("review_process_history", []).append(
            {
                "action": action,
                "key": key,
                "version": version,
                "basis": basis,
                "note": note,
                "at": store.now(),
                "previous_approval": previous,
                "approval": copy.deepcopy(approvals.get(key)),
            }
        )

    try:
        store.update(str(data["id"]), change)
    except ValueError as error:
        return HttpResponse(str(error), status=409)
    saved = store.load(str(data["id"]))
    approval = saved.get("automation_approvals", {}).get(f"{criterion}:{source}", {})
    shared_approvals.set_approval(
        f"{criterion}:{source}",
        action,
        version,
        approval.get("reference", ""),
        approval.get("note", ""),
        origin={"review_id": str(data["id"]), "basis": basis},
    )
    return redirect(
        reverse("moderation:validation_comparison", args=[review_id])
        + f"?approval={action}#stat-{criterion}"
    )


@require_POST
def resume(request, review_id):
    data = get_review(review_id)
    action = request.POST.get("action", "resume")
    if data["state"] in {"running", "queued"}:
        return redirect("moderation:review", review_id=review_id)
    if action in {"ai", "retry_ai"} and not os.getenv("OPENAI_API_KEY"):
        return HttpResponse("Configure OPENAI_API_KEY first.", status=400)

    def change(review):
        review.update(state="queued", error="")
        if action in {"ai", "retry_ai"}:
            review["use_ai"] = True
            for item in select_attempts(review).active:
                if (
                    action == "ai"
                    or item["ai"]["state"] == "failed"
                    or any(
                        item["ai"].get(f"{key}_pending")
                        for key in eligible_ai_checks(item["checks"])
                    )
                ):
                    item["state"] = "pending"

    store.update(str(review_id), change)
    jobs.start(str(review_id))
    return redirect("moderation:review", review_id=review_id)


@require_GET
def download(request, review_id, submission_id, file_id):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
    file = next((f for f in item["files"] if f["id"] == str(file_id)), None)
    if not file:
        raise Http404()
    response = FileResponse(
        (store.review_dir(review_id) / file["id"]).open("rb"),
        as_attachment=True,
        filename=file["name"].replace("\\", "/").split("/")[-1],
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def image(request, review_id, submission_id, doc_index, image_index):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
    try:
        doc = item["documents"][doc_index]
        target = list(
            dict.fromkeys(path for p in doc["paragraphs"] for path in p["images"])
        )[image_index]
        file = next(f for f in item["files"] if f["name"] == doc["filename"])
        mime = mimetypes.guess_type(target)[0]
        if mime not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            raise Http404()
        source = (store.review_dir(review_id) / file["id"]).read_bytes()
        if doc.get("converted_from") == "doc":
            from .legacy_word import convert_legacy_doc

            source = convert_legacy_doc(source)
        if doc["kind"] == "pdf":
            import pymupdf

            match = re.fullmatch(r"pdf-image-(\d+)\.png", target)
            if match is None:
                raise Http404()
            with pymupdf.open(stream=source, filetype="pdf") as pdf:
                extracted = pdf.extract_image(int(match[1]))
                if (
                    not extracted
                    or extracted["width"] * extracted["height"] > 16_000_000
                ):
                    raise Http404()
                pixmap = pymupdf.Pixmap(extracted["image"])
                if pixmap.colorspace is None:
                    raise Http404()
                if pixmap.colorspace.n > 3:
                    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
                if extracted.get("smask") and not pixmap.alpha:
                    mask_image = pdf.extract_image(extracted["smask"])
                    if not mask_image or (
                        mask_image["width"],
                        mask_image["height"],
                    ) != (extracted["width"], extracted["height"]):
                        raise Http404()
                    mask = pymupdf.Pixmap(mask_image["image"])
                    pixmap = pymupdf.Pixmap(pixmap, mask)
                payload = pixmap.tobytes("png")
        elif match := re.fullmatch(r"word-drawing-(\d+)\.png", target):
            payload = word_drawing_png(source, int(match[1]))
        else:
            with bounded_zip(source, 80 * 1024 * 1024) as archive:
                payload = archive.read(target)
    except (
        IndexError,
        KeyError,
        StopIteration,
        ValueError,
        RuntimeError,
        zipfile.BadZipFile,
    ):
        raise Http404() from None
    response = HttpResponse(payload, content_type=mime)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@require_GET
def export(request, review_id, kind):
    data = get_review(review_id)
    if kind not in {"xlsx", "csv"}:
        raise Http404()
    try:
        payload = xlsx_bytes(data) if kind == "xlsx" else csv_bytes(data)
    except ValueError as error:
        return HttpResponse(str(error), status=400)
    response = HttpResponse(
        payload,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if kind == "xlsx"
        else "text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="moderation-{review_id}.{kind}"'
    )
    return response
