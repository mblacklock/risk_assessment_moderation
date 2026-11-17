"""Synthetic v2 regressions; mocked AI tests verify safeguards, not model accuracy."""

# Imported pytest fixture is intentionally also a test parameter.
# ruff: noqa: F811
import copy
import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse
from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

from moderation import store
from moderation.ai import Judgement, LanguageReview, apply_ai
from moderation.checks import check_documents
from moderation.criteria import effective_status
from moderation.documents import extract_document, highlighted_yes_no
from moderation.feedback import fallback_wording, feedback_items, feedback_signature
from moderation.tests.test_review import STUDENT, document_bytes, grouped_risk_pdf_bytes
from moderation.tests.test_workflow import workflow_review  # noqa: F401
from moderation.validation import comparison_token, historical_adjudications


def extract(doc):
    buffer = io.BytesIO()
    doc.save(buffer)
    return extract_document(buffer.getvalue(), "synthetic.docx")


def run(doc):
    checks, context = check_documents([extract(doc)], STUDENT)
    return {c["id"]: c for c in checks}, context


def ai_response(checks, context, key, judgement):
    base = Judgement(
        status="review",
        explanation="Inspect the evidence.",
        quotes=["Synthetic project"],
    )
    with patch("moderation.ai.OpenAI") as client:
        client.return_value.responses.parse.return_value = SimpleNamespace(
            output_parsed=LanguageReview(
                **{
                    k: judgement if k == key else base
                    for k in LanguageReview.model_fields
                }
            ),
            usage=None,
        )
        metadata = apply_ai(list(checks.values()), context, STUDENT)
        payload = json.loads(
            client.return_value.responses.parse.call_args.kwargs["input"]
        )
    return metadata, payload


def test_separate_ra_sections_keep_own_locations_rows_and_dedicated_location():
    doc = Document(io.BytesIO(document_bytes(location="Computer software work")))
    second = copy.deepcopy(doc.tables[0]._tbl)
    area = doc.add_paragraph("Area/Activity: Physical testing")
    workspace = doc.add_paragraph("Location: Synthetic materials laboratory")
    doc.tables[0]._tbl.addnext(area._p)
    area._p.addnext(workspace._p)
    workspace._p.addnext(second)
    doc.tables[1].cell(1, 1).text = "Tensile testing"
    checks, context = run(doc)
    sections = context["risk_sections"]
    assert len(sections) == 2
    assert sections[0]["risk_rows"][0][1] == "Computer work"
    assert sections[1]["risk_rows"][0][1] == "Tensile testing"
    assert sections[1]["location"] == "Synthetic materials laboratory"
    assert all(not s["association_uncertain"] for s in sections)
    assert "Synthetic materials laboratory" in context["location"]
    _, payload = ai_response(
        checks,
        context,
        "location",
        Judgement(
            status="complete",
            explanation="All sections considered.",
            quotes=["Computer software work"],
        ),
    )
    assert len(payload["risk_sections"]) == 2
    assert (
        checks["location"]["status"] == "review"
    )  # Cannot clear both using only first entry.


def test_dedicated_location_before_area_is_available():
    doc = Document(io.BytesIO(document_bytes(location="")))
    for p in doc.paragraphs:
        if p.text.startswith("Area/Activity:"):
            p.insert_paragraph_before("Location: Synthetic test laboratory")
    checks, context = run(doc)
    assert "Synthetic test laboratory" in context["location"]
    assert checks["location"]["status"] == "review"


def test_blank_second_ra_location_cannot_be_cleared_by_first_section_quote():
    doc = Document(io.BytesIO(document_bytes()))
    second = copy.deepcopy(doc.tables[0]._tbl)
    area = doc.add_paragraph("Area/Activity:")
    doc.tables[0]._tbl.addnext(area._p)
    area._p.addnext(second)
    checks, context = run(doc)
    assert checks["location"]["status"] == "issue"
    ai_response(
        checks,
        context,
        "location",
        Judgement(
            status="complete",
            explanation="First location is specific.",
            quotes=["ELC 004"],
        ),
    )
    assert checks["location"]["status"] == "issue"


