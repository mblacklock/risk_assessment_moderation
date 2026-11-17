import io
import zipfile
from concurrent.futures import Future
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from moderation import jobs, store
from moderation.attempts import select_attempts, submission_timestamp
from moderation.exports import csv_bytes, xlsx_bytes
from moderation.tests.test_review import document_bytes


def attempt(stamp, assessment="assignment", number="w12345678"):
    return {
        "number": number,
        "submitted": stamp,
        "attempt": f"{assessment}_{number}_attempt.txt",
    }


@pytest.mark.parametrize(
    ("raw", "hour"),
    [
        ("Thursday, 22 October 2026 14:41:56 o'clock BST", 13),
        ("15 November 2026 14:41:56 GMT", 14),
        ("2026-10-22T14:41:56+01:00", 13),
    ],
)
def test_submission_times(raw, hour):
    assert submission_timestamp(attempt(raw)) == datetime(
        2026,
        10 if hour == 13 else 11,
        22 if hour == 13 else 15,
        hour,
        41,
        56,
        tzinfo=timezone.utc,
    )


def test_filename_timestamp_and_ambiguous_clock():
    assert (
        submission_timestamp(
            {"attempt": "assignment_w12345678_attempt_2026-10-22-14-41-56.txt"}
        ).hour
        == 13
    )
    assert submission_timestamp(attempt("25 October 2026 01:30:00")) is None


def test_selection_preserves_assessments_and_uncertain_attempts():
    old, new = attempt("2026-11-01T12:00:00Z"), attempt("2026-11-02T12:00:00Z")
    other = attempt("2026-10-01T12:00:00Z", assessment="ethics")
    selection = select_attempts({"latest_only": True, "submissions": [old, new, other]})
    assert selection.active == [new, other]
    assert selection.earlier == [old]
    tied = select_attempts({"latest_only": True, "submissions": [old, new, dict(new)]})
    assert len(tied.active) == 2 and tied.warnings
    missing = select_attempts(
        {"latest_only": True, "submissions": [old, attempt("unknown")]}
    )
    assert len(missing.active) == 2 and missing.warnings
    unknown = select_attempts(
        {"latest_only": True, "submissions": [attempt("", number="Unknown")]}
    )
    assert len(unknown.active) == 1 and unknown.warnings
    assert select_attempts({"submissions": [old, new]}).active == [old, new]


@pytest.fixture
def attempt_review(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    output = io.BytesIO()
    doc = document_bytes()
    with zipfile.ZipFile(output, "w") as archive:
        for day in (1, 2):
            files = [f"ra-{day}.docx", f"ethics-{day}.docx"]
            for filename in files:
                archive.writestr(filename, doc)
            archive.writestr(
                f"assignment_w12345678_attempt_2026-11-0{day}-12-00-00.txt",
                f"Name: Synthetic Student (w12345678)\nDate Submitted: 0{day} November 2026 12:00:00 GMT\nFiles:\n"
                + "".join(f"Filename: {name}\n" for name in files),
            )
    with patch.object(jobs, "start"):
        review = jobs.create_review(
            output.getvalue(), "Attempts", True, latest_only=True
        )
    with patch.object(jobs, "apply_ai", return_value={"state": "done"}) as ai:
        jobs.run(review["id"])
    assert ai.call_count == 1
    return store.load(review["id"])


def test_latest_processing_counts_exports_and_retained_sources(attempt_review, client):
    review = attempt_review
    old, latest = review["submissions"]
    assert old["state"] == "pending" and not old["checks"]
    assert latest["state"] == "done" and len(latest["documents"]) == 2
    assert all(
        (store.review_dir(review["id"]) / f["id"]).exists()
        for s in review["submissions"]
        for f in s["files"]
    )
    url = reverse("moderation:review", args=[review["id"]])
    page = client.get(url)
    assert len(page.context["rows"]) == 1
    assert page.context["earlier_attempts"][0]["id"] == old["id"]
    assert (
        client.get(reverse("moderation:progress", args=[review["id"]])).json()["total"]
        == 1
    )
    assert store.list_reviews()[0]["count"] == 1
    assert b"ra-1.docx" not in csv_bytes(review) and b"ra-2.docx" in csv_bytes(review)
    assert load_workbook(io.BytesIO(xlsx_bytes(review))).active.max_row == 2
    source = client.get(
        reverse("moderation:submission", args=[review["id"], old["id"]])
    )
    assert source.context["excluded_attempt"]
    assert (
        client.get(
            reverse(
                "moderation:download",
                args=[review["id"], old["id"], old["files"][0]["id"]],
            )
        ).status_code
        == 200
    )


def test_selection_changes_do_not_run_ai_and_preserve_decisions(attempt_review, client):
    review = attempt_review
    latest = review["submissions"][1]
    latest["checks"][0].update(
        decision="complete", note="Staff review", history=[{"note": "Retain"}]
    )
    store.save(review)
    url = reverse("moderation:attempt_selection", args=[review["id"]])
    with patch.object(jobs, "start") as start, patch.object(jobs, "apply_ai") as ai:
        assert client.post(url, {}).status_code == 302
        changed = store.load(review["id"])
        assert not changed["latest_only"]
        assert changed["submissions"] == review["submissions"]
        page = client.get(reverse("moderation:review", args=[review["id"]]))
        assert page.context["unprocessed_count"] == 1
        assert len(page.context["rows"]) == 2
        client.post(url, {"latest_only": "on"})
        client.post(url, {"latest_only": "on"})
        assert store.load(review["id"])["submissions"] == review["submissions"]
        start.assert_not_called()
        ai.assert_not_called()
    store.update(review["id"], lambda r: r.update(state="running"))
    with patch.dict(jobs.ACTIVE, {review["id"]: Future()}):
        client.post(url, {})
    assert store.load(review["id"])["latest_only"]


def test_ai_reruns_only_selected_attempts(attempt_review, client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    review = attempt_review
    old = review["submissions"][0]
    old["state"] = "done"
    old["ai"] = {"state": "failed", "message": "Earlier failure"}
    store.save(review)
    old = jobs.snapshot(review["id"])["submissions"][0]
    with patch.object(jobs, "start"):
        client.post(reverse("moderation:resume", args=[review["id"]]), {"action": "ai"})
    queued = store.load(review["id"])
    assert queued["submissions"][0] == old
    assert queued["submissions"][1]["state"] == "pending"
    with patch.object(jobs, "apply_ai", return_value={"state": "done"}) as ai:
        jobs.run(review["id"])
    assert ai.call_count == 1
    assert store.load(review["id"])["submissions"][0] == old


def test_upload_default_and_explicit_selection(client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from moderation.forms import UploadForm

    assert UploadForm()["latest_only"].value() is True
    with patch.object(
        jobs,
        "create_review",
        return_value={"id": "00000000-0000-0000-0000-000000000001"},
    ) as create:
        response = client.post(
            reverse("moderation:index"),
            {
                "title": "Latest upload",
                "archive": SimpleUploadedFile(
                    "sample.zip", b"sample", content_type="application/zip"
                ),
                "latest_only": "on",
            },
        )
    assert response.status_code == 302
    assert create.call_args.args[3] is True
