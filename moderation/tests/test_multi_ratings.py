import io
from unittest.mock import patch

import pytest
from docx import Document

from moderation import jobs, store
from moderation.checks import check_documents, numeric_rating, rating_checks
from moderation.documents import extract_document
from moderation.tests.test_review import STUDENT, archive_bytes, document_bytes


def row(severity="4\n4", likelihood="3\n2", initial="12\n8", final="4x2=8\n4"):
    return [
        "1",
        "Testing",
        "Hazard one\nHazard two",
        "Student",
        severity,
        likelihood,
        initial,
        "Controls",
        final,
    ]


@pytest.mark.parametrize(
    ("values", "status", "fragment"),
    [
        ({}, "complete", "2 initial/final score pairs"),
        ({"final": "8\n8"}, "issue", "Row 1, entry 2: initial 8, final 8"),
        ({"final": "14\n4"}, "issue", "Row 1, entry 1: initial 12, final 14"),
        ({"final": "8\n4\n4"}, "issue", "2 initial and 3 final entries"),
        ({"severity": "4"}, "issue", "1 severity"),
        ({"final": "8\nunclear"}, "review", "manual review"),
        ({"final": ""}, "skipped", "missing or unreadable"),
        (
            {"initial": "12\n\n8\n", "final": "4x2=8\n\n4 (L)"},
            "complete",
            "2 initial/final score pairs",
        ),
    ],
)
def test_multiple_scores(values, status, fragment):
    ratings, reduction = rating_checks([row(**values)])
    assert reduction["status"] == status
    assert fragment in reduction["message"]
    assert "Final scores:" in reduction["evidence"][0]["text"]
    if status == "issue" and "entry" not in fragment:
        assert ratings["status"] == "issue"


def test_mismatch_does_not_hide_separate_failed_pair_or_skip_later_pairs():
    _, check = rating_checks([row(final="8\n4\n4"), row(final="12\n4")])
    assert check["status"] == "issue"
    assert (
        "Row 1:" in check["message"]
        and "Row 2, entry 1: initial 12, final 12" in check["message"]
    )


def test_multiple_equations_are_not_read_as_last_score_only():
    assert numeric_rating("4x2=8\n4x1=4") is None
    _, check = rating_checks([row(initial="12 8", final="8 4")])
    assert check["status"] == "review"


def multi_document():
    doc = Document(io.BytesIO(document_bytes()))
    for cell, value in zip(doc.tables[0].rows[1].cells, row(), strict=True):
        cell.text = value
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def test_word_multiline_cells_are_checked_without_splitting_hazard_prose():
    checks, extracted = check_documents(
        [extract_document(multi_document(), "synthetic.docx")], STUDENT
    )
    assert len(extracted["risk_rows"]) == 1
    check = next(c for c in checks if c["id"] == "risk_reduction")
    assert check["status"] == "complete"
    assert "2 initial/final score pairs" in check["message"]


def test_saved_multiple_ratings_refresh_without_ai_preserves_history(
    settings, tmp_path
):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    with patch.object(jobs, "start"):
        review = jobs.create_review(
            archive_bytes(multi_document()), "Synthetic ratings", False
        )
    jobs.run(review["id"])
    review = store.load(review["id"])
    item = review["submissions"][0]
    item["multi_rating_version"] = 1
    old = next(c for c in item["checks"] if c["id"] == "risk_reduction")
    old.update(
        status="unable",
        message="Cannot compare rows.",
        decision="review",
        note="Staff note",
        history=[{"note": "Retain"}],
    )
    other_checks = [
        c for c in item["checks"] if c["id"] not in {"ratings", "risk_reduction"}
    ]
    originals = [
        (store.review_dir(review["id"]) / f["id"]).read_bytes() for f in item["files"]
    ]
    store.save(review)
    with patch.object(jobs, "apply_ai") as ai:
        updated = jobs.snapshot(review["id"])
        ai.assert_not_called()
    checks = updated["submissions"][0]["checks"]
    check = next(c for c in checks if c["id"] == "risk_reduction")
    assert check["status"] == "complete"
    assert check["note"] == old["note"] and check["history"] == old["history"]
    assert check["superseded_multi_rating_finding"] == old
    assert [
        c for c in checks if c["id"] not in {"ratings", "risk_reduction"}
    ] == other_checks
    assert originals == [
        (store.review_dir(review["id"]) / f["id"]).read_bytes() for f in item["files"]
    ]
    assert jobs.snapshot(review["id"]) == updated


@pytest.mark.parametrize(
    "text", ["4L)", "4(L", "4 (L)", "4L", "2*2=4L)", "2x2=4(L", "2×2=4 (L)"]
)
def test_readable_score_tolerates_unbalanced_band_parenthesis(text):
    assert numeric_rating(text) == 4
    ratings, reduction = rating_checks(
        [row(severity="2", likelihood="4", initial="8(L)", final=text)]
    )
    assert ratings["status"] == reduction["status"] == "complete"
    assert text in reduction["evidence"][0]["text"]


@pytest.mark.parametrize(
    "text", ["4 or 8L)", "4L) 8", "2*2=4L)=8", "4unknown)", "4)", "4(L)\n8(L)"]
)
def test_parenthesis_tolerance_does_not_accept_extra_or_unclear_scores(text):
    assert numeric_rating(text) is None


@pytest.mark.parametrize(
    ("text", "score"),
    [
        ("6 (low)", 6),
        ("2 (LOW)", 2),
        ("12 (Medium)", 12),
        ("24 high", 24),
        ("3x2=6 (low)", 6),
        ("2 low)", 2),
    ],
)
def test_full_risk_band_words_do_not_make_numeric_scores_unreadable(text, score):
    assert numeric_rating(text) == score


def test_full_risk_band_words_allow_both_rows_to_be_compared():
    rows = [
        row(severity="2", likelihood="3", initial="6 (low)", final="2 (low)"),
        row(severity="3", likelihood="1", initial="3 (low)", final="1 (low)"),
    ]
    ratings, reduction = rating_checks(rows)
    assert ratings["status"] == reduction["status"] == "complete"
    assert "2 initial/final score pairs" in reduction["message"]
    assert "(low)" in ratings["evidence"][0]["text"]


@pytest.mark.parametrize(
    "text", ["6 low or 12 high", "6 (lower)", "6 (low) 12", "6 (low)\n12 (high)"]
)
def test_band_words_do_not_hide_multiple_or_unclear_scores(text):
    assert numeric_rating(text) is None