def test_explicit_word_vertical_merge_can_share_numbered_activity():
    doc = Document(io.BytesIO(document_bytes()))
    values = ["2", "", "Flying fragments", "Student", "2", "3", "6", "Use shield", "2"]
    for cell, value in zip(doc.tables[0].add_row().cells, values, strict=True):
        cell.text = value
    doc.tables[0].cell(1, 1)._tc.get_or_add_tcPr().append(
        parse_xml(f'<w:vMerge {nsdecls("w")} w:val="restart"/>')
    )
    doc.tables[0].rows[2]._tr.tc_lst[1].get_or_add_tcPr().append(
        parse_xml(f"<w:vMerge {nsdecls('w')}/>")
    )
    checks, context = run(doc)
    assert checks["risk_table"]["status"] == "complete"
    assert context["risk_rows"][1][1] == "Computer work"


@pytest.mark.parametrize(("identifier", "expected"), [("", "complete"), ("2", "issue")])
def test_continuation_activity_does_not_blindly_fill_numbered_rows(
    identifier, expected
):
    doc = Document(io.BytesIO(document_bytes()))
    values = [
        identifier,
        "",
        "Flying fragments",
        "Student",
        "2",
        "3",
        "6",
        "Use shield",
        "2",
    ]
    for cell, value in zip(doc.tables[0].add_row().cells, values, strict=True):
        cell.text = value
    checks, context = run(doc)
    assert checks["risk_table"]["status"] == expected
    assert context["risk_rows"][1][1] == ("Computer work" if not identifier else "")
    if not identifier:
        assert (
            "Activity shared from Risk row 1"
            in checks["risk_table"]["evidence"][-1]["text"]
        )


def test_pdf_missing_item_continuation_retained_and_checked():
    import pymupdf

    # Existing synthetic multi-page table demonstrates page continuations stay readable.
    doc = extract_document(grouped_risk_pdf_bytes(), "synthetic.pdf")
    checks, context = check_documents([doc], STUDENT)
    assert len(context["risk_rows"]) == 6
    assert next(c for c in checks if c["id"] == "risk_table")["status"] == "complete"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox((30, 50, 550, 750), "Risk assessment text " * 20)
        unresolved = extract_document(pdf.tobytes(), "synthetic.pdf")
    checks, _ = check_documents([unresolved], STUDENT)
    assert next(c for c in checks if c["id"] == "risk_table")["status"] == "review"


def test_pdf_multiple_sections_keep_page_table_association():
    import pymupdf

    with pymupdf.open(stream=grouped_risk_pdf_bytes(), filetype="pdf") as pdf:
        pdf[0].insert_text(
            (25, 30), "Area/Activity: Computer software work", fontsize=9
        )
        pdf[3].insert_text(
            (25, 30), "Area/Activity: Physical test procedure", fontsize=9
        )
        document = extract_document(pdf.tobytes(), "synthetic.pdf")
    _, context = check_documents([document], STUDENT)
    sections = context["risk_sections"]
    assert [len(s["risk_rows"]) for s in sections] == [2, 4]
    assert all(not s["association_uncertain"] for s in sections)


@pytest.mark.parametrize(
    ("yes_bold", "no_bold", "expected"),
    [
        (False, True, "no"),
        (True, False, "yes"),
        (True, True, "ambiguous"),
        (False, False, None),
    ],
)
def test_word_primary_bold_contrast(yes_bold, no_bold, expected):
    doc = Document()
    p = doc.add_paragraph("Manual Handling: ")
    p.add_run("Y").bold = yes_bold
    p.add_run("/")
    p.add_run("N").bold = no_bold
    p.add_run(" Please list reference No:")
    extracted = extract(doc)
    assert highlighted_yes_no(extracted["paragraphs"][0]) == expected


