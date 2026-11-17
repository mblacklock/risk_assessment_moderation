import base64
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from docx import Document
from openpyxl import load_workbook

from moderation import jobs, store
from moderation.ai import Judgement, LanguageReview, apply_ai
from moderation.checks import SPECIALISTS, check_documents
from moderation.criteria import CRITERIA, effective_status, overall
from moderation.documents import archive_submissions, extract_document
from moderation.exports import csv_bytes, xlsx_bytes

STUDENT = {"name": "Synthetic Student", "number": "w12345678", "submitted": "Test date"}


def document_bytes(
    *,
    medium=False,
    assessor="Synthetic Student",
    specialist="No",
    hazard="Eye strain from screen use",
    instructions_only=False,
    missing_signature=False,
    location="ELC 004",
    activity="Computer work",
    research_activity="This project uses published data and a university computer in ELC 004.",
    student_job_title="Student",
    supervisor_job_title="Lecturer",
    word_limit_fragment=None,
):
    doc = Document()
    for text in [
        "Guidance for Completing this Form",
        "Assessor: The assessor is the student.",
        "Date: 12/11/2026",
        f"Assessor: {assessor}",
        f"Area/Activity: {location}",
        "Assessment Title: Synthetic project",
    ]:
        doc.add_paragraph(text)
    table = doc.add_table(rows=2, cols=9)
    headers = [
        "Item No.",
        "Activity",
        "Hazard",
        "Persons at risk",
        "Severity",
        "Likelihood",
        "Risk Rating",
        "Control Measures",
        "Final Result",
    ]
    values = [
        "1",
        activity,
        hazard,
        "Student",
        "2",
        "3",
        "6 (L)",
        "Take breaks",
        "2x1=2 (L)",
    ]
    for cell, value in zip(table.rows[0].cells, headers, strict=True):
        cell.text = value
    for cell, value in zip(table.rows[1].cells, values, strict=True):
        cell.text = value
    for label in [
        "Manual Handling",
        "COSHH",
        "PUWER",
        "DSEAR",
        "Young Persons",
        "New & Expectant Mothers",
    ]:
        doc.add_paragraph(f"{label}: {specialist if label == 'COSHH' else 'No'}")
    for text in [
        "To be completed by the person undertaking the risk assessment",
        f"Student Name: Synthetic Student    Job Title: {student_job_title}",
        f"Signature: {'Synthetic Student' if not missing_signature else ''}",
        "Date: 12/11/2026",
        "To be completed by the Line Manager",
        f"Supervisor Name: Synthetic Supervisor    Job Title: {supervisor_job_title}",
        "Signature: Synthetic Supervisor    Date: 12/11/2026",
        "NB – end of sign-off",
        "Can this risk assessment be shared and labelled as Generic to the University? N",
        "Is there a related risk assessment that may require review and update? N",
        "KB6060 Student Project Ethics Approval Form",
        "Tutor sign off",
        "Ethics form complete",
        "☒",
        "Ethical concerns acknowledged",
        "☒",
        "Research tool(s) checked",
        "☒",
        "You must use this document",
        "Student Name:",
        "Synthetic Student",
        "Project Title:",
        "Synthetic project",
        "Supervisor Name:",
        "Synthetic Supervisor",
        "Ethics application you are amending:",
        "☐ Low Risk" if medium else "☒ Low Risk",
        "☒ Medium Risk" if medium else "☐ Medium Risk",
    ]:
        doc.add_paragraph(text)
    for heading in [
        "Project Aims and Objectives",
        "Research Activities",
        "Ethical, Environmental, Societal Impact",
        "Research Data Management",
        "Research Data Storage",
    ]:
        doc.add_paragraph(heading)
        doc.add_paragraph("Please provide the details of your project.")
        if word_limit_fragment is not None:
            doc.add_paragraph(word_limit_fragment)
        if not instructions_only:
            doc.add_paragraph(
                research_activity
                if heading == "Research Activities"
                else "This project uses published data and a university computer in ELC 004."
            )
    for text in [
        "Data Management, Retention and Disposal",
        "☒ I confirm compliance with Data Management policy",
        "Ethics, Health and Safety",
        "☒ I confirm I read the health and safety policy",
        "☒ I confirm mandatory completion of risk assessments",
        "Physical Risk Involved",
        "Physical risk assessment form completed?",
        "☒ Yes   ☐ No",
        "Supervisor Statement",
        "☒ I confirm that I reviewed the content of this form",
        "Student sign: Synthetic Student",
        "Supervisor sign: Synthetic Supervisor",
        "Date: 12/11/2026",
        "Date: 12/11/2026",
    ]:
        doc.add_paragraph(text)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def archive_bytes(data=None, metadata=True):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        name = "assignment_w12345678_attempt.docx"
        archive.writestr(name, data or document_bytes())
        if metadata:
            archive.writestr(
                "assignment_w12345678.txt",
                "Name: Synthetic Student (w12345678)\n"
                "Date Submitted: Test date\nFiles:\n\tFilename: " + name,
            )
    return output.getvalue()


def checked(**kwargs):
    checks, extracted = check_documents(
        [extract_document(document_bytes(**kwargs), "form.docx")], STUDENT
    )
    return {c["id"]: c for c in checks}, extracted


def test_complete_form_checks_and_same_paragraph_signoff():
    checks, _ = checked()
    assert len(checks) == 25
    assert checks["word_limits"]["status"] == "skipped"
    for key in checks.keys() - {
        "hs_relevance",
        "entry_quality",
        "facilities",
        "location",
        "word_limits",
    }:
        assert checks[key]["status"] == "complete", (key, checks[key]["message"])
    assert overall(list(checks.values())) == "review"


def test_medium_ethics_is_an_issue_even_with_complete_fields():
    checks, _ = checked(medium=True)
    assert checks["low_risk"]["status"] == "issue"


def test_supervisor_as_assessor_fails():
    checks, _ = checked(assessor="Synthetic Supervisor")
    assert checks["identity"]["status"] != "complete"


def test_conditional_specialist_yes_requires_document_review():
    checks, _ = checked(
        specialist="N for water, Y if chemicals are used. Ref: local lab assessment"
    )
    assert checks["specialists"]["status"] == "supervisor"
    assert "COSHH" in checks["specialists"]["message"]
    assert "supporting" in checks["specialists"]["message"]


def test_non_health_and_safety_hazard_is_flagged():
    checks, _ = checked(hazard="Loss or corruption of simulation data")
    assert checks["hs_relevance"]["message"].startswith("Potential non-H&S")


@pytest.mark.parametrize(
    ("student_role", "staff_role", "expected"),
    [
        ("Synthetic project", "Lecturer", "issue"),
        ("Student", "Synthetic project", "issue"),
        ("Student", "Lecturer", "review"),
        ("Postgraduate student", "Research Fellow", "review"),
        (
            "Student",
            "Director of a newly established interdisciplinary research centre for advanced manufacturing and materials",
            "review",
        ),
    ],
)
def test_job_titles_identify_roles_not_projects(student_role, staff_role, expected):
    checks, _ = checked(student_job_title=student_role, supervisor_job_title=staff_role)
    check = checks["entry_quality"]
    assert check["status"] == expected
    if expected == "issue":
        assert "contains the project title" in check["message"]
        assert "Student" in check["message"]
        assert "staff role" in check["message"]
        assert check["evidence"]


@pytest.mark.parametrize("model_status", ["complete", "issue"])
def test_ai_cannot_clear_project_title_in_role_field(model_status):
    checks, extracted = checked(student_job_title="Synthetic project")
    judgement = Judgement(
        status=model_status, explanation="AI assessment.", quotes=["Synthetic project"]
    )
    parsed = LanguageReview(**{key: judgement for key in LanguageReview.model_fields})
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=parsed, usage=None
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["entry_quality"]["status"] == "issue"
    assert checks["entry_quality"]["source"] == "Rule"


def test_saved_project_job_title_refresh_preserves_moderation(saved_review):
    item = saved_review["submissions"][0]
    item.pop("job_title_version")
    item["documents"] = [
        extract_document(
            document_bytes(student_job_title="Synthetic project"), "form.docx"
        )
    ]
    old = next(c for c in item["checks"] if c["id"] == "entry_quality")
    old.update(
        status="review",
        message="A job-title field may contain a project title.",
        decision="complete",
        note="Moderator note.",
        history=[{"note": "Prior decision"}],
    )
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    check = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "entry_quality"
    )
    assert check["status"] == "issue"
    assert check["decision"] == "complete"
    assert check["note"] == "Moderator note."
    assert check["history"] == old["history"]
    assert check["superseded_job_title_finding"] == old
    assert jobs.snapshot(saved_review["id"]) == updated


@pytest.mark.parametrize("fragment", ["words maximum).", "(200 words maximum)."])
@pytest.mark.parametrize("blank_answer", [False, True])
def test_word_limit_guidance_is_not_student_response(fragment, blank_answer):
    checks, extracted = checked(
        instructions_only=blank_answer, word_limit_fragment=fragment
    )
    baseline, _ = checked(instructions_only=blank_answer)
    assert checks["narrative"]["status"] == ("issue" if blank_answer else "complete")
    assert checks["word_limits"]["message"] == baseline["word_limits"]["message"]
    assert all(
        p["text"] != fragment for ps in extracted["responses"].values() for p in ps
    )
    assert any(p["text"] == fragment for p in extracted["paragraphs"])


def test_ai_cannot_use_template_word_limit_as_entry_error():
    checks, extracted = checked(word_limit_fragment="words maximum).")
    judgement = Judgement(
        status="review",
        explanation="Leftover guidance needs cleanup.",
        quotes=["words maximum)."],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{key: judgement for key in LanguageReview.model_fields}
            ),
            usage=None,
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
        payload = json.loads(
            client.return_value.responses.parse.call_args.kwargs["input"]
        )
    assert "words maximum)." not in payload["document_text"]
    assert "Leftover guidance needs cleanup" not in checks["entry_quality"]["message"]
    assert checks["entry_quality"]["source"] == "Rule"


