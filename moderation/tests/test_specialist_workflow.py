import io
from unittest.mock import patch

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from moderation import jobs, store
from moderation.checks import check_documents
from moderation.criteria import effective_status, overall
from moderation.documents import extract_document
from moderation.exports import csv_bytes, xlsx_bytes
from moderation.tests.test_review import STUDENT, archive_bytes, document_bytes
from moderation.workflow import finding_fingerprint, review_progress


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ("No", "complete"),
        ("Yes", "supervisor"),
        ("N for water, Y if chemicals are used", "supervisor"),
        ("", "issue"),
        ("Y/N? Please list reference No: N", "issue"),
        ("unclear", "moderator"),
        ("Y and N", "moderator"),
        ("Maybe", "moderator"),
    ],
)
def test_specialist_outcomes_separate_followup_from_completion_and_reading(
    answer, status
):
    checks, _ = check_documents(
        [extract_document(document_bytes(specialist=answer), "synthetic.docx")], STUDENT
    )
    check = next(c for c in checks if c["id"] == "specialists")
    assert check["status"] == status
    assert overall([check]) == status


def test_missing_answer_still_issue_when_another_specialist_is_yes():
    document = extract_document(document_bytes(specialist="Yes"), "synthetic.docx")
    for p in document["paragraphs"]:
        if p["text"].startswith("Manual Handling:"):
            p["text"] = "Manual Handling: Y/N Please list reference No: No"
    checks, _ = check_documents([document], STUDENT)
    check = next(c for c in checks if c["id"] == "specialists")
    assert check["status"] == "issue"
    assert "Supervisor" in check["message"] and "Unanswered" in check["message"]


def test_supervisor_followup_moderation_export_and_saved_migration(
    settings, tmp_path, client
):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        r = jobs.create_review(
            archive_bytes(document_bytes(specialist="Yes")),
            "Synthetic follow-up",
            False,
        )
    jobs.run(r["id"])
    r = store.load(r["id"])
    item = r["submissions"][0]
    item.pop("specialist_followup_version")
    old = next(c for c in item["checks"] if c["id"] == "specialists")
    old.update(
        status="review",
        message="Locate and review supporting assessments: COSHH.",
        note="Feedback checked",
        decided_at="2026-11-16",
        reviewed_at="2026-11-16",
        history=[{"decision": "", "note": "Feedback checked"}],
    )
    old["reviewed_fingerprint"] = finding_fingerprint(old)
    store.save(r)
    with patch.object(jobs, "apply_ai") as ai:
        updated = jobs.snapshot(r["id"])
        ai.assert_not_called()
    check = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "specialists"
    )
    assert check["status"] == "supervisor"
    assert (
        review_progress(check)["reviewed"] and review_progress(check)["review_resolved"]
    )
    assert (
        not review_progress(check)["needs_review"]
        and not review_progress(check)["review_unresolved"]
    )
    assert check["history"] == old["history"] and check["note"] == old["note"]
    assert check["superseded_specialist_finding"] == old
    assert jobs.snapshot(r["id"]) == updated
    assert b"Supervisor check" in csv_bytes(updated)
    workbook = load_workbook(io.BytesIO(xlsx_bytes(updated)))
    assert any(
        "Supervisor check" in row
        for row in workbook["Findings and decisions"].iter_rows(values_only=True)
    )
    page = client.get(
        reverse("moderation:review", args=[r["id"]]),
        {"criterion": "specialists", "status": "supervisor"},
    )
    assert len(page.context["rows"]) == 1 and page.context["supervisor_count"] == 1
    assert b"Supervisor check" in page.content
    page = client.get(
        reverse("moderation:review", args=[r["id"]]),
        {"criterion": "specialists", "needs_review": "on"},
    )
    assert page.context["rows"] == []
    response = client.post(
        reverse("moderation:decide", args=[r["id"], item["id"], "specialists"]),
        {
            "decision": "supervisor",
            "note": "",
            "action": "next",
            "grid": "criterion=specialists",
        },
    )
    assert response.status_code == 302
    current = next(
        c
        for c in store.load(r["id"])["submissions"][0]["checks"]
        if c["id"] == "specialists"
    )
    assert (
        effective_status(current) == "supervisor"
        and review_progress(current)["reviewed"]
    )


@pytest.mark.parametrize("whitespace", ["\n", "\r\n", "\t", " \n  "])
def test_unchanged_multiline_specialist_options_are_unanswered_not_uninterpretable(
    whitespace,
):
    from moderation.checks import SPECIALISTS

    doc = extract_document(document_bytes(), "synthetic.docx")
    for p in doc["paragraphs"]:
        label = next(
            (label for label in SPECIALISTS if p["text"].startswith(label + ":")), None
        )
        if label:
            p["text"] = label + ": Y/N?" + whitespace + "Please list reference No:"
    checks, _ = check_documents([doc], STUDENT)
    finding = next(c for c in checks if c["id"] == "specialists")
    assert finding["status"] == "issue"
    assert "Unanswered specialist questions" in finding["message"]
    assert "Select Yes or No in each primary answer field" in finding["message"]
    assert "unclear" not in finding["message"]
    assert all(label in finding["message"] for label in SPECIALISTS)