def test_reference_field_bold_does_not_select_primary_options():
    doc = Document()
    p = doc.add_paragraph("COSHH: Y/N Please list reference No: ")
    p.add_run("N").bold = True
    assert highlighted_yes_no(extract(doc)["paragraphs"][0]) is None


def test_inherited_bold_does_not_make_one_explicit_option_a_selection():
    doc = Document()
    doc.styles["Normal"].font.bold = True
    p = doc.add_paragraph("COSHH: ")
    p.add_run("Y").bold = True
    p.add_run("/N")  # Also visibly bold through Normal; no contrast.
    assert highlighted_yes_no(extract(doc)["paragraphs"][0]) == "ambiguous"


def test_module_code_does_not_establish_room_by_shape_or_ai_assertion():
    doc = Document(io.BytesIO(document_bytes(location="XY9012")))
    doc.add_paragraph("Module code: XY9012")
    checks, context = run(doc)
    _, payload = ai_response(
        checks,
        context,
        "location",
        Judgement(
            status="complete",
            explanation="The code identifies a room.",
            quotes=["XY9012"],
        ),
    )
    assert payload["module_code_context"] == ["Module code: XY9012"]
    assert checks["location"]["status"] == "review"
    assert "course/module code" in checks["location"]["message"]


@pytest.mark.parametrize(
    ("yes_font", "no_font", "answer"),
    [("hebo", "helv", "yes"), ("helv", "hebo", "no"), ("hebo", "hebo", "ambiguous")],
)
def test_pdf_primary_bold_contrast(yes_font, no_font, answer):
    import pymupdf

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((30, 50), "COSHH: ", fontsize=10)
        page.insert_text((80, 50), "Y", fontname=yes_font, fontsize=10)
        page.insert_text((87, 50), "/", fontsize=10)
        page.insert_text((91, 50), "N", fontname=no_font, fontsize=10)
        document = extract_document(pdf.tobytes(), "synthetic.pdf")
    assert highlighted_yes_no(document["paragraphs"][0]) == answer


@pytest.mark.parametrize("delimiter", ["?", ":"])
def test_equivalent_administrative_questions(delimiter):
    doc = Document(io.BytesIO(document_bytes()))
    for p in doc.paragraphs:
        if "Generic to the University" in p.text:
            p.text = f"May this be shared as a generic assessment{delimiter} No"
        elif "related risk assessment that may require" in p.text:
            p.text = f"Does a related risk assessment need updating{delimiter} Yes"
    checks, _ = run(doc)
    assert checks["admin"]["status"] == "complete"


def test_duplicated_admin_question_does_not_supply_missing_other_question():
    doc = Document(io.BytesIO(document_bytes()))
    for p in doc.paragraphs:
        if "related risk assessment that may require" in p.text:
            p.text = "May this be shared as a generic assessment? No"
    checks, _ = run(doc)
    assert checks["admin"]["status"] == "review"


@pytest.mark.parametrize("answer", ["N", "Yes", "No - no physical handling"])
def test_reference_answer_is_interpretable_but_requires_placement_judgement(answer):
    doc = Document(
        io.BytesIO(document_bytes(specialist=f"Y/N Please list reference No: {answer}"))
    )
    checks, _ = run(doc)
    check = checks["specialists"]
    assert check["status"] == "moderator"
    assert "Interpretable" in check["message"]
    assert "No reliable" not in check["message"]
    if answer == "Yes":
        assert "Supervisor to locate" in check["message"]


def test_accepting_misplaced_yes_preserves_supervisor_followup_in_feedback():
    checks, _ = run(
        Document(
            io.BytesIO(document_bytes(specialist="Y/N Please list reference No: Yes"))
        )
    )
    check = checks["specialists"]
    check["decision"] = "complete"
    assert effective_status(check) == "supervisor"
    entries = feedback_items({"checks": [check]})
    assert len(entries) == 1
    assert entries[0]["audience"] == "supervisor"
    assert "COSHH" in entries[0]["text"]
    assert not entries[0]["correction_required"]


