import io
import zipfile
from unittest.mock import patch

from moderation.documents import archive_submissions, extract_document
from moderation.tests.test_review import document_bytes


def test_legacy_doc_is_imported_using_metadata_instead_of_ignored():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("assignment_w12345678_attempt.doc", b"synthetic legacy file")
        archive.writestr(
            "assignment_w12345678_attempt.txt",
            "Name: Synthetic Student (w12345678)\nDate Submitted: 16 November 2026 12:00:00 GMT\nFilename: assignment_w12345678_attempt.doc",
        )
    groups, ignored = archive_submissions(output.getvalue())
    assert len(groups) == 1 and ignored == []
    assert groups[0]["number"] == "w12345678"
    assert groups[0]["files"][0]["data"] == b"synthetic legacy file"


def test_legacy_doc_uses_converted_copy_but_retains_original_name():
    with patch(
        "moderation.legacy_word.convert_legacy_doc", return_value=document_bytes()
    ) as convert:
        document = extract_document(b"synthetic legacy file", "synthetic.doc")
    convert.assert_called_once_with(b"synthetic legacy file")
    assert document["filename"] == "synthetic.doc"
    assert document["kind"] == "docx" and document["converted_from"] == "doc"
    assert document["paragraphs"]


def test_conversion_failure_keeps_imported_row_visible(settings, tmp_path):
    from moderation import jobs, store

    settings.REVIEW_ROOT = tmp_path / "reviews"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("synthetic.doc", b"legacy content")
    with patch.object(jobs, "start"):
        review = jobs.create_review(output.getvalue(), "Synthetic legacy review", False)
    with patch(
        "moderation.legacy_word.convert_legacy_doc",
        side_effect=ValueError("Word unavailable"),
    ):
        jobs.run(review["id"])
    updated = store.load(review["id"])
    assert len(updated["submissions"]) == 1
    assert all(c["status"] == "unable" for c in updated["submissions"][0]["checks"])
    file = updated["submissions"][0]["files"][0]
    assert (
        store.review_dir(review["id"]) / file["id"]
    ).read_bytes() == b"legacy content"