def test_saved_template_guidance_finding_is_withdrawn(saved_review):
    item = saved_review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    check.update(
        status="review",
        source="AI",
        message="Leftover guidance needs cleanup.",
        evidence=[{"location": "Verified document extract", "text": "words maximum)."}],
        decision="complete",
        note="Checked the original.",
    )
    previous = {key: check[key] for key in ("status", "source", "message", "evidence")}
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        refreshed = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = refreshed["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    assert check["source"] == "Rule"
    assert check["evidence"] == []
    assert check["superseded_guidance_finding"] == previous
    assert check["decision"] == "complete"
    assert check["note"] == "Checked the original."
    assert item["ai"]["entry_quality_pending"] is True
    assert jobs.snapshot(saved_review["id"]) == refreshed


def test_template_instructions_are_not_a_response():
    checks, _ = checked(instructions_only=True)
    assert checks["narrative"]["status"] == "issue"


def test_blank_signature_not_filled_by_next_date():
    checks, _ = checked(missing_signature=True)
    assert checks["student_ra"]["status"] == "issue"
    assert "signature" in checks["student_ra"]["message"]


def test_blank_signature_beside_date_is_not_a_signature():
    doc = Document(io.BytesIO(document_bytes()))
    paragraph = next(
        p
        for p in doc.paragraphs
        if p.text.startswith("Signature: Synthetic Supervisor")
    )
    paragraph.text = "Signature:                 Date: 12/11/2026"
    output = io.BytesIO()
    doc.save(output)
    checks, _ = check_documents(
        [extract_document(output.getvalue(), "form.docx")], STUDENT
    )
    signoff = next(c for c in checks if c["id"] == "supervisor_ra")
    assert signoff["status"] == "issue"
    assert "signature" in signoff["message"]


def test_word_checkbox_state_overrides_displayed_glyph():
    from xml.etree import ElementTree as ET

    from moderation.documents import NS

    original = document_bytes()
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as archive,
        zipfile.ZipFile(output, "w") as rewritten,
    ):
        for entry in archive.infolist():
            data = archive.read(entry)
            if entry.filename == "word/document.xml":
                root = ET.fromstring(data)
                paragraph = next(
                    p
                    for p in root.findall(".//w:p", NS)
                    if "Low Risk" in "".join(p.itertext())
                )
                control = ET.SubElement(paragraph, f"{{{NS['w']}}}sdt")
                properties = ET.SubElement(control, f"{{{NS['w']}}}sdtPr")
                box = ET.SubElement(properties, f"{{{NS['w14']}}}checkbox")
                ET.SubElement(
                    box, f"{{{NS['w14']}}}checked", {f"{{{NS['w14']}}}val": "0"}
                )
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            rewritten.writestr(entry, data)
    checks, _ = check_documents(
        [extract_document(output.getvalue(), "form.docx")], STUDENT
    )
    assert next(c for c in checks if c["id"] == "low_risk")["status"] == "issue"


def structured_pdf_bytes(final="6", second_item="2", split_columns=False):
    import pymupdf

    pdf = pymupdf.open()
    widths = [30, 110, 120, 65, 45, 55, 65, 170, 75]
    edges = [30]
    for width in widths:
        edges.append(edges[-1] + width)

    def grid(page, top, rows):
        for j, row in enumerate(rows):
            for i, text in enumerate(row):
                rect = pymupdf.Rect(
                    edges[i], top + j * 65, edges[i + 1], top + (j + 1) * 65
                )
                page.draw_rect(rect, width=0.5)
                assert page.insert_textbox(rect + (3, 3, -3, -3), text, fontsize=7) >= 0

    page = pdf.new_page(width=850, height=600)
    # Deliberately put the right-hand field slightly higher and earlier in the stream.
    page.insert_text((250, 30), "Assessor: Synthetic Student", fontsize=9)
    page.insert_text((30, 31), "Date: 15/11/2026", fontsize=9)
    page.insert_text(
        (30, 50), "Assessment Title: Synthetic computer project", fontsize=9
    )
    page.insert_text((30, 70), "Area/Activity: Computing room", fontsize=9)
    grid(
        page,
        100,
        [
            [
                "Item No.",
                "Activity",
                "Hazard",
                "Persons at risk",
                "Severity",
                "Likelihood",
                "Risk Rating",
                "Control Measures",
                "Final Result",
            ],
            [
                "1",
                "Computer work",
                "Eye strain",
                "Student",
                "3",
                "4",
                "12 (M)",
                "Take regular breaks",
                final,
            ],
        ],
    )
    if split_columns:
        page.draw_line((edges[2] + 45, 165), (edges[2] + 45, 230), width=0.5)
    page = pdf.new_page(width=850, height=600)
    grid(
        page,
        40,
        [
            [
                second_item,
                "Computer work",
                "Wrist strain",
                "Student",
                "3",
                "4",
                "12 (M)",
                "Adjust workstation",
                "3x2=6 (L)",
            ]
        ],
    )
    page.insert_textbox(
        pymupdf.Rect(30, 150, 190, 200), "New & Expectant\nMothers: No", fontsize=10
    )
    page.insert_text(
        (30, 250),
        "To be completed by the person undertaking the risk assessment",
        fontsize=9,
    )
    page.insert_text(
        (30, 270), "Student Name: Synthetic Student    Job Title: Student", fontsize=9
    )
    page.insert_text(
        (30, 290), "Signature: Synthetic Student    Date: 15/11/2026", fontsize=9
    )
    page.insert_text((30, 330), "To be completed by the Line Manager", fontsize=9)
    page.insert_text(
        (30, 350),
        "Supervisor Name: Synthetic Supervisor    Job Title: Lecturer",
        fontsize=9,
    )
    page.insert_text(
        (30, 370), "Signature: Synthetic Supervisor    Date: 15/11/2026", fontsize=9
    )
    page.insert_text((30, 390), "NB - end of sign-off", fontsize=9)
    page = pdf.new_page(width=600, height=800)
    page.insert_text(
        (30, 40), "KB6060 Student Project Ethics Approval Form", fontsize=12
    )
    page.insert_text((30, 65), "You must use this document", fontsize=9)
    for j, (label, mark) in enumerate(
        [
            ("Tutor sign off", ""),
            ("Ethics form complete", "X"),
            ("Ethical concerns acknowledged", "X"),
            ("Research tools checked", "X"),
        ]
    ):
        for x0, x1, text in [(30, 240, label), (240, 275, mark)]:
            rect = pymupdf.Rect(x0, 90 + j * 25, x1, 115 + j * 25)
            page.draw_rect(rect, width=0.5)
            page.insert_text((x0 + 4, 105 + j * 25), text, fontsize=9)
    page.insert_text((30, 240), "Student Name: Synthetic Student", fontsize=9)
    page.insert_text((30, 260), "Project Title: Synthetic computer project", fontsize=9)
    page.insert_text((30, 280), "Supervisor Name: Synthetic Supervisor", fontsize=9)
    data = pdf.tobytes()
    pdf.close()
    return data


@pytest.mark.parametrize(
    "final,status", [("6", "complete"), ("3x2=6 (L)", "complete"), ("12", "issue")]
)
def test_pdf_recovers_continuation_tables_wrapped_fields_and_typed_signoffs(
    final, status
):
    document = extract_document(structured_pdf_bytes(final), "synthetic.pdf")
    found, extracted = check_documents([document], STUDENT)
    checks = {c["id"]: c for c in found}
    assert len(extracted["risk_rows"]) == 2
    assert extracted["assessor"] == "Synthetic Student"
    assert any(
        "New & Expectant Mothers: No" in p["text"] for p in document["paragraphs"]
    )
    assert checks["identity"]["status"] == "complete"
    assert checks["risk_table"]["status"] == "complete"
    assert checks["ratings"]["status"] == "complete"
    assert checks["risk_reduction"]["status"] == status
    assert checks["student_ra"]["status"] == "complete"
    assert checks["supervisor_ra"]["status"] == "complete"
    assert checks["tutor"]["status"] == "complete"


def grouped_risk_pdf_bytes(last_id="B2"):
    import pymupdf

    pdf = pymupdf.open()
    widths = [35, 115, 125, 70, 45, 55, 70, 180, 90]
    edges = [25]
    for width in widths:
        edges.append(edges[-1] + width)
    header = [
        "Item",
        "Activity",
        "Hazard",
        "Persons at risk",
        "Severity",
        "Likelihood",
        "Risk Rating",
        "Control Measures",
        "Final Result",
    ]

    def risk(identifier):
        return [
            identifier,
            "Computer work",
            "Eye strain",
            "Student",
            "3",
            "4",
            "12 (M)",
            "Take regular breaks",
            "3x2=6 (L)",
        ]

    def page(rows, repeat_header=True):
        p = pdf.new_page(width=850, height=650)
        y = 60
        for row in [header] + rows if repeat_header else rows:
            if isinstance(row, str):
                rect = pymupdf.Rect(edges[0], y, edges[-1], y + 30)
                p.draw_rect(rect, width=0.5)
                p.insert_text((edges[0] + 3, y + 16), row, fontsize=8)
                y += 30
            else:
                for i, text in enumerate(row):
                    rect = pymupdf.Rect(edges[i], y, edges[i + 1], y + 55)
                    p.draw_rect(rect, width=0.5)
                    assert (
                        p.insert_textbox(rect + (3, 3, -3, -3), text, fontsize=7) >= 0
                    )
                y += 55

    page(["A. General activities", risk("1")])
    page(
        [
            [
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "Further controls continued on the next page",
                "",
            ]
        ]
    )
    page([risk("2")], repeat_header=False)
    page(["A. Specialist tests", risk("A1"), risk("A2"), "B. Measurements", risk("B1")])
    page(
        [
            risk(last_id),
            "Does this Risk Assessment Require Further Specific Risk Assessment:",
            risk("99"),
        ]
    )
    result = pdf.tobytes()
    pdf.close()
    return result


@pytest.mark.parametrize(
    "last_id,status", [("B2", "complete"), ("B4", "review"), ("B1", "review")]
)
def test_pdf_grouped_rows_headers_sections_and_continued_controls(last_id, status):
    document = extract_document(grouped_risk_pdf_bytes(last_id), "synthetic.pdf")
    found, extracted = check_documents([document], STUDENT)
    rows = extracted["risk_rows"]
    assert [row[0] for row in rows] == ["1", "2", "A1", "A2", "B1", last_id]
    assert "Further controls continued on the next page" in rows[0][7]
    assert not any("General activities" in row[0] or row[0] == "99" for row in rows)
    assert document["risk_table_reliable"] == (status == "complete")
    assert all(
        c["status"] == status
        for c in found
        if c["id"] in {"risk_table", "ratings", "risk_reduction"}
    )


def test_pdf_partial_table_extraction_cannot_pass():
    document = extract_document(structured_pdf_bytes(second_item="3"), "synthetic.pdf")
    found, _ = check_documents([document], STUDENT)
    assert document["risk_table_reliable"] is False
    assert all(
        c["status"] == "review"
        for c in found
        if c["id"] in {"risk_table", "ratings", "risk_reduction"}
    )


def test_pdf_recovers_spurious_subcolumns_from_merged_header_cells():
    import pymupdf

    data = structured_pdf_bytes(split_columns=True)
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        assert any(
            t.col_count > 9 for t in pdf[0].find_tables(strategy="lines_strict").tables
        )
    document = extract_document(data, "synthetic.pdf")
    found, extracted = check_documents([document], STUDENT)
    assert len(extracted["risk_rows"]) == 2
    assert document["risk_table_reliable"] is True
    assert next(c for c in found if c["id"] == "risk_table")["status"] == "complete"