def test_legacy_feedback_signature_is_preserved_until_followup_actually_changes():
    item = {
        "checks": [
            {
                "id": "specialists",
                "status": "supervisor",
                "source": "Rule",
                "message": "Supporting assessment follow-up.",
                "evidence": [],
                "decision": "",
            }
        ]
    }
    legacy_signature = (
        "79960702d08d5ca3f442277106275f529570a3dda99b680380a30316559ba86b"
    )
    assert feedback_signature(item) == legacy_signature
    item["checks"][0]["supporting_assessments"] = ["COSHH"]
    assert feedback_signature(item) != legacy_signature


@pytest.mark.parametrize("answer", ["No - only simulation", "No. Only simulation"])
def test_qualified_no_is_interpretable_rather_than_unreadable(answer):
    checks, _ = run(Document(io.BytesIO(document_bytes(specialist=answer))))
    check = checks["specialists"]
    assert check["status"] == "moderator"
    assert "interpretable Yes/No" in check["message"]
    assert "No reliable" not in check["message"]


def test_hazard_heading_does_not_answer_missing_specialist_questionnaire():
    doc = Document(io.BytesIO(document_bytes()))
    for p in list(doc.paragraphs):
        if p.text.startswith("COSHH:"):
            p._p.getparent().remove(p._p)
    doc.tables[0].cell(1, 2).text = "COSHH: chemical exposure"
    checks, _ = run(doc)
    assert checks["specialists"]["status"] == "moderator"
    assert "coverage could not be established" in checks["specialists"]["message"]


@pytest.mark.parametrize(
    ("key", "concern", "hazard", "expected"),
    [
        (
            "hs_relevance",
            "mixed_hs",
            "Stress and fatigue; project milestones delayed",
            "moderator",
        ),
        ("hs_relevance", "mixed_hs", "Loss of project data", "issue"),
        ("entry_quality", "name_variation", "Eye strain", "review"),
        ("entry_quality", "lab_code", "Eye strain", "review"),
    ],
)
def test_semantic_concerns_keep_judgement_and_protected_rule_flags(
    key, concern, hazard, expected
):
    doc = Document(io.BytesIO(document_bytes(hazard=hazard)))
    checks, context = run(doc)
    ai_response(
        checks,
        context,
        key,
        Judgement(
            status="issue",
            concern=concern,
            explanation="Compare the quoted entries in the original.",
            quotes=[hazard],
        ),
    )
    assert checks[key]["status"] == expected


def test_retained_example_comments_cannot_duplicate_entry_quality():
    checks, context = run(Document(io.BytesIO(document_bytes())))
    metadata, _ = ai_response(
        checks,
        context,
        "entry_quality",
        Judgement(
            status="issue",
            explanation="A retained example row needs removal.",
            quotes=["Synthetic project"],
        ),
    )
    assert checks["entry_quality"]["status"] == "review"
    assert metadata["entry_quality_pending"]


def test_facilities_specificity_is_not_a_second_student_correction():
    checks, context = run(Document(io.BytesIO(document_bytes())))
    ai_response(
        checks,
        context,
        "facilities",
        Judgement(
            status="issue",
            concern="location_specificity",
            explanation="The workspace needs a more specific name.",
            quotes=[
                "ELC 004",
                "Computer work",
                "This project uses published data and a university computer in ELC 004.",
            ],
        ),
    )
    assert checks["facilities"]["status"] == "skipped"


@pytest.mark.parametrize("uncertain", [False, True])
def test_missing_ethics_form_has_one_owner_and_skipped_dependencies(uncertain):
    doc = Document(io.BytesIO(document_bytes()))
    remove = False
    for node in list(doc.element.body):
        remove |= "Student Project Ethics Approval Form" in "".join(node.itertext())
        if remove and not node.tag.endswith("sectPr"):
            doc.element.body.remove(node)
    extracted = extract(doc)
    if uncertain:
        extracted["kind"] = "pdf"
    checks, _ = check_documents([extracted], STUDENT)
    checks = {c["id"]: c for c in checks}
    assert checks["ethics_details"]["status"] == ("review" if uncertain else "issue")
    assert checks["low_risk"]["status"] == checks["narrative"]["status"] == "skipped"
    if not uncertain:
        assert "Upload the completed ethics form" in fallback_wording(
            checks["ethics_details"], "issue"
        )


