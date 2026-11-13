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
from moderation.checks import check_documents
from moderation.criteria import effective_status, overall
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
        "Student Name: Synthetic Student    Job Title: Student",
        f"Signature: {'Synthetic Student' if not missing_signature else ''}",
        "Date: 12/11/2026",
        "To be completed by the Line Manager",
        "Supervisor Name: Synthetic Supervisor    Job Title: Lecturer",
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
    for key in checks.keys() - {
        "hs_relevance",
        "entry_quality",
        "facilities",
        "location",
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
    assert checks["specialists"]["status"] == "review"
    assert "COSHH" in checks["specialists"]["message"]
    assert "supporting" in checks["specialists"]["message"]


def test_non_health_and_safety_hazard_is_flagged():
    checks, _ = checked(hazard="Loss or corruption of simulation data")
    assert checks["hs_relevance"]["message"].startswith("Potential non-H&S")


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
        == 400
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
            "review",
        ),
        (
            "Computer design and experimental testing if approved",
            "If approved, chemical experiments will be carried out. The testing space is not yet identified.",
            "review",
            "review",
        ),
    ],
)
def test_facilities_comparison_keeps_both_sources_and_manual_mismatches(
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
def test_facilities_cannot_pass_without_grounded_location_and_activity_quotes(quotes):
    checks, extracted = checked()
    judgement = Judgement(
        status="complete", explanation="All consistent.", quotes=quotes
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
    assert checks["facilities"]["status"] == "review"
    assert "manual check required" in checks["facilities"]["message"]


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
        ("(L)", "4 (L)", "unable"),
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
        apply_ai(list(checks.values()), extracted, STUDENT)
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


@pytest.mark.parametrize("adjacent_image", [False, True])
def test_signoff_evidence_embeds_images_and_deduplicates_saved_entries(
    client, saved_review, adjacent_image
):
    review = saved_review
    item = review["submissions"][0]
    doc = Document()
    doc.add_paragraph("Supervisor Name: Synthetic Supervisor    Job Title: Professor")
    signature = doc.add_paragraph("Signature:    Date: 12/11/2026")
    image_paragraph = doc.add_paragraph() if adjacent_image else signature
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
    assert len(check["evidence"]) == (3 if adjacent_image else 2)
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
    displayed = response.context["checks"][0]["evidence"]
    assert len(displayed) == (3 if adjacent_image else 2)
    image_url = next(e["images"][0] for e in displayed if e["images"])
    assert f'class="evidence-image" src="{image_url}"' in response.content.decode()
    image_response = client.get(image_url)
    assert image_response.status_code == 200
    assert image_response["Content-Type"] == "image/png"
    assert image_response.content == png


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
    assert bool(item["ai"].get("facilities_pending")) == pending
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