def test_saved_pdf_refresh_preserves_originals_ai_and_moderation(saved_review):
    item = saved_review["submissions"][0]
    file = item["files"][0]
    file["name"] = "synthetic.pdf"
    data = structured_pdf_bytes()
    path = store.review_dir(saved_review["id"]) / file["id"]
    path.write_bytes(data)
    old_doc = extract_document(data, file["name"])
    old_doc.pop("pdf_reader_version")
    old_doc["tables"] = []
    item["documents"] = [old_doc]
    old = next(c for c in item["checks"] if c["id"] == "risk_table")
    old.update(
        status="review",
        message="PDF requires visual review.",
        decision="complete",
        note="Checked table.",
        history=[{"note": "Earlier decision"}],
    )
    ai_check = next(c for c in item["checks"] if c["id"] == "narrative")
    ai_check.update(source="AI", message="Existing AI finding.")
    saved_review["use_ai"] = True
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    refreshed = updated["submissions"][0]
    check = next(c for c in refreshed["checks"] if c["id"] == "risk_table")
    assert check["status"] == "complete"
    assert check["superseded_pdf_finding"] == old
    assert check["decision"] == "complete"
    assert check["note"] == "Checked table."
    assert check["history"] == old["history"]
    assert next(c for c in refreshed["checks"] if c["id"] == "narrative") == ai_check
    assert refreshed["ai"]["facilities_pending"] is True
    assert refreshed["documents"][0]["pdf_reader_version"] == 9
    assert path.read_bytes() == data
    assert jobs.snapshot(saved_review["id"]) == updated


def test_readable_pdf_selections_are_not_forced_manual():
    document = extract_document(document_bytes(), "synthetic.docx")
    document.update(kind="pdf", pdf_reader_version=1, risk_table_reliable=True)
    checks, _ = check_documents([document], STUDENT)
    assert all(
        c["status"] == "complete"
        for c in checks
        if c["id"] in {"low_risk", "declarations", "physical", "supervisor_statement"}
    )


def image_signature_pdf_bytes(placement="field"):
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page(width=600, height=800)
    for y, text in [
        (30, "Date: 15/11/2026"),
        (50, "Assessor: Synthetic Student"),
        (70, "Assessment Title: Synthetic computer project"),
        (90, "Area/Activity: Computing room"),
        (120, "To be completed by the person undertaking the risk assessment"),
        (140, "Student Name: Synthetic Student    Job Title: Student"),
        (160, "Signature: Synthetic Student    Date: 15/11/2026"),
        (200, "To be completed by the Line Manager"),
        (220, "Supervisor Name: Synthetic Supervisor    Job Title: Lecturer"),
        (260, "Signature:"),
        (350, "NB - end of sign-off"),
        (400, "KB6060 Student Project Ethics Approval Form"),
        (420, "Student Name: Synthetic Student"),
        (440, "Project Title: Synthetic computer project"),
        (460, "Supervisor Name: Synthetic Supervisor"),
        (540, "Student sign: Synthetic Student"),
        (610, "Date: 15/11/2026"),
    ]:
        page.insert_text((40, y), text, fontsize=10)
    page.insert_text((350, 260), "Date: 15/11/2026", fontsize=10)
    page.insert_text((300, 540), "Supervisor sign:", fontsize=10)
    page.insert_text((300, 610), "Date: 15/11/2026", fontsize=10)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 30), True)
    pixmap.clear_with(0)
    pixmap.set_rect(pymupdf.IRect(8, 12, 72, 16), (0, 0, 0, 255))
    png = pixmap.tobytes("png")
    rects = {
        "field": [(140, 245, 290, 290), (410, 525, 560, 570)],
        "header": [(460, 8, 560, 46)],
        "distant": [(400, 150, 550, 195)],
        "raised": [(140, 220, 290, 245)],
        "raised_field": [(140, 225, 290, 270)],
        "over_name": [(140, 210, 290, 265)],
        "scan": [(0, 0, 600, 800)],
        "ambiguous": [(140, 245, 200, 270), (220, 245, 280, 270)],
        "none": [],
    }[placement]
    for rect in rects:
        page.insert_image(pymupdf.Rect(rect), stream=png, keep_proportion=False)
    result = pdf.tobytes()
    pdf.close()
    return result


@pytest.mark.parametrize(
    "placement",
    [
        "field",
        "header",
        "distant",
        "ambiguous",
        "raised",
        "raised_field",
        "over_name",
        "scan",
        "none",
    ],
)
def test_pdf_image_presence_requires_clear_signature_field_association(placement):
    doc = extract_document(image_signature_pdf_bytes(placement), "synthetic.pdf")
    found, _ = check_documents([doc], STUDENT)
    checks = {c["id"]: c for c in found}
    assert checks["supervisor_ra"]["status"] == (
        "complete"
        if placement in {"field", "raised_field"}
        else "review"
        if placement in {"ambiguous", "raised", "over_name", "scan"}
        else "issue"
    )
    if placement in {"header", "distant", "none"}:
        assert checks["supervisor_ra"]["signature_presence"] == "blank"
    assert checks["student_ra"]["status"] == "complete"
    if placement == "field":
        assert checks["supervisor_ethics"]["status"] == "complete"
        assert checks["student_ethics"]["status"] == "complete"
    if placement in {"field", "raised_field"}:
        assert (
            sum(len(e.get("images", [])) for e in checks["supervisor_ra"]["evidence"])
            == 1
        )
        assert len(set(image for p in doc["paragraphs"] for image in p["images"])) == 1
    else:
        assert not any(p["images"] for p in doc["paragraphs"])


@pytest.mark.parametrize("mark", ["vector", "annotation", "covered"])
def test_unrecognised_pdf_ink_or_covered_field_is_not_declared_blank(mark):
    import pymupdf

    with pymupdf.open(stream=image_signature_pdf_bytes("none"), filetype="pdf") as pdf:
        page = pdf[0]
        if mark == "vector":
            page.draw_polyline([(140, 225), (160, 235), (190, 220)], color=(0, 0, 0))
        elif mark == "annotation":
            page.add_ink_annot([[(140, 225), (160, 235), (190, 220)]])
        else:
            page.draw_rect(pymupdf.Rect(30, 205, 350, 330), color=None, fill=(0, 0, 0))
        data = pdf.tobytes()
    found, _ = check_documents([extract_document(data, "synthetic.pdf")], STUDENT)
    check = next(c for c in found if c["id"] == "supervisor_ra")
    assert check["status"] == "review"
    assert check["signature_presence"] == "unknown"
    assert "no missing-signature conclusion has been verified" in check["message"]


def test_saved_blank_pdf_signature_is_refreshed_to_issue_without_ai(saved_review):
    item = saved_review["submissions"][0]
    file = item["files"][0]
    data = image_signature_pdf_bytes("none")
    file["name"] = "synthetic.pdf"
    path = store.review_dir(saved_review["id"]) / file["id"]
    path.write_bytes(data)
    document = extract_document(data, file["name"])
    document["pdf_reader_version"] = 4
    for p in document["paragraphs"]:
        p.pop("signature_field_blank", None)
    item["documents"] = [document]
    old = next(c for c in item["checks"] if c["id"] == "supervisor_ra")
    old.update(
        status="review",
        message="PDF evidence unreadable; missing signature.",
        note="Moderator note.",
        history=[{"note": "Earlier review"}],
    )
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    check = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "supervisor_ra"
    )
    assert check["status"] == "issue"
    assert check["signature_presence"] == "blank"
    assert check["note"] == "Moderator note."
    assert check["history"] == old["history"]
    assert check["superseded_pdf_finding"] == old
    assert path.read_bytes() == data
    assert jobs.snapshot(saved_review["id"]) == updated


def test_pdf_signature_image_is_served_privately_with_transparency(
    client, saved_review
):
    import pymupdf

    item = saved_review["submissions"][0]
    file = item["files"][0]
    data = image_signature_pdf_bytes()
    file["name"] = "synthetic.pdf"
    (store.review_dir(saved_review["id"]) / file["id"]).write_bytes(data)
    doc = extract_document(data, file["name"])
    item["documents"] = [doc]
    item["checks"], _ = check_documents([doc], item)
    store.save(saved_review)
    response = client.get(
        reverse("moderation:submission", args=[saved_review["id"], item["id"]])
    )
    assert len(response.context["documents"][0]["images"]) == 1
    image_url = response.context["documents"][0]["images"][0]
    assert image_url in response.content.decode()
    image_response = client.get(image_url)
    assert image_response.status_code == 200
    assert image_response["Content-Type"] == "image/png"
    assert image_response["Cache-Control"] == "private, no-store"
    assert image_response["X-Content-Type-Options"] == "nosniff"
    pixmap = pymupdf.Pixmap(image_response.content)
    assert (pixmap.width, pixmap.height, pixmap.alpha) == (80, 30, 1)
    assert (
        client.get(
            reverse("moderation:image", args=[saved_review["id"], item["id"], 0, 99])
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "placement", ["own_cell", "cross_column", "date_cell", "above_cell"]
)
def test_raised_ethics_signature_image_stays_inside_own_table_cell(placement):
    import pymupdf

    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        for y, text in [
            (40, "KB6060 Student Project Ethics Approval Form"),
            (70, "Student Name: Synthetic Student"),
            (90, "Project Title: Synthetic computer project"),
            (110, "Supervisor Name: Synthetic Supervisor"),
        ]:
            page.insert_text((40, y), text, fontsize=10)
        for x0, x1 in [(30, 300), (300, 580)]:
            for y0, y1 in [(450, 515), (515, 550)]:
                page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), width=0.5)
        page.insert_text((40, 470), "Student sign: Synthetic Student", fontsize=10)
        page.insert_text((310, 495), "Supervisor sign:", fontsize=10)
        page.insert_text((40, 530), "Date: 15/11/2026", fontsize=10)
        page.insert_text((310, 530), "Date: 15/11/2026", fontsize=10)
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 30), True)
        pixmap.clear_with(0)
        pixmap.set_rect(pymupdf.IRect(8, 12, 72, 16), (0, 0, 0, 255))
        rect = {
            "own_cell": (400, 465, 550, 510),
            "cross_column": (250, 465, 450, 510),
            "date_cell": (400, 520, 550, 545),
            "above_cell": (400, 420, 550, 460),
        }[placement]
        page.insert_image(
            pymupdf.Rect(rect), stream=pixmap.tobytes("png"), keep_proportion=False
        )
        data = pdf.tobytes()
    found, _ = check_documents([extract_document(data, "synthetic.pdf")], STUDENT)
    checks = {c["id"]: c for c in found}
    assert checks["student_ethics"]["status"] == "complete"
    assert checks["supervisor_ethics"]["status"] == (
        "complete" if placement == "own_cell" else "review"
    )
    assert any(e.get("images") for e in checks["supervisor_ethics"]["evidence"]) == (
        placement == "own_cell"
    )


def test_pdf_does_not_claim_signature_or_checkbox_certainty():
    import pymupdf

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox((30, 40, 550, 750), "Risk assessment text " * 15)
        data = pdf.tobytes()
    checks, _ = check_documents([extract_document(data, "form.pdf")], STUDENT)
    for check in checks:
        if check["id"] in {"low_risk", "student_ra", "supervisor_ethics"}:
            assert check["status"] == "review"