def test_unrecognised_ethics_template_is_not_claimed_absent():
    doc = Document(io.BytesIO(document_bytes()))
    remove = False
    for node in list(doc.element.body):
        remove |= "Student Project Ethics Approval Form" in "".join(node.itertext())
        if remove and not node.tag.endswith("sectPr"):
            doc.element.body.remove(node)
    doc.add_paragraph("Ethics review questionnaire (alternative template)")
    checks, _ = run(doc)
    assert checks["ethics_details"]["status"] == "review"
    assert not checks["ethics_details"]["missing_form"]


@pytest.mark.parametrize("entry", ["L1–3", "5 (5)", "2x1 (L)"])
def test_technical_rating_defect_is_reported_without_repair_and_can_be_waived(entry):
    doc = Document(io.BytesIO(document_bytes()))
    doc.tables[0].cell(1, 8).text = entry
    checks, _ = run(doc)
    rating = checks["ratings"]
    assert rating["status"] == "review"
    assert entry in rating["technical_defects"][0]
    assert "do not silently repair" in rating["message"]
    original = copy.deepcopy(rating)
    rating["decision"] = "complete"
    assert effective_status(rating) == "complete"
    assert rating["status"] == original["status"]
    assert rating["technical_defects"] == original["technical_defects"]


@pytest.mark.parametrize(
    ("relative", "expected"), [("paragraph", "complete"), ("page", "review")]
)
def test_floating_title_placement_is_verified_or_manual(relative, expected):
    doc = Document(io.BytesIO(document_bytes()))
    p = next(
        p
        for p in doc.paragraphs
        if p.text.startswith("Student Name: Synthetic Student    Job Title:")
    )
    p.text = "Student Name: Synthetic Student    Job Title:"
    xml = f'''<w:r {nsdecls("w")} xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"><w:drawing><wp:anchor><wp:positionH relativeFrom="character"><wp:posOffset>0</wp:posOffset></wp:positionH><wp:positionV relativeFrom="{relative}"><wp:posOffset>0</wp:posOffset></wp:positionV><w:txbxContent><w:p><w:r><w:t>Student</w:t></w:r></w:p></w:txbxContent></wp:anchor></w:drawing></w:r>'''
    p._p.append(parse_xml(xml))
    checks, context = run(doc)
    assert checks["student_ra"]["status"] == expected
    if relative == "paragraph":
        assert any(p.get("textbox_association") for p in context["paragraphs"])
    else:
        assert "Floating textbox" in checks["student_ra"]["message"]


@pytest.mark.parametrize("checked", [True, False])
def test_pdf_vector_risk_checkbox_is_not_assumed_from_guidance(checked):
    import pymupdf

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.draw_rect((40, 40, 50, 50))
        page.insert_text((58, 49), "Low Risk", fontsize=10)
        if checked:
            page.draw_line((42, 45), (45, 48))
            page.draw_line((45, 48), (48, 42))
        extracted = extract_document(pdf.tobytes(), "synthetic.pdf")
    low = next(p for p in extracted["paragraphs"] if "Low Risk" in p["text"])
    assert low["states"] == [checked]


def test_pdf_checkbox_ambiguous_annotation_stays_unreadable():
    import pymupdf

    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.draw_rect((40, 40, 50, 50))
        page.insert_text((58, 49), "Low Risk", fontsize=10)
        page.add_ink_annot([[(42, 44), (46, 48)]])
        document = extract_document(pdf.tobytes(), "synthetic.pdf")
    assert document["paragraphs"][0]["states"] == [None]


