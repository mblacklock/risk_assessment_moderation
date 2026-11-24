import copy
import re
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from django.urls import reverse
from django.utils.html import escape

from moderation import jobs, store
from moderation.criteria import effective_status
from moderation.tests.test_review import archive_bytes
from moderation.workflow import finding_fingerprint, review_progress


@pytest.fixture
def workflow_review(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        review = jobs.create_review(archive_bytes(), "Synthetic workflow", False)
    jobs.run(review["id"])
    review = store.load(review["id"])
    for c in review["submissions"][0]["checks"]:
        c.update(
            status="complete",
            source="Rule",
            message="Synthetic finding",
            evidence=[],
            decision="",
            note="",
        )
    review["submissions"][0]["checks"][0]["status"] = "issue"
    review["submissions"][0]["checks"][1]["status"] = "review"
    other = copy.deepcopy(review["submissions"][0])
    other.update(
        id=str(uuid.uuid4()), name="Second synthetic student", number="w23456789"
    )
    for file in other["files"]:
        file["name"] = "second-synthetic.docx"
    review["submissions"].append(other)
    store.save(review)
    return review


def save(client, review, key="readable", **payload):
    return client.post(
        reverse(
            "moderation:decide",
            args=[review["id"], review["submissions"][0]["id"], key],
        ),
        {"decision": "", "note": "", **payload},
    )


def test_confirm_issue_returns_to_filtered_grid_and_marks_reviewed(
    workflow_review, client
):
    r = workflow_review
    response = save(
        client,
        r,
        grid="category=Submission+details&sort=number&direction=desc&needs_review=on",
    )
    destination = urlsplit(response.url)
    assert destination.path == reverse("moderation:review", args=[r["id"]])
    params = parse_qs(destination.query)
    assert params["sort"] == ["number"] and params["needs_review"] == ["on"]
    assert params["saved"] == [r["submissions"][0]["id"] + ":readable"]
    check = store.load(r["id"])["submissions"][0]["checks"][0]
    assert effective_status(check) == "issue"
    assert review_progress(check)["review_resolved"]
    assert check["history"][-1]["decision"] == ""
    page = client.get(response.url)
    assert page.context["reviewed_count"] == 1 and page.context["flagged_count"] == 4
    assert b"Reviewed" in page.content


def identity_block(response, variant="sidebar"):
    html = response.content.decode()
    match = re.search(
        rf'<div class="review-student-identity review-student-{variant}".*?</div>',
        html,
        re.S,
    )
    assert match, "The review panel must identify the current student."
    return match.group()


def test_review_panel_identity_tracks_navigation_between_students(
    workflow_review, client
):
    review = workflow_review
    first, second = review["submissions"]
    first_url = reverse("moderation:submission", args=[review["id"], first["id"]])
    # Render raw synthetic records; this UI test must not refresh checking results.
    with patch("moderation.views.get_review", side_effect=store.load):
        page = client.get(first_url)
        block = identity_block(page)
        assert escape(first["name"]) in block and first["number"] in block
        html = page.content.decode()
        assert (
            html.index('<aside class="source-panel">')
            < html.index(block)
            < html.index("Source documents")
        )
        assert "Save and open next" in html
        response = save(client, review, "identity", decision="complete", action="next")
        assert urlsplit(response.url).path == reverse(
            "moderation:submission", args=[review["id"], second["id"]]
        )
        next_page = client.get(response.url)
        for variant in ("sidebar", "mobile"):
            block = identity_block(next_page, variant)
            assert escape(second["name"]) in block and second["number"] in block
            assert escape(first["name"]) not in block and first["number"] not in block
        previous_page = client.get(first_url)
        assert escape(first["name"]) in identity_block(previous_page)
        assert second["number"] not in identity_block(previous_page)


def test_review_identity_escapes_long_names_in_both_responsive_headers(
    workflow_review, client
):
    review = workflow_review
    student = review["submissions"][0]
    student["name"] = (
        'A very long synthetic student name & <img src=x onerror="alert(1)">'
    )
    original = copy.deepcopy(review)
    with patch("moderation.views.get_review", return_value=review):
        page = client.get(
            reverse("moderation:submission", args=[review["id"], student["id"]])
        )
    for variant in ("sidebar", "mobile"):
        block = identity_block(page, variant)
        assert escape(student["name"]) in block and student["number"] in block
        assert "<img" not in block
    assert review == original


def test_saved_manual_result_counts_as_reviewed_but_remains_unresolved(
    workflow_review, client
):
    response = save(client, workflow_review, "identity")
    assert response.status_code == 302
    r = store.load(workflow_review["id"])
    p = review_progress(r["submissions"][0]["checks"][1])
    assert p["reviewed"] and not p["needs_review"] and not p["review_resolved"]
    assert p["review_unresolved"]
    assert "unresolved" in p["review_label"]


@pytest.mark.parametrize("note", ["", "Original verified"])
def test_override_can_clear_flag_with_optional_note(workflow_review, client, note):
    response = save(client, workflow_review, decision="complete", note=note)
    assert response.status_code == 302
    check = store.load(workflow_review["id"])["submissions"][0]["checks"][0]
    assert (
        review_progress(check)["review_resolved"]
        and effective_status(check) == "complete"
    )
    assert check["status"] == "issue"
    assert check["note"] == note
    assert check["history"][-1]["note"] == note


def test_needs_review_filter_hides_reviewed_rows_without_changing_totals(
    workflow_review, client
):
    r = workflow_review
    save(client, r)
    save(client, r, "identity", decision="complete", note="Identity checked")
    response = client.get(
        reverse("moderation:review", args=[r["id"]]), {"needs_review": "on"}
    )
    assert len(response.context["rows"]) == 1
    assert response.context["reviewed_count"] == 2
    assert response.context["remaining_count"] == 2
    assert response.context["rows"][0]["name"] == "Second synthetic student"


def test_save_next_uses_grid_order_and_filters(workflow_review, client):
    r = workflow_review
    response = save(
        client,
        r,
        "identity",
        decision="complete",
        note="Checked",
        action="next",
        grid="criterion=identity&needs_review=on&sort=name&direction=desc",
    )
    target = urlsplit(response.url)
    assert target.path == reverse(
        "moderation:submission", args=[r["id"], r["submissions"][1]["id"]]
    )
    assert target.fragment == "identity"
    assert "criterion=identity" in parse_qs(target.query)["grid"][0]
    page = client.get(response.url)
    assert "needs_review=on" in page.context["grid_query"]


def test_save_next_returns_grid_when_filtered_queue_finished(workflow_review, client):
    r = workflow_review
    response = save(
        client,
        r,
        action="next",
        grid="q=w12345678&criterion=readable&needs_review=on",
    )
    assert urlsplit(response.url).path == reverse("moderation:review", args=[r["id"]])


def test_return_context_cannot_redirect_outside_review(workflow_review, client):
    response = save(
        client, workflow_review, grid="next=https://example.com&saved=bad&sort=number"
    )
    assert urlsplit(response.url).path == reverse(
        "moderation:review", args=[workflow_review["id"]]
    )
    assert "example.com" not in response.url


def test_changed_finding_requires_review_again_and_rerun_preserves_audit(
    workflow_review, client
):
    r = workflow_review
    save(client, r)
    stored = store.load(r["id"])
    c = stored["submissions"][0]["checks"][0]
    assert review_progress(c)["review_resolved"]
    c["message"] = "New automated evidence"
    assert review_progress(c)["needs_review"]
    stored["submissions"][0]["state"] = "pending"
    store.save(stored)
    jobs.run(r["id"])
    new = store.load(r["id"])["submissions"][0]["checks"][0]
    assert new["reviewed_at"] == c["reviewed_at"]
    assert new["reviewed_fingerprint"] == c["reviewed_fingerprint"]
    assert new["history"] == c["history"]
    assert not review_progress(new)["reviewed"]


def test_legacy_saved_confirmation_is_counted_without_creating_new_decision(
    workflow_review,
):
    r = workflow_review
    c = r["submissions"][0]["checks"][0]
    c.update(
        decided_at="2026-11-16T10:00:00+00:00",
        history=[{"decision": "", "note": "", "at": "2026-11-16"}],
    )
    store.save(r)
    updated = jobs.snapshot(r["id"])
    check = updated["submissions"][0]["checks"][0]
    assert review_progress(check)["review_resolved"]
    assert check["reviewed_fingerprint"] == finding_fingerprint(c)
    assert check["history"] == c["history"]
    assert jobs.snapshot(r["id"]) == updated


def test_save_next_visits_each_flag_once_even_when_manual_results_are_kept(
    workflow_review, client
):
    r = workflow_review
    sid = r["submissions"][0]["id"]
    criterion = "readable"
    visited = set()
    for _ in range(5):
        assert (sid, criterion) not in visited
        visited.add((sid, criterion))
        response = client.post(
            reverse("moderation:decide", args=[r["id"], sid, criterion]),
            {"decision": "", "note": "", "action": "next", "grid": "needs_review=on"},
        )
        target = urlsplit(response.url)
        if target.path == reverse("moderation:review", args=[r["id"]]):
            break
        sid = target.path.rstrip("/").split("/")[-1]
        criterion = target.fragment
    assert len(visited) == 4
    page = client.get(response.url)
    assert page.context["reviewed_count"] == page.context["flagged_count"] == 4
    assert page.context["remaining_count"] == 0
    assert page.context["unresolved_count"] == 2
    assert page.context["rows"] == []
    followup = client.get(
        reverse("moderation:review", args=[r["id"]]), {"needs_review": "unresolved"}
    )
    assert len(followup.context["rows"]) == 2
    assert followup.context["unresolved_only"]
    stored = store.load(r["id"])
    assert all(
        s["checks"][0]["status"] == "issue" and s["checks"][1]["status"] == "review"
        for s in stored["submissions"]
    )


def test_finished_unverified_ai_is_not_reported_as_pending(workflow_review, client):
    r = workflow_review
    r["use_ai"] = True
    item = r["submissions"][0]
    item["ai"] = {"state": "complete", "facilities_pending": True}
    check = next(c for c in item["checks"] if c["id"] == "facilities")
    check.update(
        status="review",
        excluded_facilities_assessments=[
            {"status": "complete", "quotes": ["Unverified quote"]}
        ],
    )
    store.save(r)
    response = client.get(reverse("moderation:review", args=[r["id"]]))
    assert response.context["pending_ai_count"] == 0
    assert len(response.context["unverified_ai_checks"]) == 1
    assert b"Processing finished" in response.content
    assert b"data-pending-ai-count" not in response.content
    assert b'data-unverified-ai-count="1"' in response.content
    assert store.load(r["id"])["submissions"][0]["ai"]["facilities_pending"]


def test_review_next_link_opens_first_unreviewed_in_filtered_sort_order(
    workflow_review, client
):
    r = workflow_review
    response = client.get(
        reverse("moderation:review", args=[r["id"]]),
        {
            "criterion": "identity",
            "sort": "number",
            "direction": "desc",
            "needs_review": "on",
        },
    )
    target = urlsplit(response.context["next_review_url"])
    assert target.path == reverse(
        "moderation:submission", args=[r["id"], r["submissions"][1]["id"]]
    )
    assert target.fragment == "identity"
    assert "criterion=identity" in parse_qs(target.query)["grid"][0]
    assert not response.context["next_review_all"]
    assert b"data-review-next" in response.content
    assert not any(
        c.get("reviewed_at")
        for s in store.load(r["id"])["submissions"]
        for c in s["checks"]
    )


def test_review_next_offers_explicit_all_checks_route_when_filters_hide_flags(
    workflow_review, client
):
    r = workflow_review
    response = client.get(
        reverse("moderation:review", args=[r["id"]]),
        {"q": "no matches", "criterion": "project"},
    )
    assert response.context["rows"] == []
    assert response.context["next_review_all"]
    assert b"Review next (all checks)" in response.content
    target = urlsplit(response.context["next_review_url"])
    assert "criterion" not in parse_qs(parse_qs(target.query)["grid"][0])
    assert target.fragment == "readable"


def test_review_next_disappears_when_all_flags_reviewed(workflow_review, client):
    r = workflow_review
    for s in r["submissions"]:
        for criterion in ("readable", "identity"):
            client.post(
                reverse("moderation:decide", args=[r["id"], s["id"], criterion]),
                {"decision": "", "note": ""},
            )
    response = client.get(reverse("moderation:review", args=[r["id"]]))
    assert response.context["remaining_count"] == 0
    assert not response.context["next_review_url"]
    assert b"All flagged checks reviewed." in response.content
    assert b"data-review-next" not in response.content


def test_row_review_label_tracks_all_flags_even_outside_visible_columns(
    workflow_review, client
):
    r = workflow_review
    url = reverse("moderation:review", args=[r["id"]])

    def first_row():
        page = client.get(url, {"criterion": "readable"})
        return next(
            row
            for row in page.context["rows"]
            if row["id"] == r["submissions"][0]["id"]
        )

    assert first_row()["row_review_label"] == "Not reviewed"
    save(client, r)
    assert first_row()["row_review_label"] == "1 of 2 reviewed"
    assert not first_row()["row_review_complete"]
    save(client, r, "identity")
    assert first_row()["row_review_label"] == "Reviewed"
    assert first_row()["row_review_complete"]
    assert first_row()["outcome_label"] == "Fail — correction required"


def test_no_flags_does_not_imply_moderator_review(workflow_review, client):
    r = workflow_review
    for s in r["submissions"]:
        for c in s["checks"]:
            c["status"] = "complete"
    store.save(r)
    page = client.get(reverse("moderation:review", args=[r["id"]]))
    assert all(
        row["row_review_label"] == "No flagged checks"
        and not row["row_review_complete"]
        for row in page.context["rows"]
    )


def test_row_review_link_targets_first_unreviewed_finding_and_keeps_grid_context(
    workflow_review, client
):
    r = workflow_review
    page = client.get(
        reverse("moderation:review", args=[r["id"]]),
        {"sort": "number", "direction": "desc"},
    )
    row = next(
        row for row in page.context["rows"] if row["id"] == r["submissions"][0]["id"]
    )
    target = urlsplit(row["row_review_url"])
    assert target.path == reverse("moderation:submission", args=[r["id"], row["id"]])
    assert target.fragment == "readable"
    assert "sort=number" in parse_qs(target.query)["grid"][0]
    assert b'class="row-review-link"' in page.content
    save(client, r)
    save(client, r, "identity")
    page = client.get(reverse("moderation:review", args=[r["id"]]))
    row = next(
        row for row in page.context["rows"] if row["id"] == r["submissions"][0]["id"]
    )
    assert not row["row_review_url"] and row["row_review_label"] == "Reviewed"


def test_student_and_overall_headers_sort_rows_in_both_directions(
    workflow_review, client
):
    r = workflow_review
    for c in r["submissions"][0]["checks"]:
        c["status"] = "complete"
    store.save(r)
    url = reverse("moderation:review", args=[r["id"]])
    ascending = client.get(url, {"sort": "name", "direction": "asc"})
    descending = client.get(url, {"sort": "name", "direction": "desc"})
    assert [row["id"] for row in ascending.context["rows"]] == list(
        reversed([row["id"] for row in descending.context["rows"]])
    )
    assert (
        b'data-sort="name"' in ascending.content
        and b'data-sort="overall"' in ascending.content
    )
    issues_first = client.get(url, {"sort": "overall", "direction": "asc"})
    passes_first = client.get(url, {"sort": "overall", "direction": "desc"})
    assert [row["outcome"] for row in issues_first.context["rows"]] == [
        "issue",
        "complete",
    ]
    assert [row["outcome"] for row in passes_first.context["rows"]] == [
        "complete",
        "issue",
    ]
    assert b'aria-sort="ascending"' in issues_first.content
    assert b'aria-sort="descending"' in passes_first.content
