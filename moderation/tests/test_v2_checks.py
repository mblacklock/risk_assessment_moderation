"""Synthetic regressions for changes after the frozen evaluation baseline."""

import io

import pytest
from docx import Document

from moderation.checks import (
    assessor_matches,
    check_documents,
    field,
    rating_checks,
    rating_entries,
)
from moderation.documents import extract_document
from moderation.tests.test_multi_ratings import row
from moderation.tests.test_review import STUDENT, document_bytes


@pytest.mark.parametrize(
    ("entered", "expected", "matches"),
    [
        ("Alex Morgan", "Alex Morgan", True),
        ("Alex James Morgan", "Alex Morgan", True),
        ("Alex James de Silva", "Alex de Silva", True),
        ("Alex James Smith-Jones", "Alex Smith-Jones", True),
        ("Alex James Silva", "Alex de Silva", False),
        ("Alex James Jones", "Alex Morgan", False),
        ("Alex Morgan", "Alexander Morgan", False),
        ("A Morgan", "Alex Morgan", False),
        ("Alex", "Alex Morgan", False),
        ("Alex Jones", "Alex Morgan", False),
        ("", "Alex Morgan", False),
    ],
)
def test_inserted_middle_names_preserve_first_and_full_surname(
    entered, expected, matches
):
    assert assessor_matches(entered, expected) is matches


@pytest.mark.parametrize(
    "next_text", ["Risk Rating", "Risk Rating H 20–36", "Severity"]
)
def test_blank_title_does_not_borrow_table_heading(next_text):
    paragraphs = [{"text": "Assessment Title:"}, {"text": next_text}]
    assert field(paragraphs, "Assessment Title") == ("", paragraphs[0])


def test_blank_title_allows_separate_answer_paragraph():
    paragraphs = [{"text": "Assessment Title:"}, {"text": "Synthetic material testing"}]
    assert field(paragraphs, "Assessment Title") == (
        paragraphs[1]["text"],
        paragraphs[1],
    )


@pytest.mark.parametrize(
    ("entered", "scores"),
    [
        ("L – 4", [4]),
        ("L 6", [6]),
        ("4 [L]", [4]),
        ("[L] 4", [4]),
        ("4\n(L)", [4]),
        ("4\n[L]\n2\n(L)", [4, 2]),
        ("2x2=4\n(L)", [4]),
        ("L1–3", None),
        ("5 (5)", None),
        ("2x1 (L)", None),
        ("4\n(L)\n(H)", None),
        ("L 4 H", None),
    ],
)
def test_readable_formats_and_technical_defects(entered, scores):
    assert rating_entries(entered) == scores


@pytest.mark.parametrize("persons", ["1", "1–3", "1 / 3", "Student", "2 technicians"])
def test_persons_at_risk_identifies_people_not_just_counts(persons):
    doc = Document(io.BytesIO(document_bytes()))
    doc.tables[0].cell(1, 3).text = persons
    stream = io.BytesIO()
    doc.save(stream)
    checks, _ = check_documents(
        [extract_document(stream.getvalue(), "case.docx")], STUDENT
    )
    check = next(c for c in checks if c["id"] == "risk_table")
    assert check["status"] == (
        "complete" if any(c.isalpha() for c in persons) else "issue"
    )
    if check["status"] == "issue":
        assert "Persons at risk" in check["message"]


@pytest.mark.parametrize("separate_answer", [False, True])
def test_generic_name_in_scoped_supervisor_signoff(separate_answer):
    data = document_bytes()
    doc = Document(io.BytesIO(data))
    for paragraph in doc.paragraphs:
        if paragraph.text.startswith(
            "Supervisor Name: Synthetic Supervisor    Job Title:"
        ):
            paragraph.text = paragraph.text.replace("Supervisor Name:", "Name:")
            if separate_answer:
                paragraph.text = "Name:"
                paragraph.insert_paragraph_before("Unrelated preceding text")
                # Insert a genuine following answer, preserving the role section.
                answer = doc.add_paragraph(
                    "Synthetic Supervisor    Job Title: Lecturer"
                )
                paragraph._p.addnext(answer._p)
    stream = io.BytesIO()
    doc.save(stream)
    checks, _ = check_documents(
        [extract_document(stream.getvalue(), "case.docx")], STUDENT
    )
    assert next(c for c in checks if c["id"] == "supervisor_ra")["status"] == "complete"


def test_unused_row_does_not_block_valid_comparison_or_renumber_rows():
    unused = ["1", "N/A", "", "", "", "", "", "", ""]
    ratings, reduction = rating_checks([unused, row(final="12\n4")])
    assert ratings["status"] == "complete"
    assert reduction["status"] == "issue"
    assert "Row 2, entry 1: initial 12, final 12" in reduction["message"]
    assert "unused/N/A rows: 1" in ratings["message"]


def test_all_unused_rows_are_skipped_not_passed():
    checks = rating_checks([["1", "N/A", "", "", "", "", "", "", ""]])
    assert all(c["status"] == "skipped" for c in checks)


def test_partially_assessed_row_with_na_is_not_ignored():
    assessed = row(severity="2", likelihood="3", initial="6", final="N/A")
    ratings, reduction = rating_checks([assessed])
    assert ratings["status"] == "issue"
    assert "Final Result" in ratings["message"]
    assert reduction["status"] == "skipped"


def test_unused_row_cleanup_is_moderator_judgement_not_missing_ratings():
    doc = Document(io.BytesIO(document_bytes()))
    cells = doc.tables[0].add_row().cells
    cells[0].text, cells[1].text = "2", "N/A"
    stream = io.BytesIO()
    doc.save(stream)
    checks, _ = check_documents(
        [extract_document(stream.getvalue(), "case.docx")], STUDENT
    )
    checks = {c["id"]: c for c in checks}
    assert checks["risk_table"]["status"] == "review"
    assert "cleanup" in checks["risk_table"]["message"]
    assert (
        checks["ratings"]["status"] == checks["risk_reduction"]["status"] == "complete"
    )