def test_mixed_hs_review_retains_unconfirmed_rule_flag_without_declaring_error():
    hazard = "Stress from software problems and missed deadlines"
    checks, context = run(Document(io.BytesIO(document_bytes(hazard=hazard))))
    ai_response(
        checks,
        context,
        "hs_relevance",
        Judgement(
            status="review",
            concern="mixed_hs",
            explanation="Health effects are present; moderator to judge the project-only wording.",
            quotes=[hazard],
        ),
    )
    assert checks["hs_relevance"]["status"] == "moderator"
    assert checks["hs_relevance"]["potential_non_hs_flag"].startswith("Potential")


def test_adjudication_preserves_originals_and_reports_positive_findings(
    workflow_review, client
):
    review = workflow_review
    for item in review["submissions"]:
        payload = {f"audit_{c['id']}": "complete" for c in item["checks"]}
        payload["other_corrections"] = (
            "Remove unused rows; not recorded as missing ratings."
        )
        assert (
            client.post(
                reverse("moderation:validation_audit", args=[review["id"], item["id"]]),
                payload,
            ).status_code
            == 302
        )
    before = store.load(review["id"])
    item = before["submissions"][0]
    url = reverse(
        "moderation:adjudicate_audit", args=[review["id"], item["id"], "readable"]
    )
    payload = {
        "basis": comparison_token(before),
        "classification": "human_error",
        "reason": "The original confirms the defect missed in the audit.",
    }
    assert client.post(url, payload).status_code == 302
    after = store.load(review["id"])
    assert after["submissions"][0]["validation_audits"] == item["validation_audits"]
    assert after["submissions"][0]["checks"] == item["checks"]
    page = client.get(reverse("moderation:validation_comparison", args=[review["id"]]))
    stats = next(s for s in page.context["check_statistics"] if s["id"] == "readable")
    assert stats["adjudicated"] == 1
    assert (
        next(
            s
            for s in stats["adjudication_counts"]
            if s["classification"] == "human_error"
        )["count"]
        == 1
    )
    assert b"Other corrections outside" in page.content
    assert client.post(url, payload).status_code == 409  # Stale evidence token.
    assert (
        client.post(
            url, {**payload, "basis": comparison_token(after), "reason": ""}
        ).status_code
        == 400
    )


def test_existing_private_decision_log_is_read_only_and_not_reclassified(
    workflow_review, client
):
    review = workflow_review
    for item in review["submissions"]:
        payload = {f"audit_{c['id']}": "complete" for c in item["checks"]}
        client.post(
            reverse("moderation:validation_audit", args=[review["id"], item["id"]]),
            payload,
        )
    path = store.review_dir(review["id"]) / "evaluation-decisions.json"
    log = {
        "review_id": review["id"],
        "adjudications": [
            {
                "student_number": review["submissions"][0]["number"],
                "check": "readable",
                "classification": "Human error caught by tool",
                "reason": "Earlier staff decision; original audit preserved.",
                "agreed_date": "2026-11-17",
            }
        ],
    }
    path.write_text(json.dumps(log), encoding="utf-8")
    before_log = path.read_bytes()
    before_review = store.load(review["id"])
    page = client.get(reverse("moderation:validation_comparison", args=[review["id"]]))
    stat = next(s for s in page.context["check_statistics"] if s["id"] == "readable")
    assert stat["historical_adjudicated"] == 1
    assert stat["adjudicated"] == 0
    assert stat["historical_counts"] == [
        {"label": "Human error caught by tool", "count": 1}
    ]
    assert b"Earlier staff decision" in page.content
    assert path.read_bytes() == before_log
    assert store.load(review["id"]) == before_review
    log["adjudications"].append(
        {
            "student_number": review["submissions"][1]["number"],
            "check": "readable",
            "classification": "Unresolved",
        }
    )
    path.write_text(json.dumps(log), encoding="utf-8")
    assert len(historical_adjudications(review)) == 2  # Legacy reasons may be absent.
    path.write_text(json.dumps({**log, "review_id": "wrong batch"}), encoding="utf-8")
    with pytest.raises(ValueError):
        historical_adjudications(review)
