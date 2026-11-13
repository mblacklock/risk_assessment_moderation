import mimetypes
import os
import zipfile

from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from . import jobs, store
from .criteria import BY_ID, CRITERIA, STATUSES, effective_status, overall
from .documents import bounded_zip
from .exports import csv_bytes, xlsx_bytes
from .forms import DecisionForm, UploadForm


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


def decorated(check):
    return {
        **check,
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
            "checklist_count": len(CRITERIA),
        },
    )


@require_GET
def review(request, review_id):
    data = get_review(review_id)
    category = request.GET.get("category", "")
    status = request.GET.get("status", "")
    criterion = request.GET.get("criterion", "")
    if criterion not in BY_ID or (
        category and BY_ID[criterion]["category"] != category
    ):
        criterion = ""
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "name")
    descending = request.GET.get("direction") == "desc"
    columns = [
        BY_ID[key]
        for key, _, cat in CRITERIA
        if (not category or category == cat) and (not criterion or criterion == key)
    ]
    rows = []
    totals = {key: 0 for key in STATUSES}
    for item in data["submissions"]:
        state = overall(item["checks"]) if item["checks"] else "pending"
        present = {effective_status(c) for c in item["checks"]}
        for outcome in present - {"complete"}:
            totals[outcome] += 1
        if state == "complete":
            totals["complete"] += 1
        checks = {c["id"]: decorated(c) for c in item["checks"]}
        cells = [
            checks.get(
                col["id"],
                {"id": col["id"], "effective": "pending", "status_label": "Pending"},
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
        if status and not any(c["effective"] == status for c in cells):
            continue
        rows.append(
            {
                **item,
                "cells": cells,
                "outcome": state,
                "outcome_label": STATUSES.get(state, "Pending"),
                "flag_count": sum(
                    effective_status(c) != "complete" for c in item["checks"]
                ),
            }
        )

    def sorting(row):
        if sort == "issues":
            return row["flag_count"], row["name"].casefold()
        if sort in BY_ID:
            cell = next((c for c in row["checks"] if c["id"] == sort), None)
            return (
                {"issue": 0, "unable": 1, "review": 2, "complete": 3}.get(
                    effective_status(cell), 4
                )
                if cell
                else 4,
                row["name"].casefold(),
            )
        return row.get(
            sort if sort in {"name", "number", "submitted"} else "name", ""
        ).casefold()

    rows.sort(key=sorting, reverse=descending)
    return render(
        request,
        "moderation/review.html",
        {
            "review": data,
            "rows": rows,
            "columns": columns,
            "totals": totals,
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
        },
    )


@require_GET
def progress(request, review_id):
    data = get_review(review_id)
    return JsonResponse(
        {
            "state": data["state"],
            "done": sum(s["state"] == "done" for s in data["submissions"]),
            "total": len(data["submissions"]),
            "updated": data["updated"],
        }
    )


@require_GET
def submission(request, review_id, submission_id):
    data = get_review(review_id)
    item = get_submission(data, submission_id)
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
    for check in item["checks"]:
        extracts = []
        for extract in check["evidence"]:
            displayed = {
                **extract,
                "images": paragraph_images.get(extract["location"], []),
            }
            if displayed not in extracts:
                extracts.append(displayed)
        checks.append(decorated({**check, "evidence": extracts}))
    return render(
        request,
        "moderation/submission.html",
        {
            "review": data,
            "submission": item,
            "checks": checks,
            "documents": documents,
            "editable": data["state"] not in {"running", "queued"},
            "statuses": STATUSES,
        },
    )


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
    form = DecisionForm(request.POST)
    if not form.is_valid():
        return HttpResponse(
            "Choose a valid outcome and add a note when overriding a result.",
            status=400,
        )

    def change(review):
        target = get_submission(review, submission_id)
        check = next(c for c in target["checks"] if c["id"] == criterion)
        check.setdefault("history", []).append(
            {
                "decision": form.cleaned_data["decision"],
                "note": form.cleaned_data["note"],
                "at": store.now(),
            }
        )
        check.update(
            decision=form.cleaned_data["decision"],
            note=form.cleaned_data["note"],
            decided_at=store.now(),
        )

    store.update(str(review_id), change)
    return redirect(
        reverse(
            "moderation:submission",
            kwargs={"review_id": review_id, "submission_id": submission_id},
        )
        + "#"
        + criterion
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
            for item in review["submissions"]:
                if (
                    action == "ai"
                    or item["ai"]["state"] == "failed"
                    or item["ai"].get("facilities_pending")
                    or item["ai"].get("entry_quality_pending")
                    or item["ai"].get("location_pending")
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
        with bounded_zip(
            (store.review_dir(review_id) / file["id"]).read_bytes(), 80 * 1024 * 1024
        ) as archive:
            payload = archive.read(target)
    except (IndexError, KeyError, StopIteration, ValueError, zipfile.BadZipFile):
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
    payload = xlsx_bytes(data) if kind == "xlsx" else csv_bytes(data)
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
