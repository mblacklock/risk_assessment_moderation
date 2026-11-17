# Imported pytest fixture is intentionally also a test parameter.
# ruff: noqa: F811
import copy

from django.urls import reverse

from moderation import store
from moderation.feedback import feedback_readiness
from moderation.review_policy import checking_version
from moderation.tests.test_workflow import workflow_review  # noqa: F401
from moderation.validation import comparison_token
from moderation.workflow import review_progress


def audited_review(review):
    review["review_mode"] = "routine"
    for item in review["submissions"]:
        for check in item["checks"]:
            check.update(
                status="issue" if check["id"] == "readable" else "complete", decision=""
            )
        item["validation_audits"] = [
            {
                "at": "2026-11-17T10:00:00+00:00",
                "reviewer": "Synthetic reviewer",
                "findings": {c["id"]: c["status"] for c in item["checks"]},
                "automated_snapshot": copy.deepcopy(item["checks"]),
            }
        ]
    store.save(review)
    return review


def approval_payload(review, **changes):
    return {
        "source": "Rule",
        "version": checking_version(),
        "basis": comparison_token(review),
        "action": "approve",
        "note": "Synthetic staff validation decision",
        **changes,
    }


def test_inline_approval_bypasses_only_definitive_findings_and_can_be_withdrawn(
    workflow_review, client
):
    review = audited_review(workflow_review)
    item = review["submissions"][0]
    original_items = copy.deepcopy(review["submissions"])
    url = reverse("moderation:approve_check", args=[review["id"], "readable"])
    comparison = reverse("moderation:validation_comparison", args=[review["id"]])
    assert b"Approve this check" in client.get(comparison).content
    assert not feedback_readiness(review, item)[0]
    assert client.get(url).status_code == 405
    payload = approval_payload(review)
    response = client.post(url, payload)
    assert response.status_code == 302 and response.url.endswith("#stat-readable")
    saved = store.load(review["id"])
    assert saved["submissions"] == original_items
    assert saved["review_mode"] == "routine"
    approved = saved["automation_approvals"]["readable:Rule"]
    assert approved["reference"] and approved["basis"] == payload["basis"]
    check = saved["submissions"][0]["checks"][0]
    assert not review_progress(check, saved)["needs_review"]
    assert not review_progress(check, saved)["reviewed"]
    assert review_progress({**check, "status": "review"}, saved)["needs_review"]
    assert feedback_readiness(saved, saved["submissions"][0])[0]
    assert b"Withdraw approval" in client.get(comparison).content
    assert client.post(url, payload).status_code == 302
    assert len(store.load(review["id"])["review_process_history"]) == 1
    assert client.post(url, {**payload, "action": "revoke"}).status_code == 302
    revoked = store.load(review["id"])
    assert "readable:Rule" not in revoked["automation_approvals"]
    assert review_progress(check, revoked)["needs_review"]
    assert not feedback_readiness(revoked, revoked["submissions"][0])[0]
    assert revoked["review_process_history"][-1]["previous_approval"] == approved
    assert revoked["submissions"] == original_items


def test_inline_approval_requires_current_represented_audit_evidence(
    workflow_review, client
):
    review = audited_review(workflow_review)
    url = reverse("moderation:approve_check", args=[review["id"], "readable"])
    payload = approval_payload(review)
    for changes in [{"basis": "stale"}, {"version": "old"}, {"source": "AI"}]:
        assert client.post(url, {**payload, **changes}).status_code == 409
    assert client.post(url, {**payload, "source": "unknown"}).status_code == 400
    assert (
        client.post(
            reverse("moderation:approve_check", args=[review["id"], "word_limits"]),
            payload,
        ).status_code
        == 404
    )

    def change(data):
        data["submissions"][0]["validation_audits"][-1]["findings"]["readable"] = (
            "complete"
        )

    store.update(review["id"], change)
    assert client.post(url, payload).status_code == 409
    saved = store.load(review["id"])
    assert not saved.get("automation_approvals")
    saved["submissions"][0].pop("validation_audits")
    store.save(saved)
    assert client.post(url, approval_payload(saved)).status_code == 409


def test_legacy_version_statistics_cannot_approve_current_checks(
    workflow_review, client
):
    review = audited_review(workflow_review)
    for item in review["submissions"]:
        for check in item["validation_audits"][-1]["automated_snapshot"]:
            check.pop("engine_version", None)
    store.save(review)
    comparison = client.get(
        reverse("moderation:validation_comparison", args=[review["id"]])
    )
    readable = next(
        stat
        for stat in comparison.context["check_statistics"]
        if stat["id"] == "readable"
    )
    assert not readable["strata"][0]["can_approve"]
    url = reverse("moderation:approve_check", args=[review["id"], "readable"])
    assert client.post(url, approval_payload(review)).status_code == 409