def highlighted_word_bytes(choice):
    from docx.enum.text import WD_COLOR_INDEX

    doc = Document(io.BytesIO(document_bytes()))
    for p in doc.paragraphs:
        if any(p.text.startswith(label + ":") for label in SPECIALISTS):
            prefix = p.text.split(":", 1)[0] + ": "
        elif (
            "Generic to the University" in p.text
            or "related risk assessment that may require" in p.text
        ):
            prefix = p.text.rsplit("?", 1)[0] + "? "
        else:
            continue
        p.clear()
        p.add_run(prefix)
        for text, key in [("Y", "yes"), ("/", "separator"), ("N", "no")]:
            run = p.add_run(text)
            if choice == key or choice == "both":
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        if choice == "reference":
            p.add_run(" Please list reference No: ")
            p.add_run("N").font.highlight_color = WD_COLOR_INDEX.YELLOW
    result = io.BytesIO()
    doc.save(result)
    return result.getvalue()


@pytest.mark.parametrize(
    "choice,status",
    [
        ("no", "complete"),
        ("yes", "supervisor"),
        ("both", "moderator"),
        ("none", "issue"),
        ("reference", "issue"),
    ],
)
def test_word_highlights_select_primary_specialist_answers(choice, status):
    document = extract_document(highlighted_word_bytes(choice), "synthetic.docx")
    checks, _ = check_documents([document], STUDENT)
    check = next(c for c in checks if c["id"] == "specialists")
    assert check["status"] == status
    if choice == "no":
        assert any(
            e.get("selection_note") == "Highlighted choice: No"
            for e in check["evidence"]
        )
    if choice == "yes":
        assert "supporting assessments" in check["message"]


@pytest.mark.parametrize(
    "choice,status",
    [("no", "complete"), ("yes", "complete"), ("both", "review"), ("none", "issue")],
)
def test_word_highlights_select_admin_answers(choice, status):
    document = extract_document(highlighted_word_bytes(choice), "synthetic.docx")
    checks, _ = check_documents([document], STUDENT)
    assert next(c for c in checks if c["id"] == "admin")["status"] == status


def test_partly_highlighted_word_option_requires_review():
    from docx.enum.text import WD_COLOR_INDEX

    doc = Document(io.BytesIO(document_bytes()))
    paragraph = next(p for p in doc.paragraphs if p.text.startswith("Manual Handling:"))
    paragraph.clear()
    paragraph.add_run("Manual Handling: Yes/")
    paragraph.add_run("N").font.highlight_color = WD_COLOR_INDEX.YELLOW
    paragraph.add_run("o")
    data = io.BytesIO()
    doc.save(data)
    found, _ = check_documents(
        [extract_document(data.getvalue(), "synthetic.docx")], STUDENT
    )
    assert next(c for c in found if c["id"] == "specialists")["status"] == "moderator"


def test_saved_highlights_refresh_only_answer_checks_and_preserve_decisions(
    saved_review,
):
    item = saved_review["submissions"][0]
    file = item["files"][0]
    data = highlighted_word_bytes("no")
    path = store.review_dir(saved_review["id"]) / file["id"]
    path.write_bytes(data)
    old_doc = extract_document(data, file["name"])
    old_doc.pop("highlight_reader_version")
    for paragraph in old_doc["paragraphs"]:
        paragraph.pop("highlighted_ranges", None)
    item["documents"] = [old_doc]
    old = next(c for c in item["checks"] if c["id"] == "specialists")
    old.update(
        status="issue",
        message="Unanswered Y/N options.",
        decision="review",
        note="Original moderator note.",
        history=[{"note": "Original decision"}],
    )
    other = next(c for c in item["checks"] if c["id"] == "narrative")
    other.update(source="AI", message="Original AI finding.")
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "specialists")
    assert check["status"] == "complete"
    assert check["decision"] == "review"
    assert check["note"] == old["note"]
    assert check["history"] == old["history"]
    assert check["superseded_highlight_finding"] == old
    assert next(c for c in item["checks"] if c["id"] == "narrative") == other
    assert path.read_bytes() == data
    assert jobs.snapshot(saved_review["id"]) == updated


def highlighted_pdf_bytes(choice, style):
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page(width=800, height=650)
    page.insert_text(
        (30, 30), "Date: 15/11/2026    Assessor: Synthetic Student", fontsize=10
    )
    page.insert_text((30, 50), "Assessment Title: Synthetic computer work", fontsize=10)
    labels = [label + ": " for label in SPECIALISTS] + [
        "Can this risk assessment be shared as Generic to the University? ",
        "Is there a related risk assessment that may require review? ",
    ]
    for index, prefix in enumerate(labels):
        text = prefix + "Y/N"
        if choice == "reference":
            text += " Please list reference No: N"
        start = len(prefix) + (2 if choice == "no" else 0)
        end = len(prefix) + (3 if choice in {"no", "both"} else 1)
        if choice == "reference":
            start, end = len(text) - 1, len(text)
        y = 100 + index * 50
        rect = pymupdf.Rect(
            30 + pymupdf.get_text_length(text[:start], fontsize=10),
            y - 11,
            30 + pymupdf.get_text_length(text[:end], fontsize=10),
            y + 3,
        )
        if style == "flattened" and choice != "none":
            page.draw_rect(rect, color=None, fill=(1, 1, 0), overlay=False)
        page.insert_text((30, y), text, fontsize=10)
        if style == "annotation" and choice != "none":
            page.add_highlight_annot(rect)
    data = pdf.tobytes()
    pdf.close()
    return data


@pytest.mark.parametrize("style", ["annotation", "flattened"])
@pytest.mark.parametrize(
    "choice,status",
    [
        ("no", "complete"),
        ("yes", "supervisor"),
        ("both", "moderator"),
        ("none", "issue"),
        ("reference", "issue"),
    ],
)
def test_pdf_highlights_select_primary_answers(choice, status, style):
    document = extract_document(highlighted_pdf_bytes(choice, style), "synthetic.pdf")
    checks, _ = check_documents([document], STUDENT)
    by_id = {c["id"]: c for c in checks}
    assert by_id["specialists"]["status"] == status
    if choice in {"no", "yes"}:
        assert by_id["admin"]["status"] == "complete"
    if choice == "no":
        assert any(
            e.get("selection_note") == "Highlighted choice: No"
            for e in by_id["specialists"]["evidence"]
        )


def test_archive_metadata_and_missing_metadata():
    groups, ignored = archive_submissions(archive_bytes())
    assert groups[0]["name"] == STUDENT["name"]
    assert groups[0]["number"] == STUDENT["number"]
    assert ignored == []
    groups, _ = archive_submissions(archive_bytes(metadata=False))
    assert groups[0]["name"] == "Identity needs review"


def test_archive_rejects_path_traversal():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../private.docx", b"test")
    with pytest.raises(ValueError, match="unsafe"):
        archive_submissions(output.getvalue())


@pytest.fixture
def saved_review(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        review = jobs.create_review(archive_bytes(), "Synthetic review", False)
    jobs.run(review["id"])
    return store.load(review["id"])


def test_upload_review_filters_decision_and_exports(client, saved_review):
    review = saved_review
    rid = review["id"]
    item = review["submissions"][0]
    review_url = reverse("moderation:review", args=[rid])
    response = client.get(review_url, {"category": "Ethics", "status": "complete"})
    assert response.status_code == 200
    assert len(response.context["rows"]) == 1
    assert all(col["category"] == "Ethics" for col in response.context["columns"])
    assert client.get(review_url, {"q": "no-match"}).context["rows"] == []
    assert (
        client.get(reverse("moderation:submission", args=[rid, item["id"]])).status_code
        == 200
    )
    decision_url = reverse("moderation:decide", args=[rid, item["id"], "hs_relevance"])
    assert (
        client.post(decision_url, {"decision": "complete", "note": ""}).status_code
        == 302
    )
    assert (
        client.post(
            decision_url, {"decision": "complete", "note": "Inspected all hazard rows."}
        ).status_code
        == 302
    )
    updated = store.load(rid)
    check = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "hs_relevance"
    )
    assert effective_status(check) == "complete"
    assert check["status"] == "review"  # Original automated finding is preserved.
    assert "Inspected all" in check["note"]
    for kind in ("csv", "xlsx"):
        response = client.get(reverse("moderation:export", args=[rid, kind]))
        assert response.status_code == 200
    file = item["files"][0]
    response = client.get(
        reverse("moderation:download", args=[rid, item["id"], file["id"]])
    )
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"PK")


