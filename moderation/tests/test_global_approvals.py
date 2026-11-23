import copy
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django.urls import reverse

from moderation import global_approvals, jobs, store
from moderation.review_policy import checking_version
from moderation.tests.test_review import archive_bytes
from moderation.workflow import finding_fingerprint, review_progress


@pytest.fixture
def workspace(settings, tmp_path):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    return settings.REVIEW_ROOT


def approve(key="ratings:Rule"):
    return global_approvals.set_approval(
        key,
        "approve",
        checking_version(),
        "Synthetic independent validation",
        "Recommended parser improvements remain open.",
    )


def check(**changes):
    return {
        "id": "ratings",
        "source": "Rule",
        "status": "issue",
        "engine_version": checking_version(),
        "decision": "",
        **changes,
    }


def test_new_reviews_share_approvals_and_revocation_never_restores_local(workspace):
    approve()
    with patch.object(jobs, "start") as start:
        first = jobs.create_review(archive_bytes(), "First synthetic", False)
        second = jobs.create_review(archive_bytes(), "Second synthetic", False)
        assert start.call_count == 2
    assert first["review_mode"] == second["review_mode"] == "routine"
    original = copy.deepcopy(first)
    assert review_progress(check(), first)["automatic"]
    assert review_progress(check(), second)["automatic"]
    assert not review_progress(check(), {**first, "review_mode": "validation"})[
        "automatic"
    ]
    global_approvals.set_approval("ratings:Rule", "revoke", checking_version())
    first["automation_approvals"] = {
        "ratings:Rule": {
            "version": checking_version(),
            "reference": "Old local approval",
        }
    }
    assert review_progress(check(), first)["needs_review"]
    assert review_progress(check(), second)["needs_review"]
    assert store.load(original["id"]) == original
    assert global_approvals.load()["history"][-1]["previous_approval"]["reference"]


def test_global_decisions_keep_uncertain_unknown_overridden_and_changed_models_manual(
    workspace, monkeypatch
):
    approve()
    review = {"review_mode": "routine"}
    for changes in [{"status": s} for s in ("review", "moderator", "unable")]:
        assert review_progress(check(**changes), review)["needs_review"]
    for changes in [
        {"engine_version": "old"},
        {"engine_version": None},
        {"source": "AI"},
        {"decision": "complete"},
    ]:
        assert review_progress(check(**changes), review)["needs_review"]
    original_check = check()
    monkeypatch.setenv("OPENAI_MODEL", "different-synthetic-model")
    assert review_progress(original_check, review)["needs_review"]


def test_acknowledging_an_eligible_finding_does_not_make_confirmation_required(
    workspace,
):
    approve()
    finding = check(message="A synthetic rating issue", evidence=[])
    review = {"review_mode": "routine"}
    before = review_progress(finding, review)
    assert before["automatic"] and not before["review_required"]
    finding.update(
        reviewed_at="2026-11-23T12:00:00+00:00",
        reviewed_fingerprint=finding_fingerprint(finding),
        history=[{"decision": "", "note": "Confirmed existing finding"}],
    )
    saved = copy.deepcopy(finding)
    approval_bytes = global_approvals.registry_path().read_bytes()
    after = review_progress(finding, review)
    assert after["reviewed"] and after["review_resolved"]
    assert not after["automatic"]
    assert not after["review_required"] and not after["needs_review"]
    assert after["review_label"] == "Reviewed — automated result confirmed"
    assert finding == saved
    assert global_approvals.registry_path().read_bytes() == approval_bytes
    assert review_progress(finding, {"review_mode": "validation"})["review_required"]
    finding["decision"] = "complete"
    assert review_progress(finding, review)["review_required"]
    global_approvals.set_approval("ratings:Rule", "revoke", checking_version())
    finding["decision"] = ""
    assert review_progress(finding, review)["review_required"]


