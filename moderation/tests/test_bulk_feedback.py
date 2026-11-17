import copy
import io
import uuid
from concurrent.futures import Future
from unittest.mock import patch

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from moderation import jobs, store
from moderation.feedback import bulk_feedback_state, new_feedback_record
from moderation.tests.test_review import archive_bytes
from moderation.workflow import finding_fingerprint


@pytest.fixture
def bulk_review(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        r = jobs.create_review(archive_bytes(), "Synthetic bulk feedback", False)
    jobs.run(r["id"])
    r = store.load(r["id"])
    base = r["submissions"][0]
    for c in base["checks"]:
        c.update(
            status="complete",
            source="Rule",
            message="Present",
            evidence=[],
            decision="",
            note="PRIVATE STAFF NOTE",
        )
    r["submissions"] = []
    for index, name in enumerate(
        (
            "Ready Pass",
            "Ready Fail",
            "Ready Supervisor",
            "Unreviewed",
            "Unresolved",
            "Needs Wording",
        )
    ):
        item = copy.deepcopy(base)
        item.update(id=str(uuid.uuid4()), name=name, number=f"w{12345678 + index}")
        r["submissions"].append(item)

    def change(index, key, status, message, decision="", reviewed=True):
        c = next(c for c in r["submissions"][index]["checks"] if c["id"] == key)
        c.update(status=status, message=message, decision=decision)
        if reviewed:
            c.update(
                reviewed_at="2026-11-16",
                decided_at="2026-11-16",
                reviewed_fingerprint=finding_fingerprint(c),
            )

    change(
        1, "ratings", "issue", "Row 1: enter a numeric post-control Final Result score."
    )
    change(
        2,
        "specialists",
        "supervisor",
        "Supervisor to locate and review supporting assessments: COSHH.",
    )
    change(3, "location", "issue", "Area/Activity is missing.", reviewed=False)
    change(4, "facilities", "review", "Manual judgement required.")
    change(
        5,
        "entry_quality",
        "review",
        "AI evidence could not be verified.",
        decision="issue",
    )
    store.save(r)
    return r


def bulk_url(r):
    return reverse("moderation:bulk_feedback", args=[r["id"]])


def test_bulk_generates_only_reviewed_and_worded_students_without_ai(
    bulk_review, client
):
    r = bulk_review
    with patch.object(jobs, "apply_ai") as ai:
        response = client.post(bulk_url(r), {"grid": "q=Unreviewed"})
        ai.assert_not_called()
    assert response.status_code == 302
    page = client.get(response.url)
    assert len(page.context["generated"]) == 3
    assert len(page.context["excluded"]) == 3
    assert page.context["waiting"] == []
    assert page.content.count(b"data-copy-feedback ") == 3
    assert b"PRIVATE STAFF NOTE" not in page.content
    stored = store.load(r["id"])
    assert all("elp_feedback" in s for s in stored["submissions"][:3])
    assert all("elp_feedback" not in s for s in stored["submissions"][3:])
    assert [s["checks"] for s in stored["submissions"]] == [
        s["checks"] for s in r["submissions"]
    ]


def test_combined_download_has_only_current_generated_feedback(bulk_review, client):
    r = bulk_review
    client.post(bulk_url(r))
    page = client.get(bulk_url(r))
    response = client.get(
        reverse("moderation:download_feedback", args=[r["id"]]),
        {"version": page.context["batch_version"]},
    )
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["Snapshot"]
    assert sheet.cell(1, sheet.max_column).value == "eLP feedback"
    rows = {row[1]: row for row in sheet.iter_rows(min_row=2, values_only=True)}
    assert len(rows) == 6
    for name in ("Ready Pass", "Ready Fail", "Ready Supervisor"):
        assert rows[name][-1].startswith("Result:")
        assert "PRIVATE STAFF NOTE" not in rows[name][-1]
    assert all(
        rows[name][-1] is None for name in ("Unreviewed", "Unresolved", "Needs Wording")
    )
    assert "Findings and decisions" in workbook.sheetnames
    assert response["Content-Disposition"].endswith('.xlsx"')


def test_repeating_bulk_generation_preserves_edited_feedback_and_history(
    bulk_review, client
):
    r = bulk_review
    item = r["submissions"][1]
    edited = new_feedback_record(
        item,
        {
            "ratings": "Enter the final score in row 1 after assessing the stated controls."
        },
        store.now(),
    )
    item.update(elp_feedback=edited, feedback_history=[edited])
    store.save(r)
    client.post(bulk_url(r))
    before = store.load(r["id"])
    assert before["submissions"][1]["elp_feedback"] == edited
    client.post(bulk_url(r))
    assert store.load(r["id"]) == before


def test_latest_selection_excludes_earlier_attempt_from_bulk_and_download(
    bulk_review, client
):
    r = bulk_review
    old = r["submissions"][0]
    old["submitted"] = "2026-11-15T12:00:00Z"
    latest = copy.deepcopy(old)
    latest.update(id=str(uuid.uuid4()), submitted="2026-11-16T12:00:00Z")
    r["submissions"].append(latest)
    r["latest_only"] = True
    store.save(r)
    client.post(bulk_url(r))
    stored = store.load(r["id"])
    state = bulk_feedback_state(stored)
    assert old["id"] not in {row["submission"]["id"] for row in state["generated"]}
    assert latest["id"] in {row["submission"]["id"] for row in state["generated"]}
    assert any(item["id"] == old["id"] for item in state["earlier"])
    assert len(state["excluded"]) == 3
    response = client.get(
        reverse("moderation:download_feedback", args=[r["id"]]),
        {"version": state["batch_version"]},
    )
    sheet = load_workbook(io.BytesIO(response.content))["Snapshot"]
    assert "2026-11-15T12:00:00Z" not in [
        row[2] for row in sheet.iter_rows(min_row=2, values_only=True)
    ]


def test_changed_findings_block_old_download_and_hide_stale_feedback(
    bulk_review, client
):
    r = bulk_review
    client.post(bulk_url(r))
    previous = bulk_feedback_state(store.load(r["id"]))["batch_version"]
    latest = store.load(r["id"])
    latest["submissions"][0]["checks"][0].update(
        status="issue", message="New finding requiring review"
    )
    store.save(latest)
    response = client.get(
        reverse("moderation:download_feedback", args=[r["id"]]), {"version": previous}
    )
    assert response.status_code == 409
    page = client.get(bulk_url(r))
    assert len(page.context["generated"]) == 2
    assert latest["submissions"][0]["id"] not in {
        row["submission"]["id"] for row in page.context["generated"]
    }


def test_get_bulk_page_does_not_generate_feedback(bulk_review, client):
    r = bulk_review
    page = client.get(bulk_url(r))
    assert page.status_code == 200 and len(page.context["waiting"]) == 3
    assert page.context["generated"] == []
    assert all("elp_feedback" not in s for s in store.load(r["id"])["submissions"])
    assert (
        client.get(reverse("moderation:download_feedback", args=[r["id"]])).status_code
        == 409
    )


def test_bulk_cannot_generate_while_review_is_processing(bulk_review, client):
    r = bulk_review
    r["state"] = "running"
    store.save(r)
    with patch.dict(jobs.ACTIVE, {r["id"]: Future()}):
        assert client.post(bulk_url(r)).status_code == 409
    assert all("elp_feedback" not in s for s in store.load(r["id"])["submissions"])


def test_student_with_outstanding_ai_is_excluded_without_running_ai(
    bulk_review, client
):
    r = bulk_review
    r["use_ai"] = True
    r["submissions"][0]["ai"] = {"state": "pending"}
    store.save(r)
    with patch.object(jobs, "apply_ai") as ai:
        assert client.post(bulk_url(r)).status_code == 302
        ai.assert_not_called()
    stored = store.load(r["id"])
    assert "elp_feedback" not in stored["submissions"][0]
    state = bulk_feedback_state(stored)
    excluded = next(
        row
        for row in state["excluded"]
        if row["submission"]["id"] == r["submissions"][0]["id"]
    )
    assert "AI checks" in excluded["reason"]


def test_confirmed_area_and_risk_selection_overrides_use_known_requirements_in_bulk(
    bulk_review, client
):
    r = bulk_review
    item = r["submissions"][0]
    for key, message in (
        ("location", "The building name does not identify the workspace."),
        ("low_risk", "Confirm the ethics risk selection."),
    ):
        c = next(c for c in item["checks"] if c["id"] == key)
        c.update(
            status="review",
            message=message,
            decision="issue",
            note="PRIVATE STAFF NOTE",
            reviewed_at="2026-11-16",
            decided_at="2026-11-16",
        )
        c["reviewed_fingerprint"] = finding_fingerprint(c)
    store.save(r)
    assert client.post(bulk_url(r)).status_code == 302
    stored = store.load(r["id"])
    text = stored["submissions"][0]["elp_feedback"]["text"]
    assert "building name alone is not specific enough" in text
    assert "restore the Low Risk and Medium Risk selection boxes" in text
    assert "PRIVATE STAFF NOTE" not in text
    assert "Result: Fail" in text
