import io
from unittest.mock import patch

import pytest
from django.urls import reverse
from docx import Document
from docx.oxml import parse_xml

from moderation import jobs, store
from moderation.checks import check_documents
from moderation.documents import extract_document
from moderation.tests.test_review import STUDENT, archive_bytes, document_bytes
from moderation.word_drawings import word_drawing_png


@pytest.fixture
def drawing_review(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        review = jobs.create_review(archive_bytes(), "Synthetic drawing review", False)
    jobs.run(review["id"])
    return store.load(review["id"])


def drawn_document(placement="preceding", simple=False):
    doc = Document(io.BytesIO(document_bytes(missing_signature=True)))
    label = next(p for p in doc.paragraphs if p.text.startswith("Signature:"))
    target = label if placement == "inline" else label.insert_paragraph_before("")
    vertical = "page" if placement == "page" else "paragraph"
    commands = (
        '<a:lnTo><a:pt x="100" y="100"/></a:lnTo>'
        if simple
        else (
            '<a:cubicBezTo><a:pt x="10" y="80"/><a:pt x="70" y="10"/><a:pt x="90" y="60"/></a:cubicBezTo>'
            * 3
        )
    )
    xml = f'''<w:drawing xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><wp:anchor><wp:positionH relativeFrom="column"><wp:posOffset>800000</wp:posOffset></wp:positionH><wp:positionV relativeFrom="{vertical}"><wp:posOffset>60000</wp:posOffset></wp:positionV><wp:extent cx="900000" cy="400000"/><a:graphic><a:graphicData><a:custGeom><a:pathLst><a:path w="100" h="100"><a:moveTo><a:pt x="0" y="40"/></a:moveTo>{commands}</a:path></a:pathLst></a:custGeom></a:graphicData></a:graphic></wp:anchor></w:drawing>'''
    target.add_run()._r.append(parse_xml(xml))
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


@pytest.mark.parametrize("placement", ["inline", "preceding", "page"])
def test_freehand_signature_presence_and_ambiguous_page_anchor(placement):
    doc = extract_document(drawn_document(placement), "synthetic.docx")
    found, _ = check_documents([doc], STUDENT)
    check = next(c for c in found if c["id"] == "student_ra")
    assert check["status"] == ("review" if placement == "page" else "complete")
    if placement != "page":
        assert any(
            "word-drawing-0.png" in e.get("images", []) for e in check["evidence"]
        )
        assert word_drawing_png(drawn_document(placement), 0).startswith(b"\x89PNG")


def test_plain_drawing_does_not_establish_signature_presence():
    doc = extract_document(drawn_document(simple=True), "synthetic.docx")
    found, _ = check_documents([doc], STUDENT)
    check = next(c for c in found if c["id"] == "student_ra")
    assert check["status"] == "review"
    with pytest.raises(ValueError):
        word_drawing_png(drawn_document(simple=True), 0)


def test_saved_drawing_refresh_preserves_audit_and_serves_preview(
    drawing_review, client
):
    review = drawing_review
    item = review["submissions"][0]
    file = item["files"][0]
    data = drawn_document()
    source = store.review_dir(review["id"]) / file["id"]
    source.write_bytes(data)
    document = extract_document(data, file["name"])
    document.pop("drawing_reader_version")
    for p in document["paragraphs"]:
        p["images"] = [i for i in p["images"] if not i.startswith("word-drawing-")]
    item["documents"] = [document]
    old = next(c for c in item["checks"] if c["id"] == "student_ra")
    old.update(
        status="issue",
        message="Missing: signature.",
        decision="review",
        note="Staff note",
        history=[{"note": "Previous decision"}],
    )
    store.save(review)
    with patch("moderation.jobs.apply_ai") as ai:
        updated = jobs.snapshot(review["id"])
        ai.assert_not_called()
    check = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "student_ra"
    )
    assert check["status"] == "complete"
    assert check["note"] == old["note"] and check["history"] == old["history"]
    assert check["superseded_pdf_finding"] == old
    assert jobs.snapshot(review["id"]) == updated
    assert source.read_bytes() == data
    response = client.get(
        reverse("moderation:image", args=[review["id"], item["id"], 0, 0])
    )
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert response["Cache-Control"] == "private, no-store"
