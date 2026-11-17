import copy
import io
from unittest.mock import patch

import pytest
from docx import Document

from moderation import jobs, store
from moderation.checks import check_documents
from moderation.documents import extract_document
from moderation.tests.test_review import STUDENT, archive_bytes, document_bytes
from moderation.workflow import review_progress


def missing_document(columns, rows=1):
    doc = Document(io.BytesIO(document_bytes()))
    table = doc.tables[0]
    original = [cell.text for cell in table.rows[1].cells]
    for _ in range(rows - 1):
        row = table.add_row()
        for cell, text in zip(row.cells, original, strict=True):
            cell.text = text
    for index, row in enumerate(table.rows[1:], 1):
        row.cells[0].text = str(index)
        for column in columns:
            row.cells[column].text = ""
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def findings(data):
    checks, _ = check_documents([extract_document(data, "synthetic.docx")], STUDENT)
    return {c["id"]: c for c in checks}


def test_blank_final_scores_reported_only_under_ratings_with_student_instructions():
    checks = findings(missing_document([8], rows=3))
    assert checks["risk_table"]["status"] == "complete"
    assert checks["ratings"]["status"] == "issue"
    message = checks["ratings"]["message"]
    for index in range(1, 4):
        assert (
            f"Row {index}: enter a numeric value for Final Result (post-control score)."
            in message
        )
    assert "final score alone is sufficient" in message
    assert "multiplication expression is optional" in message
    assert checks["risk_reduction"]["status"] == "skipped"
    assert checks["risk_reduction"]["blocked_by"] == "ratings"
    assert not review_progress(checks["risk_reduction"])["needs_review"]


@pytest.mark.parametrize(
    ("column", "label"),
    [
        (1, "Activity/equipment/materials"),
        (2, "Hazard"),
        (3, "Persons at risk"),
        (7, "Control Measures Required"),
    ],
)
def test_missing_description_names_exact_field_without_rating_failure(column, label):
    checks = findings(missing_document([column]))
    assert checks["risk_table"]["status"] == "issue"
    assert f"Row 1: complete {label}." in checks["risk_table"]["message"]
    assert checks["ratings"]["status"] == "complete"


@pytest.mark.parametrize(
    ("column", "label"),
    [
        (4, "Severity"),
        (5, "Likelihood"),
        (6, "Risk Rating (initial score)"),
        (8, "Final Result (post-control score)"),
    ],
)
def test_missing_rating_field_not_duplicated_as_table_completion_defect(column, label):
    checks = findings(missing_document([column]))
    assert checks["risk_table"]["status"] == "complete"
    assert checks["ratings"]["status"] == "issue"
    assert label in checks["ratings"]["message"]


def test_known_nonreducing_score_not_hidden_by_missing_score_in_another_row():
    from moderation.checks import rating_checks

    rows = [
        ["1", "Activity", "Hazard", "Student", "2", "3", "6", "Controls", ""],
        ["2", "Activity", "Hazard", "Student", "2", "3", "6", "Controls", "6"],
    ]
    ratings, reduction = rating_checks(rows)
    assert ratings["status"] == reduction["status"] == "issue"
    assert "Row 2: initial 6, final 6" in reduction["message"]


def test_saved_scope_refresh_preserves_decisions_and_other_findings(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    source = missing_document([8], rows=3)
    with patch.object(jobs, "start"):
        r = jobs.create_review(archive_bytes(source), "Synthetic completion", False)
    jobs.run(r["id"])
    r = store.load(r["id"])
    item = r["submissions"][0]
    item.pop("risk_completion_version")
    old = next(c for c in item["checks"] if c["id"] == "risk_table")
    old.update(
        status="issue",
        message="Incomplete risk rows: 1, 2, 3",
        decision="complete",
        note="Staff checked",
        history=[{"note": "Retain"}],
    )
    other = copy.deepcopy(
        [
            c
            for c in item["checks"]
            if c["id"] not in {"risk_table", "ratings", "risk_reduction"}
        ]
    )
    store.save(r)
    with patch.object(jobs, "apply_ai") as ai:
        updated = jobs.snapshot(r["id"])
        ai.assert_not_called()
    checks = updated["submissions"][0]["checks"]
    current = next(c for c in checks if c["id"] == "risk_table")
    assert current["status"] == "complete"
    assert current["decision"] == old["decision"] and current["note"] == old["note"]
    assert current["history"] == old["history"]
    assert current["superseded_risk_completion_finding"] == old
    assert [
        c for c in checks if c["id"] not in {"risk_table", "ratings", "risk_reduction"}
    ] == other
    assert (store.review_dir(r["id"]) / item["files"][0]["id"]).read_bytes() == source
    assert jobs.snapshot(r["id"]) == updated
