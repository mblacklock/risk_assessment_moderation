import copy
import uuid
from unittest.mock import patch

import pytest
from django.urls import reverse

from moderation import jobs, store
from moderation.feedback import feedback_items, feedback_readiness, feedback_signature
from moderation.tests.test_review import archive_bytes
from moderation.workflow import finding_fingerprint


@pytest.fixture
def feedback_review(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        r = jobs.create_review(archive_bytes(), "Synthetic feedback", False)
    jobs.run(r["id"])
    r = store.load(r["id"])
    for c in r["submissions"][0]["checks"]:
        c.update(
            status="complete",
            source="Rule",
            message="Present",
            evidence=[],
            decision="",
            note="INTERNAL NOTE DO NOT COPY",
        )
    store.save(r)
    return r


def finding(r, key):
    return next(c for c in r["submissions"][0]["checks"] if c["id"] == key)


def acknowledge(check, decision=""):
    check.update(
        decision=decision,
        reviewed_at="2026-11-16",
        decided_at="2026-11-16",
        reviewed_fingerprint=finding_fingerprint(check),
    )


def url(r):
    return reverse("moderation:feedback", args=[r["id"], r["submissions"][0]["id"]])


def generate(client, r, **extra):
    return client.post(
        url(r),
        {
            "signature": feedback_signature(store.load(r["id"])["submissions"][0]),
            **extra,
        },
    )


def test_no_feedback_or_draft_before_flagged_reviews_complete(feedback_review, client):
    r = feedback_review
    finding(r, "ratings").update(status="issue", message="Row 1: enter Final Result.")
    store.save(r)
    page = client.get(
        reverse("moderation:submission", args=[r["id"], r["submissions"][0]["id"]])
    )
    assert not page.context["feedback_ready"]
    assert b"disabled>Generate eLP feedback" in page.content
    assert generate(client, r).status_code == 409
    assert client.get(url(r)).status_code == 409
    assert "elp_feedback" not in store.load(r["id"])["submissions"][0]


def test_saved_but_unresolved_moderation_still_blocks_generation(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "facilities")
    c.update(status="review", message="Manual judgement required")
    acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 409
    assert "unresolved" in feedback_readiness(r, r["submissions"][0])[1]


def test_pass_feedback_after_completed_review_does_not_copy_internal_notes(
    feedback_review, client
):
    r = feedback_review
    with patch.object(jobs, "apply_ai") as ai:
        response = generate(client, r)
        ai.assert_not_called()
    assert response.status_code == 302
    record = store.load(r["id"])["submissions"][0]["elp_feedback"]
    assert record["text"].startswith("Result: Pass\n")
    assert "INTERNAL NOTE" not in record["text"]
    page = client.get(response.url)
    assert (
        b"Copy eLP feedback" in page.content
        and b"Ready to copy into eLP" in page.content
    )


def test_confirmed_corrections_are_specific_and_duplicate_rating_findings_merge(
    feedback_review, client
):
    r = feedback_review
    a = finding(r, "ratings")
    a.update(
        status="issue",
        message="Rating entry counts do not match. Row 1: 2 initial and 3 final entries. Correct or clarify which ratings belong together.",
    )
    b = finding(r, "risk_reduction")
    b.update(
        status="issue",
        message="Rating entry counts do not match. Row 1: 2 initial and 3 final entries. Correct or clarify the entries before comparing these rows.",
    )
    acknowledge(a)
    acknowledge(b)
    store.save(r)
    assert len(feedback_items(r["submissions"][0])) == 1
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert text.startswith("Result: Fail — correction required")
    assert text.count("Rating entry counts do not match") == 1
    assert "Row 1" in text and "2 initial and 3 final" in text
    assert "every correction" in text


def test_supervisor_followup_pass_is_separate_from_student_corrections(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "specialists")
    c.update(
        status="supervisor",
        message="Supervisor to locate and review supporting assessments: COSHH. A Yes answer identifies follow-up, not a student completion error.",
    )
    acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert text.startswith("Result: Pass — supervisor follow-up")
    assert "Supervisor follow-up" in text and "COSHH" in text
    assert "Student corrections" not in text


def test_override_without_public_wording_never_exposes_tool_failure_or_internal_note(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "entry_quality")
    c.update(
        status="review",
        message="AI evidence could not be verified. Inspect the original.",
    )
    acknowledge(c, "issue")
    store.save(r)
    response = generate(client, r)
    assert response.status_code == 200 and response.context["wording_needed"]
    assert response.context["feedback"] is None
    assert response.context["form"]["entry_quality"].value() == ""
    assert b"INTERNAL NOTE" not in response.content
    assert "elp_feedback" not in store.load(r["id"])["submissions"][0]
    signature = feedback_signature(store.load(r["id"])["submissions"][0])
    assert (
        client.post(
            url(r), {"signature": signature, "action": "confirm", "entry_quality": ""}
        ).status_code
        == 400
    )
    response = client.post(
        url(r),
        {
            "signature": signature,
            "action": "confirm",
            "entry_quality": "Use Student as your job title rather than the project title.",
        },
    )
    assert response.status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert "Use Student" in text
    assert "AI evidence" not in text and "INTERNAL NOTE" not in text


def test_overridden_complete_finding_is_not_in_student_corrections(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "location")
    c.update(status="issue", message="Workspace missing")
    acknowledge(c, "complete")
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert text.startswith("Result: Pass") and "Workspace missing" not in text


def test_stale_feedback_hidden_and_copy_verification_fails_when_findings_change(
    feedback_review, client
):
    r = feedback_review
    assert generate(client, r).status_code == 302
    stored = store.load(r["id"])
    signature = stored["submissions"][0]["elp_feedback"]["signature"]
    version = stored["submissions"][0]["elp_feedback"]["id"]
    assert client.get(url(r), {"verify": signature, "version": version}).json()[
        "current"
    ]
    finding(stored, "ratings").update(status="issue", message="New missing score")
    store.save(stored)
    assert not client.get(url(r), {"verify": signature, "version": version}).json()[
        "current"
    ]
    assert client.get(url(r)).status_code == 409
    assert client.post(url(r), {"signature": signature}).status_code == 409
    assert (
        store.load(r["id"])["submissions"][0]["elp_feedback"]["signature"] == signature
    )


def test_processing_pending_ai_and_excluded_attempts_block_feedback(feedback_review):
    r = feedback_review
    item = r["submissions"][0]
    r["state"] = "running"
    assert not feedback_readiness(r, item)[0]
    r["state"] = "done"
    r["use_ai"] = True
    item["ai"] = {"state": "pending"}
    assert not feedback_readiness(r, item)[0]
    r["use_ai"] = False
    item["submitted"] = "2026-11-15T12:00:00Z"
    later = copy.deepcopy(item)
    later.update(id=str(uuid.uuid4()), submitted="2026-11-16T12:00:00Z")
    r["submissions"].append(later)
    r["latest_only"] = True
    assert not feedback_readiness(r, item)[0]


def test_required_supervisor_omission_stays_fail_but_is_addressed_to_supervisor(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "supervisor_ethics")
    c.update(status="issue", message="Missing: signature, date.")
    acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert (
        "Result: Fail" in text
        and "Supervisor completion required before resubmission" in text
    )
    assert "Add the missing signature and date" in text


def test_edited_wording_invalidates_copy_from_older_generated_page(
    feedback_review, client
):
    r = feedback_review
    assert generate(client, r).status_code == 302
    first = store.load(r["id"])["submissions"][0]["elp_feedback"]
    assert generate(client, r).status_code == 302
    second = store.load(r["id"])["submissions"][0]["elp_feedback"]
    assert first["id"] != second["id"]
    assert not client.get(
        url(r), {"verify": first["signature"], "version": first["id"]}
    ).json()["current"]
    assert client.get(
        url(r), {"verify": second["signature"], "version": second["id"]}
    ).json()["current"]
    assert len(store.load(r["id"])["submissions"][0]["feedback_history"]) == 2


def test_feedback_groups_scores_names_questions_and_details_supervisor_actions(
    feedback_review, client
):
    r = feedback_review
    messages = {
        "ratings": "Row 1: enter a numeric value for Final Result (post-control score). Row 2: enter a numeric value for Final Result (post-control score). Row 3: enter a numeric value for Final Result (post-control score).",
        "admin": "Administrative question(s) 1, 2 unanswered. Select Yes or No.",
        "specialists": "Unanswered specialist questions: Manual Handling, COSHH, PUWER. Select Yes or No.",
        "physical": "Risk assessment completed must be Yes only.",
        "supervisor_ra": "Missing: name, job title, signature, date.",
        "supervisor_ethics": "Missing: signature, date.",
        "tutor": "Tutor checklist is incomplete or unreadable.",
        "supervisor_statement": "Supervisor confirmation must be selected.",
    }
    for key, message in messages.items():
        c = finding(r, key)
        c.update(status="issue", message=message)
        acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert "in risk rows 1, 2 and 3" in text
    assert text.count("Enter the post-control") == 1
    assert "Generic to the University (" in text
    assert "related risk assessment need review or updating" in text
    assert '"Physical risk assessment form completed?"' in text
    assert "Ethics form complete" in text
    assert "Ethical concerns acknowledged" in text
    assert "Research tool(s) checked" in text
    assert text.count("Supervisor sign-off:") == 1
    assert "Correction required —" not in text
    assert "incomplete or unreadable" not in text
    assert text.count("Leaving Y/N unchanged") == 1
    assert text.count("resubmit") == 1


def test_only_unanswered_administrative_question_is_named(feedback_review, client):
    r = feedback_review
    c = finding(r, "admin")
    c.update(status="issue", message="Administrative question(s) 2 unanswered.")
    acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert "related risk assessment" in text
    assert "Generic to the University" not in text


def test_format_upgrade_keeps_manual_wording_and_history(feedback_review, client):
    from moderation.feedback import (
        INTERNAL,
        SUPERVISOR_OWNED,
        clean_message,
        feedback_signature,
    )
    from moderation.feedback_legacy import legacy_feedback_items

    r = feedback_review
    c = finding(r, "ratings")
    c.update(
        status="issue",
        message="Row 1: enter a numeric value for Final Result (post-control score).",
    )
    acknowledge(c)
    item = r["submissions"][0]
    defaults = {
        e["key"]: e["text"]
        for e in legacy_feedback_items(item, clean_message, INTERNAL, SUPERVISOR_OWNED)
    }
    defaults["ratings"] = (
        "Please add the assessed post-control score for the screen-work entry."
    )
    old = {
        "id": "old-feedback",
        "format_version": 1,
        "signature": feedback_signature(item),
        "wording": defaults,
        "text": "Previous feedback",
        "generated_at": "2026-11-16",
    }
    item.update(elp_feedback=old, feedback_history=[old])
    store.save(r)
    response = generate(client, r)
    assert response.status_code == 302
    updated = store.load(r["id"])["submissions"][0]
    assert updated["elp_feedback"]["format_version"] == 2
    assert "screen-work entry" in updated["elp_feedback"]["text"]
    assert updated["feedback_history"][0] == old
    assert len(updated["feedback_history"]) == 2


def test_format_upgrade_rewrites_old_automatic_repetition(feedback_review, client):
    from moderation.feedback import (
        INTERNAL,
        SUPERVISOR_OWNED,
        clean_message,
        feedback_signature,
    )
    from moderation.feedback_legacy import legacy_feedback_items

    r = feedback_review
    c = finding(r, "ratings")
    c.update(
        status="issue",
        message="Row 1: enter a numeric value for Final Result (post-control score). Row 2: enter a numeric value for Final Result (post-control score).",
    )
    acknowledge(c)
    item = r["submissions"][0]
    old = {
        "id": "old-auto",
        "format_version": 1,
        "signature": feedback_signature(item),
        "wording": {
            e["key"]: e["text"]
            for e in legacy_feedback_items(
                item, clean_message, INTERNAL, SUPERVISOR_OWNED
            )
        },
        "text": "Previous automatic feedback",
    }
    item.update(elp_feedback=old, feedback_history=[old])
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert "in risk rows 1 and 2" in text and "Row 2: enter" not in text


def test_condensed_rating_feedback_keeps_separate_count_mismatch_and_unclear_entries(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "ratings")
    c.update(
        status="issue",
        message="Row 1: enter a numeric value for Final Result (post-control score). Complete the missing rating fields. Rating entry counts do not match. Row 2: 2 initial and 3 final entries. Correct or clarify which ratings belong together. Multiple or unclear rating entries could not be read reliably in rows: 3. Check the original and the pairing manually.",
    )
    acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert "risk row 1" in text and "Row 2: 2 initial and 3 final entries" in text
    assert "In risk row 3" in text


def test_condensed_specialist_omissions_keep_supervisor_followup(
    feedback_review, client
):
    r = feedback_review
    c = finding(r, "specialists")
    c.update(
        status="issue",
        message="Supervisor to locate and review supporting assessments: COSHH. A Yes answer identifies follow-up, not a student completion error. Unanswered specialist questions: Manual Handling. Select Yes or No.",
    )
    acknowledge(c)
    store.save(r)
    assert generate(client, r).status_code == 302
    text = store.load(r["id"])["submissions"][0]["elp_feedback"]["text"]
    assert "Answer each category: Manual Handling" in text
    assert "Supervisor follow-up" in text and "for COSHH" in text


def test_standard_excel_export_appends_current_feedback_with_line_breaks(
    feedback_review, client
):
    import io

    from openpyxl import load_workbook

    r = feedback_review
    assert generate(client, r).status_code == 302
    before = store.load(r["id"])
    expected = before["submissions"][0]["elp_feedback"]["text"]
    response = client.get(reverse("moderation:export", args=[r["id"], "xlsx"]))
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["Snapshot"]
    cell = sheet.cell(2, sheet.max_column)
    assert sheet.cell(1, sheet.max_column).value == "eLP feedback"
    assert cell.value == expected and "\n" in cell.value
    assert cell.alignment.wrap_text and cell.alignment.vertical == "top"
    assert sheet.column_dimensions[cell.column_letter].width == 90
    assert "Findings and decisions" in workbook.sheetnames
    assert store.load(r["id"]) == before
    finding(before, "ratings").update(status="issue", message="New score omission")
    store.save(before)
    response = client.get(reverse("moderation:export", args=[r["id"], "xlsx"]))
    sheet = load_workbook(io.BytesIO(response.content))["Snapshot"]
    assert sheet.cell(2, sheet.max_column).value is None


def test_excel_feedback_limit_does_not_silently_truncate_content(
    feedback_review, client
):
    r = feedback_review
    generate(client, r)
    stored = store.load(r["id"])
    stored["submissions"][0]["elp_feedback"]["text"] = "x" * 32768
    store.save(stored)
    response = client.get(reverse("moderation:export", args=[r["id"], "xlsx"]))
    assert response.status_code == 400
    assert b"single-cell text limit" in response.content


def test_excel_feedback_is_literal_text_even_if_it_starts_like_a_formula(
    feedback_review, client
):
    import io

    from openpyxl import load_workbook

    r = feedback_review
    generate(client, r)
    stored = store.load(r["id"])
    text = "=1+1\nPublic feedback wording"
    stored["submissions"][0]["elp_feedback"]["text"] = text
    store.save(stored)
    response = client.get(reverse("moderation:export", args=[r["id"], "xlsx"]))
    sheet = load_workbook(io.BytesIO(response.content))["Snapshot"]
    cell = sheet.cell(2, sheet.max_column)
    assert cell.value == text and cell.data_type == "s"
