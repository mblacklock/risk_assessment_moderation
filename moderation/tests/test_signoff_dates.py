import pytest

from moderation.checks import check_documents, field
from moderation.documents import extract_document
from moderation.tests.test_review import STUDENT


def dates_pdf(student="Date: 22 October 2026", supervisor="Date 21 October 2026"):
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=400)
    page.insert_text(
        (30, 40), "KB6060 Student Project Ethics Approval Form", fontsize=10
    )
    page.insert_text((30, 80), "Student Name: Synthetic Student", fontsize=10)
    page.insert_text((30, 100), "Project Title: Synthetic project", fontsize=10)
    page.insert_text((30, 120), "Supervisor Name: Synthetic Supervisor", fontsize=10)
    page.insert_text((30, 170), "Student sign: Student", fontsize=10)
    page.insert_text((300, 170), "Supervisor sign: Supervisor", fontsize=10)
    page.insert_text((30, 210), student, fontsize=10)
    page.insert_text((300, 210), supervisor, fontsize=10)
    data = pdf.tobytes()
    pdf.close()
    return data


@pytest.mark.parametrize(
    "label", ["Date 21 October 2026", "Date: 21 October 2026", "Date 21/10/2026"]
)
def test_pdf_dates_with_or_without_colon_stay_separate(label):
    doc = extract_document(dates_pdf(supervisor=label), "synthetic.pdf")
    checks, _ = check_documents([doc], STUDENT)
    checks = {c["id"]: c for c in checks}
    assert checks["student_ethics"]["status"] == "complete"
    assert checks["supervisor_ethics"]["status"] == "complete"
    assert any(e["text"] == label for e in checks["supervisor_ethics"]["evidence"])
    assert not any(
        "22 October" in e["text"] for e in checks["supervisor_ethics"]["evidence"]
    )


def test_blank_supervisor_date_does_not_borrow_student_date():
    checks, _ = check_documents(
        [extract_document(dates_pdf(supervisor="Date:"), "synthetic.pdf")], STUDENT
    )
    check = next(c for c in checks if c["id"] == "supervisor_ethics")
    assert check["status"] == "review" and "date" in check["message"]


def test_date_without_colon_cannot_be_mistaken_for_signature_text():
    p = {"text": "Signature: Date 21 October 2026", "images": [], "states": []}
    assert field([p], "Signature")[0] == ""
    assert field([p], "Date")[0] == "21 October 2026"
    assert field([{"text": "Database 21 October 2026"}], "Date") == ("", None)