def test_upload_endpoint_and_csrf(client, settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        response = client.post(
            "/",
            {
                "title": "Test",
                "archive": SimpleUploadedFile("download.zip", archive_bytes()),
            },
        )
    assert response.status_code == 302
    from django.test import Client

    strict = Client(enforce_csrf_checks=True)
    assert strict.post("/", {}).status_code == 403


def test_exports_escape_formulas_and_include_notes(saved_review):
    saved_review["submissions"][0]["name"] = '=HYPERLINK("bad")'
    assert b"'=HYPERLINK" in csv_bytes(saved_review)
    workbook = load_workbook(io.BytesIO(xlsx_bytes(saved_review)))
    assert workbook["Snapshot"]["B2"].data_type == "s"
    assert workbook["Findings and decisions"].max_row == 26


def test_manual_filter_includes_submissions_with_other_issues(client, saved_review):
    review = saved_review
    review["submissions"][0]["checks"][0]["status"] = "issue"
    store.save(review)
    response = client.get(
        reverse("moderation:review", args=[review["id"]]), {"status": "review"}
    )
    assert len(response.context["rows"]) == 1
    assert response.context["totals"]["issue"] == 1
    assert response.context["totals"]["review"] == 1


def test_saved_checks_use_current_groups_and_order_without_changing_results(
    client, saved_review
):
    item = saved_review["submissions"][0]
    item["checks"].reverse()
    for check in item["checks"]:
        check["category"] = "Old category"
    item["checks"][0].update(decision="complete", note="Preserved moderator note.")
    store.save(saved_review)
    before = store.load(saved_review["id"])
    response = client.get(
        reverse("moderation:submission", args=[saved_review["id"], item["id"]])
    )
    assert response.status_code == 200
    assert [c["id"] for c in response.context["checks"]] == [
        key for key, _, _ in CRITERIA
    ]
    html = response.content.decode()
    groups = list(dict.fromkeys(category for _, _, category in CRITERIA))
    assert [html.index(f"<h3>{group}</h3>") for group in groups] == sorted(
        html.index(f"<h3>{group}</h3>") for group in groups
    )
    assert "Preserved moderator note." in html
    assert "Old category" not in html
    workbook = load_workbook(io.BytesIO(xlsx_bytes(before)))
    details = list(workbook["Findings and decisions"].values)[1:]
    assert [(row[3], row[2]) for row in details] == [
        (label, category) for _, label, category in CRITERIA
    ]
    assert [cell.value for cell in workbook["Snapshot"][1]][6:-1] == [
        label for _, label, _ in CRITERIA
    ]
    assert (
        workbook["Snapshot"].cell(1, workbook["Snapshot"].max_column).value
        == "eLP feedback"
    )
    assert store.load(saved_review["id"]) == before


@pytest.mark.parametrize("category", ["", "Risk assessment", "Ethics sign-off"])
def test_matrix_has_group_headers_matching_visible_columns(
    client, saved_review, category
):
    response = client.get(
        reverse("moderation:review", args=[saved_review["id"]]), {"category": category}
    )
    columns = response.context["columns"]
    html = response.content.decode()
    for group in dict.fromkeys(col["category"] for col in columns):
        count = sum(col["category"] == group for col in columns)
        assert f'scope="colgroup" colspan="{count}">{group}</th>' in html
    assert columns == [
        {"id": key, "label": label, "category": group}
        for key, label, group in CRITERIA
        if not category or group == category
    ]


def test_unknown_review_is_404(client, settings):
    settings.ALLOWED_HOSTS = ["testserver"]
    assert (
        client.get("/reviews/00000000-0000-0000-0000-000000000000/").status_code == 404
    )


def test_ai_evidence_is_verified_and_rule_failures_are_preserved():
    checks, extracted = checked(
        medium=True, hazard="Loss or corruption of simulation data"
    )
    decision = Judgement(status="complete", explanation="No issue.", quotes=["ELC 004"])
    parsed = LanguageReview(
        location=decision,
        hs_relevance=decision,
        facilities=decision,
        entry_quality=decision,
        narrative=decision,
    )
    response = SimpleNamespace(output_parsed=parsed, usage=None)
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = response
        apply_ai(list(checks.values()), extracted, STUDENT)
        assert client.return_value.responses.parse.call_args.kwargs["store"] is False
    assert checks["hs_relevance"]["status"] == "review"
    assert checks["low_risk"]["status"] == "issue"
    hallucinated = Judgement(
        status="complete", explanation="Fine", quotes=["This text does not exist"]
    )
    parsed = LanguageReview(
        location=hallucinated,
        hs_relevance=hallucinated,
        facilities=hallucinated,
        entry_quality=hallucinated,
        narrative=hallucinated,
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=parsed, usage=None
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["entry_quality"]["status"] == "review"


@pytest.mark.parametrize(
    ("model_status", "quote", "expected"),
    [
        ("issue", "Loss or corruption of simulation data", "issue"),
        ("review", "Loss or corruption of simulation data", "review"),
        ("complete", "Loss or corruption of simulation data", "review"),
        ("issue", "This hazard does not exist in the document", "review"),
    ],
)
def test_ai_confirmed_non_hs_hazard_requires_correction(model_status, quote, expected):
    checks, extracted = checked(hazard="Loss or corruption of simulation data")
    ordinary = Judgement(status="complete", explanation="Complete.", quotes=["ELC 004"])
    explanation = "Simulation data loss is not an H&S hazard."
    parsed = LanguageReview(
        location=ordinary,
        hs_relevance=Judgement(
            status=model_status, explanation=explanation, quotes=[quote]
        ),
        facilities=ordinary,
        entry_quality=ordinary,
        narrative=ordinary,
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=parsed, usage=None
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
    check = checks["hs_relevance"]
    assert check["status"] == expected
    if expected == "issue":
        assert check["source"] == "AI"
        assert check["message"] == explanation
        assert check["evidence"] == [
            {"location": "Verified document extract", "text": quote}
        ]
    else:
        assert check["message"].startswith("Potential non-H&S")


@pytest.mark.parametrize("current_version", [False, True])
def test_saved_hazard_flag_can_be_retried_without_automatic_ai(
    client, saved_review, monkeypatch, current_version
):
    review = saved_review
    item = review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "hs_relevance")
    check.update(
        status="review",
        source="Rule",
        message="Potential non-H&S hazards: Data loss. AI observation: Not H&S.",
        decision="complete",
        note="Existing moderator note.",
    )
    if current_version:
        check["hs_relevance_ai_version"] = 1
    item["ai"] = {"state": "complete"}
    review["use_ai"] = True
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(review["id"])
        api.assert_not_called()
    updated_item = updated["submissions"][0]
    assert bool(updated_item["ai"].get("hs_relevance_pending")) != current_version
    assert next(c for c in updated_item["checks"] if c["id"] == "hs_relevance") == check
    assert jobs.snapshot(review["id"]) == updated
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    with patch("moderation.jobs.start"):
        response = client.post(
            reverse("moderation:resume", args=[review["id"]]),
            {"action": "retry_ai"},
        )
    assert response.status_code == 302
    assert store.load(review["id"])["submissions"][0]["state"] == (
        "done" if current_version else "pending"
    )


@pytest.mark.parametrize(
    ("ai", "expected"),
    [
        ({"state": "complete"}, 0),
        ({"state": "complete", "hs_relevance_pending": True}, 1),
        (
            {"state": "complete", "location_pending": True, "facilities_pending": True},
            2,
        ),
        ({"state": "failed"}, 0),
        ({"state": "off"}, 0),
        ({"state": "pending", "location_pending": True}, 5),
    ],
)
def test_review_displays_only_genuinely_pending_ai_checks(
    client, saved_review, ai, expected
):
    saved_review["use_ai"] = ai["state"] != "off"
    saved_review["submissions"][0]["ai"] = ai
    store.save(saved_review)
    response = client.get(
        reverse("moderation:review", args=[saved_review["id"]]), {"q": "no-match"}
    )
    assert response.context["pending_ai_count"] == expected
    html = response.content.decode()
    if expected:
        assert f'data-pending-ai-count="{expected}"' in html
        assert f"{expected} AI check{'s' if expected != 1 else ''} pending." in html
    else:
        assert "data-pending-ai-count" not in html


def test_review_storage_is_json_not_database(saved_review, settings):
    assert (
        json.loads(
            (settings.REVIEW_ROOT / saved_review["id"] / "review.json").read_text(
                encoding="utf-8"
            )
        )["state"]
        == "done"
    )
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.dummy"


@pytest.mark.parametrize(
    ("activity", "research", "model_status", "expected"),
    [
        (
            "CFD simulation of hydrogen combustion on a computer",
            "This is CFD simulation only. No physical experiments are planned and no hydrogen will be handled.",
            "complete",
            "complete",
        ),
        (
            "Physical load testing of manufactured components",
            "We will perform physical load tests using laboratory equipment.",
            "issue",
            "issue",
        ),
        (
            "Computer design and experimental testing if approved",
            "If approved, chemical experiments will be carried out. The testing space is not yet identified.",
            "review",
            "review",
        ),
    ],
)
def test_facilities_comparison_distinguishes_clear_issues_from_ambiguity(
    activity, research, model_status, expected
):
    workspace = "University computer facilities"
    checks, extracted = checked(
        location=workspace, activity=activity, research_activity=research
    )
    assert checks["facilities"]["status"] == "review"  # No AI means no inferred pass.
    judgement = Judgement(
        status=model_status,
        explanation="Comparison needs the stated workspace and actual activities.",
        quotes=[workspace, research],
    )
    response = SimpleNamespace(
        output_parsed=LanguageReview(
            **{key: judgement for key in LanguageReview.model_fields}
        ),
        usage=None,
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = response
        apply_ai(list(checks.values()), extracted, STUDENT)
        sent = json.loads(client.return_value.responses.parse.call_args.kwargs["input"])
    assert sent["location"] == workspace
    assert any(activity in text for text in sent["activity_descriptions"])
    assert research in sent["activity_descriptions"]
    assert checks["facilities"]["status"] == expected
    assert {e["text"] for e in checks["facilities"]["evidence"]} == {
        workspace,
        research,
    }


@pytest.mark.parametrize(
    "quotes",
    [
        ["ELC 004"],
        ["This project uses published data and a university computer in ELC 004."],
        ["ELC 004", "A fabricated experiment that is not described in the submission."],
        ["ELC 004", "Synthetic project"],  # Project title is not activity evidence.
    ],
)
@pytest.mark.parametrize("model_status", ["complete", "issue"])
def test_facilities_cannot_pass_without_grounded_location_and_activity_quotes(
    quotes, model_status
):
    checks, extracted = checked()
    judgement = Judgement(
        status=model_status, explanation="Workspace comparison.", quotes=quotes
    )
    response = SimpleNamespace(
        output_parsed=LanguageReview(
            **{key: judgement for key in LanguageReview.model_fields}
        ),
        usage=None,
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = response
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["facilities"]["status"] == "review"
    assert "manual check required" in checks["facilities"]["message"]
    assert metadata["facilities_pending"] is True
    assert checks["facilities"]["excluded_facilities_assessments"] == [
        judgement.model_dump()
    ]


def test_existing_review_gains_pending_facilities_check_without_calls_or_lost_decisions(
    saved_review,
):
    review = saved_review
    item = review["submissions"][0]
    item["checks"] = [c for c in item["checks"] if c["id"] != "facilities"]
    item["checks"][0].update(decision="complete", note="Previously inspected.")
    review["use_ai"] = True
    item["ai"] = {"state": "complete"}
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(review["id"])
        api.assert_not_called()
    checks = updated["submissions"][0]["checks"]
    assert len(checks) == 25
    assert checks[0]["note"] == "Previously inspected."
    assert checks[0]["decision"] == "complete"
    assert next(c for c in checks if c["id"] == "facilities")["status"] == "review"
    assert updated["submissions"][0]["ai"]["facilities_pending"] is True
    assert len(jobs.snapshot(review["id"])["submissions"][0]["checks"]) == 25


def test_pending_facilities_ai_check_can_be_run_from_existing_review(
    client, saved_review, monkeypatch
):
    review = saved_review
    review["use_ai"] = True
    review["submissions"][0]["ai"] = {"state": "complete", "facilities_pending": True}
    store.save(review)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")
    with patch.object(jobs, "start") as start:
        response = client.post(
            reverse("moderation:resume", args=[review["id"]]), {"action": "retry_ai"}
        )
    assert response.status_code == 302
    start.assert_called_once_with(review["id"])
    assert store.load(review["id"])["submissions"][0]["state"] == "pending"


def numbered_rating_document():
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document(io.BytesIO(document_bytes()))
    # Two decimal lists: one starts at 4, the other overrides its start to 6.
    for idx, start in enumerate((4, 6)):
        number_id = 100 + idx
        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(number_id))
        level = OxmlElement("w:lvl")
        level.set(qn("w:ilvl"), "0")
        for tag, value in (
            ("start", str(start if idx == 0 else 1)),
            ("numFmt", "decimal"),
            ("lvlText", "%1"),
        ):
            element = OxmlElement("w:" + tag)
            element.set(qn("w:val"), value)
            level.append(element)
        abstract.append(level)
        doc.part.numbering_part.element.append(abstract)
        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(number_id))
        reference = OxmlElement("w:abstractNumId")
        reference.set(qn("w:val"), str(number_id))
        num.append(reference)
        if idx == 1:
            override = OxmlElement("w:lvlOverride")
            override.set(qn("w:ilvl"), "0")
            start_override = OxmlElement("w:startOverride")
            start_override.set(qn("w:val"), "6")
            override.append(start_override)
            num.append(override)
        doc.part.numbering_part.element.append(num)
        if idx:
            row = doc.tables[0].add_row()
            for cell, previous in zip(
                row.cells, doc.tables[0].rows[1].cells, strict=True
            ):
                cell.text = previous.text
            row.cells[0].text = "2"
        else:
            row = doc.tables[0].rows[1]
        row.cells[6].text = "(L)"
        row.cells[8].text = f"{start} (L)"
        props = row.cells[6].paragraphs[0]._p.get_or_add_pPr()
        num_props = OxmlElement("w:numPr")
        num_ref = OxmlElement("w:numId")
        num_ref.set(qn("w:val"), str(number_id))
        num_props.append(num_ref)
        props.append(num_props)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def test_automatic_word_numbers_are_visible_ratings_in_text_and_tables():
    doc = extract_document(numbered_rating_document(), "form.docx")
    checks, extracted = check_documents([doc], STUDENT)
    assert [row[6] for row in extracted["risk_rows"]] == ["4 (L)", "6 (L)"]
    assert any(p["text"] == "4 (L)" for p in doc["paragraphs"])
    assert next(c for c in checks if c["id"] == "ratings")["status"] == "complete"
    reduction = next(c for c in checks if c["id"] == "risk_reduction")
    assert reduction["status"] == "issue"
    assert "Row 1: initial 4, final 4" in reduction["message"]
    assert "Row 2: initial 6, final 6" in reduction["message"]


@pytest.mark.parametrize(
    ("initial", "final", "expected"),
    [
        ("8 (L)", "2x2=4 (L)", "complete"),
        ("6 (L)", "3x2=6 (L)", "issue"),
        ("6 (L)", "9 (L)", "issue"),
        ("2x3=6 (L)", "3 (L)", "complete"),
        ("18 (M)", "9", "complete"),
        ("18 (M)", "9 (L)", "complete"),
        ("18 (M)", "3x3=9 (L)", "complete"),
        ("18 (M)", "18", "issue"),
        ("(L)", "4 (L)", "skipped"),
    ],
)
def test_final_ratings_must_be_strictly_lower(initial, final, expected):
    doc = Document(io.BytesIO(document_bytes()))
    doc.tables[0].rows[1].cells[6].text = initial
    doc.tables[0].rows[1].cells[8].text = final
    output = io.BytesIO()
    doc.save(output)
    checks, _ = check_documents(
        [extract_document(output.getvalue(), "form.docx")], STUDENT
    )
    assert next(c for c in checks if c["id"] == "risk_reduction")["status"] == expected


def test_numbering_refresh_corrects_saved_rules_and_preserves_ai_and_decisions(
    saved_review,
):
    review = saved_review
    item = review["submissions"][0]
    file = item["files"][0]
    (store.review_dir(review["id"]) / file["id"]).write_bytes(
        numbered_rating_document()
    )
    item.pop("reader_version", None)
    item["checks"] = [c for c in item["checks"] if c["id"] != "risk_reduction"]
    ratings = next(c for c in item["checks"] if c["id"] == "ratings")
    ratings.update(
        status="issue", decision="complete", note="Inspected visible scores."
    )
    semantic = next(c for c in item["checks"] if c["id"] == "entry_quality")
    semantic.update(source="AI", message="Previous AI finding.")
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        refreshed = jobs.snapshot(review["id"])["submissions"][0]
        api.assert_not_called()
    ratings = next(c for c in refreshed["checks"] if c["id"] == "ratings")
    assert ratings["status"] == "complete"
    assert ratings["note"] == "Inspected visible scores."
    assert ratings["decision"] == "complete"
    assert (
        next(c for c in refreshed["checks"] if c["id"] == "entry_quality")["message"]
        == "Previous AI finding."
    )
    assert (
        next(c for c in refreshed["checks"] if c["id"] == "risk_reduction")["status"]
        == "issue"
    )


@pytest.mark.parametrize(
    "explanation",
    [
        "Final Result calculations contradict the initial severity/likelihood: different multipliers.",
        "Final score is provided without severity and likelihood multipliers.",
        "Risk ratings should use the same factors before and after controls.",
    ],
)
@pytest.mark.parametrize("project_in_role", [False, True])
def test_ai_rating_claims_cannot_create_field_entry_issues(
    explanation, project_in_role
):
    checks, extracted = checked(
        student_job_title="Synthetic project" if project_in_role else "Student"
    )
    ordinary = Judgement(status="complete", explanation="Complete.", quotes=["ELC 004"])
    parsed = LanguageReview(
        **{
            key: Judgement(
                status="issue", explanation=explanation, quotes=["2x1=2 (L)"]
            )
            if key == "entry_quality"
            else ordinary
            for key in LanguageReview.model_fields
        }
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=parsed, usage=None
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
    check = checks["entry_quality"]
    assert check["status"] == ("issue" if project_in_role else "review")
    assert check["source"] == "Rule"
    assert "AI risk-rating comments were excluded" in check["message"]
    assert checks["risk_reduction"]["status"] == "complete"


def test_saved_ai_rating_finding_is_withdrawn_and_queued_for_recheck(saved_review):
    item = saved_review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    check.update(
        status="issue",
        source="AI",
        message="Final Result calculations contradict the initial severity/likelihood values.",
        decision="complete",
        note="Moderator note.",
        history=[{"note": "Prior decision"}],
    )
    previous = {key: check[key] for key in ("status", "source", "message", "evidence")}
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    assert check["status"] == "review"
    assert check["superseded_rating_finding"] == previous
    assert check["decision"] == "complete"
    assert check["note"] == "Moderator note."
    assert check["history"] == [{"note": "Prior decision"}]
    assert item["ai"]["entry_quality_pending"] is True
    assert jobs.snapshot(saved_review["id"]) == updated


def test_ai_cannot_override_embedded_signature_presence_through_entry_quality():
    checks, extracted = checked()
    extracted["paragraphs"].append(
        {
            "text": "Supervisor sign:",
            "images": ["word/media/signature.png"],
            "states": [],
        }
    )
    ordinary = Judgement(status="complete", explanation="No issue.", quotes=["ELC 004"])
    signature_claim = Judgement(
        status="issue",
        explanation="Supervisor signature lines are blank despite dates being present.",
        quotes=["Supervisor sign:"],
    )
    parsed = LanguageReview(
        **{
            key: signature_claim if key == "entry_quality" else ordinary
            for key in LanguageReview.model_fields
        }
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=parsed, usage=None
        )
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
        payload = json.loads(
            client.return_value.responses.parse.call_args.kwargs["input"]
        )
    assert payload["embedded_image_context"][-1]["embedded_images"] == 1
    assert any(
        c["criterion"] == "supervisor_ethics" and c["status"] == "complete"
        for c in payload["sign_off_checks"]
    )
    assert checks["entry_quality"]["status"] == "review"
    assert "signature comments were excluded" in checks["entry_quality"]["message"]
    assert checks["supervisor_ethics"]["status"] == "complete"
    assert metadata["entry_quality_pending"] is True
    assert checks["entry_quality"]["excluded_entry_quality_assessments"] == [
        signature_claim.model_dump()
    ]


def test_discarded_entry_assessment_is_pending_and_successful_retry_clears_it(
    saved_review,
):
    item = saved_review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    check.update(
        status="review",
        source="Rule",
        message="AI signature comments were excluded: signature presence is checked separately. Review other field entries manually.",
        note="Retained moderator note.",
    )
    item["ai"] = {"state": "complete"}
    saved_review["use_ai"] = True
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    assert item["ai"]["entry_quality_pending"] is True
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    assert check["status"] == "review"
    assert check["note"] == "Retained moderator note."
    assert "not a student correction request" in check["message"]
    assert jobs.snapshot(saved_review["id"]) == updated
    checks, extracted = checked()
    judgement = Judgement(
        status="complete",
        explanation="Field entries are appropriate.",
        quotes=["Job Title: Student"],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{key: judgement for key in LanguageReview.model_fields}
            ),
            usage=None,
        )
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
    assert not metadata.get("entry_quality_pending")
    assert checks["entry_quality"]["status"] == "complete"


@pytest.mark.parametrize("duplicate", [False, True])
def test_field_entry_ai_keeps_required_omissions_in_dedicated_checks(duplicate):
    doc = Document(io.BytesIO(document_bytes()))
    for index, paragraph in enumerate(doc.paragraphs):
        if paragraph.text == "Supervisor Name:":
            doc.paragraphs[index + 1].text = ""
    data = io.BytesIO()
    doc.save(data)
    found, extracted = check_documents(
        [extract_document(data.getvalue(), "synthetic.docx")], STUDENT
    )
    checks = {c["id"]: c for c in found}
    judgement = Judgement(
        status="issue" if duplicate else "complete",
        explanation="Supervisor Name field in the ethics header is left blank and requires completion. Other entered roles are appropriate."
        if duplicate
        else "Entered student and staff roles are appropriate.",
        quotes=["Job Title: Student"],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{key: judgement for key in LanguageReview.model_fields}
            ),
            usage=None,
        )
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
        payload = json.loads(
            client.return_value.responses.parse.call_args.kwargs["input"]
        )
    assert checks["ethics_details"]["status"] == "issue"
    assert "supervisor name" in checks["ethics_details"]["message"]
    assert (
        next(
            c
            for c in payload["dedicated_completion_checks"]
            if c["criterion"] == "ethics_details"
        )["status"]
        == "issue"
    )
    assert checks["entry_quality"]["status"] == ("review" if duplicate else "complete")
    assert bool(metadata.get("entry_quality_pending")) == duplicate
    if duplicate:
        assert checks["entry_quality"]["excluded_entry_quality_assessments"] == [
            judgement.model_dump()
        ]


def test_saved_duplicate_completion_finding_preserves_dedicated_issue(saved_review):
    item = saved_review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    check.update(
        status="issue",
        source="AI",
        message="The Supervisor Name field in the Ethics form header is left blank and requires completion.",
        note="Moderator note.",
        history=[{"note": "Earlier review"}],
    )
    dedicated = next(c for c in item["checks"] if c["id"] == "ethics_details")
    dedicated.update(status="issue", message="Missing: supervisor name.")
    previous = {key: check[key] for key in ("status", "source", "message", "evidence")}
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    assert check["status"] == "review"
    assert check["superseded_completion_finding"] == previous
    assert check["note"] == "Moderator note."
    assert check["history"] == [{"note": "Earlier review"}]
    assert next(c for c in item["checks"] if c["id"] == "ethics_details") == dedicated
    assert item["ai"]["entry_quality_pending"] is True
    assert jobs.snapshot(saved_review["id"]) == updated


@pytest.mark.parametrize("project_in_role", [False, True])
def test_assessor_identity_is_not_duplicated_as_wrong_field_content(project_in_role):
    checks, extracted = checked(
        assessor="Different Lecturer",
        student_job_title="Synthetic project" if project_in_role else "Student",
    )
    original_identity = dict(checks["identity"])
    ordinary = Judgement(
        status="complete", explanation="Other entries appropriate.", quotes=["ELC 004"]
    )
    duplicate = Judgement(
        status="issue",
        explanation="Text is in the wrong field: the Assessor field contains a staff name rather than the student name.",
        quotes=["Assessor: Different Lecturer"],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{
                    key: duplicate if key == "entry_quality" else ordinary
                    for key in LanguageReview.model_fields
                }
            ),
            usage=None,
        )
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["identity"] == original_identity
    assert checks["identity"]["status"] == "issue"
    assert checks["entry_quality"]["status"] == (
        "issue" if project_in_role else "review"
    )
    assert checks["entry_quality"]["source"] == "Rule"
    assert checks["entry_quality"]["excluded_entry_quality_assessments"] == [
        duplicate.model_dump()
    ]
    assert metadata["entry_quality_pending"] is True