def test_grid_denominator_is_stable_after_an_optional_acknowledgement(workspace):
    from django.http import QueryDict

    from moderation.views import grid_context

    approve()
    with patch.object(jobs, "start"):
        review = jobs.create_review(archive_bytes(), "Synthetic denominator", False)
    jobs.run(review["id"])
    review = store.load(review["id"])
    review["review_mode"] = "routine"
    for finding in review["submissions"][0]["checks"]:
        finding.update(status="complete", decision="")
    findings = {c["id"]: c for c in review["submissions"][0]["checks"]}
    findings["ratings"]["status"] = "issue"
    findings["identity"]["status"] = "review"
    before = grid_context(review, QueryDict())
    findings["ratings"].update(
        reviewed_at="2026-11-23T12:00:00+00:00",
        reviewed_fingerprint=finding_fingerprint(findings["ratings"]),
        history=[{"decision": "", "note": "Optional confirmation"}],
    )
    original = copy.deepcopy(review)
    after = grid_context(review, QueryDict())
    assert before["flagged_count"] == after["flagged_count"] == 1
    assert before["reviewed_count"] == after["reviewed_count"] == 0
    assert before["remaining_count"] == after["remaining_count"] == 1
    assert review == original


def test_page_evidence_stale_form_history_and_navigation(workspace, client):
    url = reverse("moderation:global_approvals")
    page = client.get(url)
    assert page.status_code == 200
    assert b"Global approvals" in page.content
    assert len(page.context["rows"]) == 24
    payload = {
        "key": "ratings:Rule",
        "action": "approve",
        "version": checking_version(),
        "revision": "new",
        "reference": "",
        "note": "Synthetic recommendation",
    }
    assert client.post(url, payload).status_code == 400
    assert global_approvals.load() is None
    assert (
        client.post(url, {**payload, "reference": "Synthetic audit"}).status_code == 302
    )
    assert client.get(url).context["approved_count"] == 1
    assert client.post(url, {**payload, "reference": "Stale form"}).status_code == 400
    assert len(global_approvals.load()["history"]) == 1
    page = client.get(url)
    assert b"Synthetic recommendation" in page.content
    response = client.post(
        url,
        {
            **payload,
            "action": "revoke",
            "revision": page.context["revision"],
        },
    )
    assert response.status_code == 302
    assert client.get(url).context["approved_count"] == 0
    assert len(global_approvals.load()["history"]) == 2
    assert client.get(reverse("moderation:index")).content.count(b"Global approvals")


def test_unsupported_and_stale_approvals_cannot_be_saved(workspace):
    for key, version in [
        ("word_limits:Rule", checking_version()),
        ("ratings:Other", checking_version()),
        ("ratings:Rule", "old"),
    ]:
        with pytest.raises(ValueError):
            global_approvals.set_approval(key, "approve", version, "Synthetic evidence")
    assert global_approvals.load() is None


def test_unreadable_registry_fails_closed_without_restoring_local(workspace):
    workspace.mkdir()
    global_approvals.registry_path().write_text("invalid json", encoding="utf-8")
    review = {
        "review_mode": "routine",
        "automation_approvals": {
            "ratings:Rule": {"version": checking_version(), "reference": "Old local"}
        },
    }
    assert review_progress(check(), review)["needs_review"]
    from moderation.views import global_approvals as page

    assert page(RequestFactory().get("/approvals/")).status_code == 503


def test_feedback_gate_uses_shared_approval_and_withdrawal(workspace):
    from moderation.criteria import CRITERIA, REMINDER_CHECKS
    from moderation.feedback import feedback_readiness

    approve()
    item = {
        "id": "synthetic",
        "state": "done",
        "number": "w00000000",
        "checks": [
            check(id=key, status="issue" if key == "ratings" else "complete")
            for key, _, _ in CRITERIA
            if key not in REMINDER_CHECKS
        ],
        "ai": {"state": "off"},
    }
    review = {
        "state": "done",
        "use_ai": False,
        "review_mode": "routine",
        "submissions": [item],
    }
    assert feedback_readiness(review, item)[0]
    global_approvals.set_approval("ratings:Rule", "revoke", checking_version())
    assert not feedback_readiness(review, item)[0]
