import io
from unittest.mock import patch

import pytest
from docx import Document

from moderation import jobs, store
from moderation.checks import check_documents
from moderation.documents import extract_document
from moderation.tests.test_review import STUDENT, archive_bytes, document_bytes


def declaration_document(unselected=None, omit_retention=False):
    doc = Document(io.BytesIO(document_bytes()))
    for p in list(doc.paragraphs):
        if any(
            t in p.text
            for t in ("I confirm compliance", "I confirm I read", "I confirm mandatory")
        ):
            p._element.getparent().remove(p._element)
    anchor = next(p for p in doc.paragraphs if p.text == "Physical Risk Involved")
    statements = [
        "I confirm that I will comply with the University's data retention schedule and guidance.",
        "I confirm I have read the university's health and safety policy and ethics policy and understood mandatory completion of risk assessments.",
        "I confirm I have read the University's Ethics policy and Data Management policy.",
    ]
    for index, text in enumerate(statements):
        if index == 0 and omit_retention:
            continue
        anchor.insert_paragraph_before(
            ("☐" if index == unselected else "☒") + " " + text
        )
    # A selected supervisor statement must not fill a missing student declaration.
    anchor.insert_paragraph_before(
        "☒ I confirm that I reviewed the content of this form and agreed with the information provided."
    )
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


@pytest.mark.parametrize("unselected", [None, 0, 1, 2])
def test_retention_template_checks_all_three_actual_selections(unselected):
    checks, _ = check_documents(
        [extract_document(declaration_document(unselected), "synthetic.docx")], STUDENT
    )
    check = next(c for c in checks if c["id"] == "declarations")
    assert check["status"] == ("complete" if unselected is None else "issue")
    assert len(check["evidence"]) == 3
    assert any("retention schedule" in e["text"] for e in check["evidence"])


def test_missing_student_declaration_not_filled_by_supervisor_statement():
    checks, _ = check_documents(
        [extract_document(declaration_document(omit_retention=True), "synthetic.docx")],
        STUDENT,
    )
    assert next(c for c in checks if c["id"] == "declarations")["status"] == "issue"


def test_declaration_refresh_keeps_staff_decisions_and_originals(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    data = declaration_document()
    with patch.object(jobs, "start"):
        review = jobs.create_review(
            archive_bytes(data), "Synthetic declarations", False
        )
    jobs.run(review["id"])
    review = store.load(review["id"])
    item = review["submissions"][0]
    item.pop("declarations_version")
    old = next(c for c in item["checks"] if c["id"] == "declarations")
    old.update(
        status="issue",
        message="All three must be selected.",
        decision="review",
        note="Staff note",
        history=[{"note": "Retain"}],
    )
    store.save(review)
    with patch.object(jobs, "apply_ai") as ai:
        updated = jobs.snapshot(review["id"])
        ai.assert_not_called()
    check = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "declarations"
    )
    assert check["status"] == "complete"
    assert check["note"] == old["note"] and check["history"] == old["history"]
    assert check["superseded_declarations_finding"] == old
    assert jobs.snapshot(review["id"]) == updated
    assert (
        store.review_dir(review["id"]) / item["files"][0]["id"]
    ).read_bytes() == data