def test_saved_assessor_duplicate_preserves_identity_and_prior_archives(saved_review):
    item = saved_review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    prior_archive = {"message": "Earlier archived completion finding."}
    check.update(
        status="issue",
        source="AI",
        message="Assessor contains a staff name instead of the student name and is in the wrong field.",
        note="Moderator note.",
        history=[{"note": "Earlier decision"}],
        superseded_completion_finding=prior_archive,
    )
    identity = next(c for c in item["checks"] if c["id"] == "identity")
    identity.update(
        status="issue", message="Assessor does not match the submitting student."
    )
    previous = {key: check[key] for key in ("status", "source", "message", "evidence")}
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    assert check["status"] == "review"
    assert check["superseded_dedicated_finding"] == previous
    assert check["superseded_completion_finding"] == prior_archive
    assert check["note"] == "Moderator note."
    assert check["history"] == [{"note": "Earlier decision"}]
    assert next(c for c in item["checks"] if c["id"] == "identity") == identity
    assert item["ai"]["entry_quality_pending"] is True
    assert jobs.snapshot(saved_review["id"]) == updated


@pytest.mark.parametrize("quote_row", [False, True])
def test_hazard_quote_verifies_against_table_when_pdf_text_order_differs(quote_row):
    hazard = "Eye strain and neck discomfort"
    checks, extracted = checked(hazard=hazard)
    extracted["paragraphs"] = [
        p for p in extracted["paragraphs"] if hazard not in p["text"]
    ]
    quote = " | ".join(extracted["risk_rows"][0]) if quote_row else hazard
    ordinary = Judgement(status="complete", explanation="Complete.", quotes=["ELC 004"])
    judgement = Judgement(
        status="complete",
        explanation="Hazards concern health and safety.",
        quotes=[quote],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{
                    key: judgement if key == "hs_relevance" else ordinary
                    for key in LanguageReview.model_fields
                }
            ),
            usage=None,
        )
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["hs_relevance"]["status"] == "complete"
    assert checks["hs_relevance"]["source"] == "AI"
    assert checks["hs_relevance"]["evidence"][0]["text"] == quote
    assert not metadata.get("hs_relevance_pending")


@pytest.mark.parametrize(
    "quote", ["ELC 004", "A fabricated hazard that is absent from this submission"]
)
def test_unverified_or_unrelated_hazard_quote_is_retryable_not_passed(quote):
    checks, extracted = checked()
    judgement = Judgement(
        status="complete", explanation="All hazards are relevant.", quotes=[quote]
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{key: judgement for key in LanguageReview.model_fields}
            ),
            usage=None,
        )
        metadata = apply_ai(list(checks.values()), extracted, STUDENT)
    check = checks["hs_relevance"]
    assert check["status"] == "review"
    assert "assessment was attempted" in check["message"]
    assert "Language review is pending" not in check["message"]
    assert "not a student correction request" in check["message"]
    assert check["excluded_hs_relevance_assessments"] == [judgement.model_dump()]
    assert metadata["hs_relevance_pending"] is True


def test_saved_hazard_verification_failure_gets_clear_message_and_retry(saved_review):
    item = saved_review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "hs_relevance")
    check.update(
        status="review",
        source="Rule",
        message="Language review is pending. AI evidence could not be verified for all required sources; manual check required.",
        note="Moderator note.",
        history=[{"note": "Earlier decision"}],
    )
    previous = {key: check[key] for key in ("status", "source", "message", "evidence")}
    saved_review["use_ai"] = True
    item["ai"] = {"state": "complete"}
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "hs_relevance")
    assert check["status"] == "review"
    assert "assessment was attempted" in check["message"]
    assert "Language review is pending" not in check["message"]
    assert check["superseded_hs_evidence_finding"] == previous
    assert check["note"] == "Moderator note."
    assert check["history"] == [{"note": "Earlier decision"}]
    assert item["ai"]["hs_relevance_pending"] is True
    assert jobs.snapshot(saved_review["id"]) == updated


def test_rule_only_hazard_review_is_not_described_as_pending_processing():
    checks, _ = checked()
    assert checks["hs_relevance"]["status"] == "review"
    assert "pending" not in checks["hs_relevance"]["message"].lower()


def test_saved_ai_signature_conflict_is_withdrawn_without_overriding_signoff(
    saved_review,
):
    review = saved_review
    item = review["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "entry_quality")
    check.update(
        status="issue", source="AI", message="Supervisor signatures appear missing."
    )
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(review["id"])["submissions"][0]
        api.assert_not_called()
    check = next(c for c in updated["checks"] if c["id"] == "entry_quality")
    assert check["status"] == "review"
    assert check["superseded_ai_finding"]["status"] == "issue"
    assert updated["ai"]["entry_quality_pending"] is True
    assert (
        next(c for c in updated["checks"] if c["id"] == "supervisor_ethics")["status"]
        == "complete"
    )


@pytest.mark.parametrize("placement", ["inline", "before", "after"])
def test_signoff_evidence_embeds_images_and_deduplicates_saved_entries(
    client, saved_review, placement
):
    review = saved_review
    item = review["submissions"][0]
    doc = Document()
    doc.add_paragraph("Supervisor Name: Synthetic Supervisor    Job Title: Professor")
    signature = doc.add_paragraph("Signature:    Date: 12/11/2026")
    image_paragraph = (
        signature.insert_paragraph_before()
        if placement == "before"
        else doc.add_paragraph()
        if placement == "after"
        else signature
    )
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII="
    )
    image_paragraph.add_run().add_picture(io.BytesIO(png))
    output = io.BytesIO()
    doc.save(output)
    file = item["files"][0]
    (store.review_dir(review["id"]) / file["id"]).write_bytes(output.getvalue())
    document = extract_document(output.getvalue(), file["name"])
    item["documents"] = [document]
    from moderation.checks import combine_signoff

    paragraphs = [
        {**p, "ref": f"Document 1, paragraph {index}"}
        for index, p in enumerate(document["paragraphs"], 1)
    ]
    check = combine_signoff("supervisor_ra", paragraphs, "Supervisor Name")
    assert check["status"] == "complete"
    assert len(check["evidence"]) == (2 if placement == "inline" else 3)
    assert any(e.get("images") for e in check["evidence"])
    # Simulate saved evidence from before image metadata and deduplication.
    check["evidence"] = [
        {"location": e["location"], "text": e["text"]}
        for e in check["evidence"]
        for _ in range(2)
    ]
    item["checks"] = [check]
    store.save(review)
    response = client.get(
        reverse("moderation:submission", args=[review["id"], item["id"]])
    )
    displayed = next(
        c for c in response.context["checks"] if c["id"] == "supervisor_ra"
    )["evidence"]
    assert len(displayed) == (2 if placement == "inline" else 3)
    image_url = next(e["images"][0] for e in displayed if e["images"])
    assert f'class="evidence-image" src="{image_url}"' in response.content.decode()
    image_response = client.get(image_url)
    assert image_response.status_code == 200
    assert image_response["Content-Type"] == "image/png"
    assert image_response.content == png


@pytest.mark.parametrize(
    "placement,expected",
    [
        ("before_name", "issue"),
        ("separated", "issue"),
        ("before_signature", "complete"),
    ],
)
def test_preceding_signoff_image_stays_with_named_signatory(placement, expected):
    from moderation.checks import combine_signoff

    def paragraph(text, images=None):
        return {"text": text, "images": images or [], "states": []}

    name = paragraph("Supervisor Name: Synthetic Supervisor    Job Title: Lecturer")
    image = paragraph("", ["word/media/synthetic.png"])
    signature = paragraph("Signature:    Date: 15/11/2026")
    scope = [name, image, signature]
    if placement == "before_name":
        scope = [image, name, signature]
    elif placement == "separated":
        scope = [name, image, paragraph("Other unrelated text."), signature]
    check = combine_signoff("supervisor_ra", scope, "Supervisor Name")
    assert check["status"] == expected
    assert any(e.get("images") for e in check["evidence"]) == (expected == "complete")


def test_saved_word_signoff_refresh_preserves_moderation_and_original(saved_review):
    item = saved_review["submissions"][0]
    item.pop("signoff_image_version")
    doc = Document(io.BytesIO(document_bytes()))
    signature = next(
        p
        for p in doc.paragraphs
        if p.text.startswith("Signature: Synthetic Supervisor")
    )
    signature.text = "Signature:    Date: 15/11/2026"
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII="
    )
    signature.insert_paragraph_before().add_run().add_picture(io.BytesIO(png))
    data = io.BytesIO()
    doc.save(data)
    file = item["files"][0]
    path = store.review_dir(saved_review["id"]) / file["id"]
    path.write_bytes(data.getvalue())
    item["documents"] = [extract_document(data.getvalue(), file["name"])]
    old = next(c for c in item["checks"] if c["id"] == "supervisor_ra")
    old.update(
        status="issue",
        message="Missing: signature.",
        decision="review",
        note="Moderator note.",
        history=[{"note": "Earlier review"}],
    )
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "supervisor_ra")
    assert check["status"] == "complete"
    assert check["decision"] == "review"
    assert check["note"] == "Moderator note."
    assert check["history"] == old["history"]
    assert check["superseded_signoff_finding"] == old
    assert any(e.get("images") for e in check["evidence"])
    assert path.read_bytes() == data.getvalue()
    assert jobs.snapshot(saved_review["id"]) == updated


def ethics_dates_document_bytes(student_date, supervisor_date):
    doc = Document(io.BytesIO(document_bytes()))
    for paragraph in doc.paragraphs[-4:]:
        paragraph._p.getparent().remove(paragraph._p)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Student sign:"
    table.cell(0, 0).add_paragraph("Synthetic Student")
    table.cell(0, 1).text = "Supervisor sign:"
    table.cell(0, 1).add_paragraph("Synthetic Supervisor")
    for cell, value in [
        (table.cell(1, 0), student_date),
        (table.cell(1, 1), supervisor_date),
    ]:
        cell.text = "Date:"
        if value is not None:
            cell.add_paragraph(value)
    data = io.BytesIO()
    doc.save(data)
    return data.getvalue()


@pytest.mark.parametrize("student_date", ["15/11/2026", None])
@pytest.mark.parametrize("supervisor_date", ["16/11/2026", None])
def test_ethics_dates_beneath_labels_stay_with_correct_signatory(
    student_date, supervisor_date
):
    document = extract_document(
        ethics_dates_document_bytes(student_date, supervisor_date), "synthetic.docx"
    )
    found, _ = check_documents([document], STUDENT)
    checks = {c["id"]: c for c in found}
    for key, value in [
        ("student_ethics", student_date),
        ("supervisor_ethics", supervisor_date),
    ]:
        check = checks[key]
        assert check["status"] == ("complete" if value else "issue")
        if value:
            assert any(e["text"] == value for e in check["evidence"])
        else:
            assert "Missing: date" in check["message"]


def test_saved_split_date_refresh_preserves_prior_findings_and_moderation(saved_review):
    item = saved_review["submissions"][0]
    item["signoff_image_version"] = 1
    file = item["files"][0]
    data = ethics_dates_document_bytes("15/11/2026", "16/11/2026")
    path = store.review_dir(saved_review["id"]) / file["id"]
    path.write_bytes(data)
    item["documents"] = [extract_document(data, file["name"])]
    old = next(c for c in item["checks"] if c["id"] == "student_ethics")
    prior = {"message": "First archived finding."}
    old.update(
        status="issue",
        message="Missing: date.",
        decision="review",
        note="Moderator note.",
        history=[{"note": "Earlier review"}],
        superseded_signoff_finding=prior,
    )
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "student_ethics")
    assert check["status"] == "complete"
    assert check["decision"] == "review"
    assert check["note"] == "Moderator note."
    assert check["history"] == old["history"]
    assert check["superseded_signoff_finding"] == prior
    assert check["signoff_refresh_history"][-1]["message"] == "Missing: date."
    assert item["signoff_image_version"] == 2
    assert path.read_bytes() == data
    assert jobs.snapshot(saved_review["id"]) == updated


@pytest.mark.parametrize(
    "ai_state,rejected,pending",
    [
        ("complete", False, True),
        ("complete", True, False),
        ("off", False, False),
        ("failed", False, False),
    ],
)
def test_saved_facilities_message_explains_manual_review(
    saved_review, ai_state, rejected, pending
):
    review = saved_review
    review["use_ai"] = ai_state != "off"
    item = review["submissions"][0]
    item["ai"] = {"state": ai_state}
    check = next(c for c in item["checks"] if c["id"] == "facilities")
    check.update(
        message="Compare facilities. AI comparison is pending; otherwise check manually.",
        decision="complete",
        note="Inspected manually.",
    )
    if rejected:
        check["message"] += (
            " AI evidence could not be verified for all required sources; manual check required."
        )
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        updated = jobs.snapshot(review["id"])
        api.assert_not_called()
    item = updated["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "facilities")
    assert "AI comparison is pending" not in check["message"]
    assert "Manual review required." in check["message"]
    assert ("No AI conclusion is recorded" in check["message"]) == pending
    assert bool(item["ai"].get("facilities_pending")) == (pending or rejected)
    assert check["status"] == "review"
    assert check["decision"] == "complete"
    assert check["note"] == "Inspected manually."
    assert jobs.snapshot(review["id"]) == updated


@pytest.mark.parametrize("labelled", [False, True])
def test_facilities_accepts_exact_workspace_quotes_with_field_label(labelled):
    workspace = (
        "Northumbria University computer facilities and home-based computer research"
    )
    research = "The project will involve a literature review and computer based numerical modelling."
    checks, extracted = checked(location=workspace, research_activity=research)
    quote = "Area/Activity: " + workspace if labelled else workspace
    judgement = Judgement(
        status="complete",
        explanation="Computer-based activities match the stated workspace.",
        quotes=[quote, research],
    )
    response = SimpleNamespace(
        output_parsed=LanguageReview(
            **{key: judgement for key in LanguageReview.model_fields}
        ),
        usage=None,
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = response
        apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["facilities"]["status"] == "complete"
    assert checks["facilities"]["source"] == "AI"
    assert quote in [e["text"] for e in checks["facilities"]["evidence"]]


@pytest.mark.parametrize(
    "area",
    [
        "in campus",
        "testing",
        "ELC 004",
        "CNC milling",
        "3D printing",
        "additive manufacturing",
        "FDM fabrication of polymer specimens",
        "Acoustic characterisation using a calibrated impedance tube",
    ],
)
def test_every_nonblank_area_requires_content_assessment(area):
    checks, _ = checked(location=area)
    assert checks["location"]["status"] == "review"
    assert checks["location"]["source"] == "Rule"


@pytest.mark.parametrize(
    "area,status",
    [
        ("in campus", "issue"),
        ("testing", "issue"),
        ("3D printing", "complete"),
        ("additive manufacturing", "complete"),
        ("FDM fabrication of polymer specimens", "complete"),
        ("ELC 004", "complete"),
        ("Home office", "complete"),
        ("PC at home", "complete"),
        ("Laptop workstation in my flat", "complete"),
        ("home", "issue"),
        ("Design/Simulation", "issue"),
    ],
)
def test_area_uses_evidence_backed_ai_assessment(area, status):
    checks, extracted = checked(location=area)
    judgement = Judgement(
        status=status,
        explanation="Assessment of the Area/Activity entry itself.",
        quotes=["Area/Activity: " + area],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{key: judgement for key in LanguageReview.model_fields}
            ),
            usage=None,
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
    assert checks["location"]["status"] == status
    assert checks["location"]["source"] == "AI"


def test_blank_area_is_an_issue_without_ai():
    checks, _ = checked(location="")
    assert checks["location"]["status"] == "issue"
    assert "missing" in checks["location"]["message"]


@pytest.mark.parametrize(
    ("activity", "research", "status"),
    [
        (
            "CFD simulation using a computer only",
            "The project involves only computer simulation. No physical testing is planned.",
            "complete",
        ),
        (
            "Physical load testing of a manufactured component",
            "Physical load tests will be performed if approval is obtained.",
            "issue",
        ),
        (
            "Computer simulation and possible testing",
            "Methods are not yet decided.",
            "review",
        ),
    ],
)
@pytest.mark.parametrize(
    "location",
    [
        "University computer labs, home office, university library workspace",
        "Engineering laboratories and computer facilities, Example University, Example City",
    ],
)
def test_computer_locations_use_activity_context_in_ai_review(
    activity, research, status, location
):
    checks, extracted = checked(
        location=location, activity=activity, research_activity=research
    )
    judgement = Judgement(
        status=status,
        explanation="Location assessed against the actual planned activities.",
        quotes=["Area/Activity: " + location, activity, research],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{key: judgement for key in LanguageReview.model_fields}
            ),
            usage=None,
        )
        apply_ai(list(checks.values()), extracted, STUDENT)
        payload = json.loads(
            client.return_value.responses.parse.call_args.kwargs["input"]
        )
        instructions = client.return_value.responses.parse.call_args.kwargs[
            "instructions"
        ]
    assert payload["location"] == location
    assert payload["risk_table_rows"][0][1] == activity
    assert research in payload["activity_descriptions"]
    assert "RA activities AND ethics Research" in instructions
    assert "no planned physical work, including conditional" in instructions
    assert checks["location"]["status"] == status
    assert checks["location"]["source"] == "AI"
    assert checks["facilities"]["status"] == status
    assert checks["location"]["lab_context_version"] == 1
    assert checks["facilities"]["lab_context_version"] == 1


@pytest.mark.parametrize("previous_status", ["complete", "issue"])
@pytest.mark.parametrize("previous_version", [0, 1])
def test_saved_location_issue_is_marked_for_new_computer_policy(
    saved_review, previous_status, previous_version
):
    item = saved_review["submissions"][0]
    item["computer_location_version"] = previous_version
    check = next(c for c in item["checks"] if c["id"] == "location")
    check.update(
        status=previous_status,
        source="AI",
        message="Computer labs and home are too generic.",
        decision="complete",
        note="Reviewed location.",
        history=[{"note": "Existing decision"}],
    )
    previous = {key: check[key] for key in ("status", "source", "message", "evidence")}
    saved_review["use_ai"] = True
    store.save(saved_review)
    with patch("moderation.jobs.apply_ai") as api:
        refreshed = jobs.snapshot(saved_review["id"])
        api.assert_not_called()
    item = refreshed["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "location")
    assert check["status"] == "review"
    assert check["decision"] == "complete"
    assert check["note"] == "Reviewed location."
    assert check["history"] == [{"note": "Existing decision"}]
    assert check["superseded_computer_location_finding"] == previous
    assert check["superseded_workspace_specificity_finding"] == previous
    assert item["computer_location_version"] == 2
    assert item["ai"]["location_pending"] is True
    assert jobs.snapshot(saved_review["id"]) == refreshed


def test_saved_area_activity_refresh_preserves_decisions_and_other_ai(saved_review):
    review = saved_review
    item = review["submissions"][0]
    item.pop("area_activity_version", None)
    doc = extract_document(
        document_bytes(location="in campus"), item["files"][0]["name"]
    )
    item["documents"] = [doc]
    check = next(c for c in item["checks"] if c["id"] == "location")
    check.update(
        status="complete",
        source="AI",
        message="Previously accepted.",
        decision="complete",
        note="Moderator note.",
    )
    other = next(c for c in item["checks"] if c["id"] == "narrative")
    other.update(source="AI", message="Existing narrative finding.")
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        refreshed = jobs.snapshot(review["id"])
        api.assert_not_called()
    item = refreshed["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "location")
    assert check["status"] == "review"
    assert check["source"] == "Rule"
    assert check["decision"] == "complete"
    assert check["note"] == "Moderator note."
    assert (
        check["superseded_area_activity_finding"]["message"] == "Previously accepted."
    )
    assert next(c for c in item["checks"] if c["id"] == "narrative") == other
    assert jobs.snapshot(review["id"]) == refreshed


@pytest.mark.parametrize(
    "answers,expected",
    [
        (("Y/ N", "Y/N"), "issue"),
        (("", "N"), "issue"),
        (("Yes / No", ""), "issue"),
        (("Y", "No"), "complete"),
        (("Yes", "N"), "complete"),
        (("Possibly", "N"), "review"),
    ],
)
def test_unanswered_admin_options_are_issues_not_ambiguity(answers, expected):
    document = extract_document(document_bytes(), "form.docx")
    questions = [
        p
        for p in document["paragraphs"]
        if "Generic to the University" in p["text"]
        or "related risk assessment that may require" in p["text"]
    ]
    for paragraph, answer in zip(questions, answers, strict=True):
        paragraph["text"] = paragraph["text"].rsplit("?", 1)[0] + "? " + answer
    checks, _ = check_documents([document], STUDENT)
    check = next(c for c in checks if c["id"] == "admin")
    assert check["status"] == expected
    if expected == "issue":
        assert "unanswered" in check["message"]


def test_saved_admin_refresh_flags_unanswered_options_and_preserves_decisions(
    saved_review,
):
    review = saved_review
    item = review["submissions"][0]
    item.pop("admin_check_version", None)
    for paragraph in item["documents"][0]["paragraphs"]:
        if "Generic to the University" in paragraph["text"]:
            paragraph["text"] = paragraph["text"].rsplit("?", 1)[0] + "? Y/ N"
    check = next(c for c in item["checks"] if c["id"] == "admin")
    check.update(
        status="review", decision="complete", note="Moderator checked original."
    )
    store.save(review)
    with patch("moderation.jobs.apply_ai") as api:
        refreshed = jobs.snapshot(review["id"])
        api.assert_not_called()
    check = next(c for c in refreshed["submissions"][0]["checks"] if c["id"] == "admin")
    assert check["status"] == "issue"
    assert "1 unanswered" in check["message"]
    assert check["decision"] == "complete"
    assert check["note"] == "Moderator checked original."
    assert jobs.snapshot(review["id"]) == refreshed
