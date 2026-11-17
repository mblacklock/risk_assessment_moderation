# Imported pytest fixture is intentionally also a test parameter.
# ruff: noqa: F811
import copy

from django.http import QueryDict
from django.urls import reverse

from moderation import store
from moderation.feedback import feedback_readiness
from moderation.review_policy import checking_version
from moderation.tests.test_workflow import workflow_review  # noqa: F401
from moderation.views import grid_context
from moderation.workflow import review_progress


def approve(review, check):
    version = checking_version()
    review["review_mode"] = "routine"
    review.setdefault("automation_approvals", {})[
        f"{check['id']}:{check['source']}"
    ] = {
        "version": version,
        "reference": "Synthetic staff validation record",
    }
    check["engine_version"] = version


def test_only_version_matched_approved_definitive_flags_are_automatic(workflow_review):
    review = workflow_review
    check = review["submissions"][0]["checks"][0]
    approve(review, check)
    assert review_progress(check, review)["automatic"]
    assert not review_progress(check, review)["needs_review"]
    assert not review_progress(check, review)["reviewed"]
    assert not review_progress(check, review)["review_resolved"]
    for status in ["review", "unable", "moderator"]:
        uncertain = {**check, "status": status}
        assert review_progress(uncertain, review)["needs_review"]
    for changed in [{"source": "AI"}, {"engine_version": "old"}, {"decision": "issue"}]:
        assert review_progress({**check, **changed}, review)["needs_review"]
    assert review_progress(check, {**review, "review_mode": "validation"})[
        "needs_review"
    ]
    assert review_progress(check, {})["needs_review"]


def test_model_change_invalidates_approval(workflow_review, monkeypatch):
    review = workflow_review
    check = review["submissions"][0]["checks"][0]
    approve(review, check)
    monkeypatch.setenv("OPENAI_MODEL", "synthetic-different-model")
    assert review_progress(check, review)["needs_review"]


def test_audit_list_hides_outcomes(workflow_review, client):
    review = workflow_review
    response = client.get(reverse("moderation:validation_list", args=[review["id"]]))
    assert response.status_code == 200
    assert b"Synthetic finding" not in response.content
    assert b"Fail" not in response.content


def test_workflow_chooser_separates_audits_from_moderation_and_preserves_approvals(
    workflow_review, client
):
    review = workflow_review
    check = review["submissions"][0]["checks"][0]
    approve(review, check)
    store.save(review)
    before = copy.deepcopy(review)
    url = reverse("moderation:review_process", args=[review["id"]])
    page = client.get(url)
    assert b"Validate the tool" in page.content
    assert b"Moderate submissions" in page.content
    assert b'name="approvals"' not in page.content
    assert b"Synthetic finding" not in page.content
    assert store.load(review["id"]) == before
    for mode, destination in [("validation", "validation_list"), ("routine", "review")]:
        response = client.post(url, {"mode": mode})
        assert response.url == reverse(f"moderation:{destination}", args=[review["id"]])
        saved = store.load(review["id"])
        assert saved["review_mode"] == mode
        assert saved["automation_approvals"] == before["automation_approvals"]
        assert saved["submissions"] == before["submissions"]
    assert client.post(url, {"mode": "unknown"}).status_code == 400


def test_approved_flags_leave_queue_and_feedback_gate_but_uncertainty_blocks(
    workflow_review,
):
    review = workflow_review
    item = review["submissions"][0]
    first, second = item["checks"][:2]
    approve(review, first)
    assert not feedback_readiness(review, item)[0]
    second["status"] = "supervisor"
    approve(review, second)
    assert feedback_readiness(review, item)[0]
    context = grid_context(review, QueryDict(""))
    assert context["automatic_count"] == 3
    assert not next(row for row in context["rows"] if row["id"] == item["id"])[
        "row_review_url"
    ]
    assert context["remaining_count"] == 1  # Other student's uncertain finding remains.
    review["automation_approvals"] = {}
    assert not feedback_readiness(review, item)[0]


def test_process_settings_require_evidence_preserve_history_and_do_not_run_ai(
    workflow_review, client
):
    review = workflow_review
    url = reverse("moderation:study_settings", args=[review["id"]])
    before = copy.deepcopy(review["submissions"])
    response = client.get(url)
    assert response.status_code == 200
    payload = {
        "mode": "routine",
        "approvals": ["readable:Rule"],
        "version": checking_version(),
    }
    response = client.post(url, payload)
    assert response.status_code == 200
    assert "reference" in response.context["form"].errors
    assert store.load(review["id"])["submissions"] == before
    response = client.post(url, {**payload, "reference": "Synthetic validation report"})
    assert response.status_code == 302
    saved = store.load(review["id"])
    assert saved["submissions"] == before
    assert saved.get("review_mode", "validation") == "validation"
    assert len(saved["review_process_history"]) == 1
    response = client.post(url, {**payload, "reference": "Report", "version": "stale"})
    assert response.status_code == 200
    assert len(store.load(review["id"])["review_process_history"]) == 1


def test_independent_audit_hides_results_then_retains_comparison_without_moderating(
    workflow_review, client
):
    review = workflow_review
    item = review["submissions"][0]
    review["audit_details"] = {"auditor": "Reviewer A", "minutes": "", "comments": ""}
    item["checks"][0]["message"] = "AUTOMATED RESULT MUST BE HIDDEN"
    store.save(review)
    url = reverse("moderation:validation_audit", args=[review["id"], item["id"]])
    response = client.get(url)
    assert response.status_code == 200
    assert b"AUTOMATED RESULT MUST BE HIDDEN" not in response.content
    payload = {"reviewer": "Reviewer A", "minutes": "4.5", "notes": "Synthetic audit"}
    payload.update({f"audit_{c['id']}": "complete" for c in item["checks"]})
    response = client.post(url, payload)
    assert response.status_code == 302
    saved = store.load(review["id"])["submissions"][0]
    assert saved["checks"] == item["checks"]
    assert saved["validation_audits"][0]["automated_snapshot"] == item["checks"]
    assert client.get(response.url).status_code == 200
    assert b"AUTOMATED RESULT MUST BE HIDDEN" not in client.get(response.url).content
    assert (
        client.get(
            reverse("moderation:validation_comparison", args=[review["id"]])
        ).status_code
        == 403
    )
    client.post(url, {**payload, "reviewer": "Reviewer B"})
    assert len(store.load(review["id"])["submissions"][0]["validation_audits"]) == 2
    assert b"AUTOMATED RESULT MUST BE HIDDEN" not in client.get(url).content


def test_batch_audit_details_are_shared_and_blank_checks_are_not_assumed_complete(
    workflow_review, client
):
    review = workflow_review
    item = review["submissions"][0]
    overview = reverse("moderation:validation_list", args=[review["id"]])
    audit_url = reverse("moderation:validation_audit", args=[review["id"], item["id"]])
    original = copy.deepcopy(item["checks"])
    response = client.post(
        overview, {"auditor": "Auditor One", "minutes": "", "comments": "Batch notes"}
    )
    assert response.status_code == 302
    page = client.get(audit_url)
    assert b"Auditor One" in page.content
    assert b'type="radio"' in page.content
    assert b'name="reviewer"' not in page.content
    assert b'name="minutes"' not in page.content
    client.post(audit_url, {"notes": "No outcomes supplied"})
    assert not store.load(review["id"])["submissions"][0].get("validation_audits")
    outcomes = {f"audit_{c['id']}": "complete" for c in item["checks"]}
    assert client.post(audit_url, outcomes).status_code == 302
    client.post(
        overview, {"auditor": "Auditor One", "minutes": "12", "comments": "Finished"}
    )
    saved = store.load(review["id"])
    assert saved["audit_details"]["minutes"] == "12"
    assert len(saved["audit_details_history"]) == 2
    record = saved["submissions"][0]["validation_audits"][0]
    assert record["reviewer"] == "Auditor One"
    assert record["audit_details_snapshot"]["comments"] == "Batch notes"
    assert saved["submissions"][0]["checks"] == original


def test_batch_comparison_requires_all_selected_audits_and_uses_frozen_results(
    workflow_review, client
):
    review = workflow_review
    review["audit_details"] = {"auditor": "Auditor One"}
    review["submissions"][0]["checks"][0]["message"] = "FROZEN TOOL RESULT"
    store.save(review)
    overview = reverse("moderation:validation_list", args=[review["id"]])
    comparison = reverse("moderation:validation_comparison", args=[review["id"]])
    assert client.get(comparison).status_code == 403

    for index, item in enumerate(review["submissions"]):
        url = reverse("moderation:validation_audit", args=[review["id"], item["id"]])
        findings = {f"audit_{c['id']}": "complete" for c in item["checks"]}
        response = client.post(url, findings)
        assert response.url == overview + "?audit_saved=1"
        page = client.get(response.url)
        assert page.context["audited_count"] == index + 1
        assert b"FROZEN TOOL RESULT" not in page.content
        if index == 0:
            assert not page.context["comparison_ready"]
            assert client.get(comparison).status_code == 403
            assert client.get(url + "?compare=1", follow=True).status_code == 403
            client.post(url, findings)
            assert client.get(overview).context["audited_count"] == 1
    assert client.get(overview).context["comparison_ready"]

    def change(data):
        data["submissions"][0]["checks"][0]["message"] = "LATER TOOL RESULT"

    store.update(review["id"], change)
    result = client.get(comparison)
    assert result.status_code == 200
    assert b"FROZEN TOOL RESULT" in result.content
    assert b"LATER TOOL RESULT" not in result.content
    assert result.context["check_count"] == 48

    def add_unaudited(data):
        extra = copy.deepcopy(data["submissions"][0])
        extra["id"] = "11111111-1111-4111-8111-111111111111"
        extra["number"] = "w99999999"
        extra.pop("validation_audits")
        data["submissions"].append(extra)

    store.update(review["id"], add_unaudited)
    assert not client.get(overview).context["comparison_ready"]
    assert client.get(comparison).status_code == 403


def test_word_limits_are_an_inactive_reminder_even_for_old_saved_issues(
    workflow_review, client
):
    from moderation.criteria import effective_status, overall
    from moderation.feedback import feedback_items
    from moderation.validation import audit_overview, comparison_rows
    from moderation.views import ValidationAuditForm

    review = workflow_review
    item = review["submissions"][0]
    for check in item["checks"]:
        check.update(status="complete", decision="")
    word = next(c for c in item["checks"] if c["id"] == "word_limits")
    word.update(status="issue", decision="issue", message="Legacy word-limit finding")
    assert effective_status(word) == "skipped"
    assert overall(item["checks"]) == "complete"
    assert not review_progress(word, review)["needs_review"]
    assert not feedback_items(item)
    findings = {
        f"audit_{c['id']}": "complete"
        for c in item["checks"]
        if c["id"] != "word_limits"
    }
    form = ValidationAuditForm(findings)
    assert form.is_valid()
    assert form.cleaned_data["audit_word_limits"] == "skipped"
    item["validation_audits"] = [
        {
            "findings": {
                c["id"]: "complete" for c in item["checks"] if c["id"] != "word_limits"
            },
            "automated_snapshot": item["checks"],
        }
    ]
    assert audit_overview(review)["audited_count"] == 1
    assert len(comparison_rows(item["validation_audits"][0])) == 24
    store.save(review)
    url = reverse("moderation:validation_audit", args=[review["id"], item["id"]])
    page = client.get(url)
    assert b"reminder-only" in page.content
    assert b'name="audit_word_limits"' not in page.content
    assert (
        client.post(
            reverse(
                "moderation:decide", args=[review["id"], item["id"], "word_limits"]
            ),
            {"decision": "issue"},
        ).status_code
        == 409
    )
    assert store.load(review["id"])["submissions"][0]["checks"] == item["checks"]


def test_audits_can_be_saved_before_name_time_or_comments(workflow_review, client):
    review = workflow_review
    for item in review["submissions"]:
        url = reverse("moderation:validation_audit", args=[review["id"], item["id"]])
        page = client.get(url)
        assert b"before saving findings" not in page.content
        response = client.post(
            url, {f"audit_{c['id']}": "complete" for c in item["checks"]}
        )
        assert response.status_code == 302
    saved = store.load(review["id"])
    original_records = copy.deepcopy(
        [item["validation_audits"] for item in saved["submissions"]]
    )
    assert original_records[0][0]["reviewer"] == ""
    assert original_records[0][0]["audit_details_snapshot"] == {}
    overview = reverse("moderation:validation_list", args=[review["id"]])
    assert client.get(overview).context["audited_count"] == 2
    client.post(
        overview,
        {"auditor": "Late-entered auditor", "minutes": "2", "comments": "Finished"},
    )
    comparison = client.get(
        reverse("moderation:validation_comparison", args=[review["id"]])
    )
    assert comparison.status_code == 200
    assert b"Late-entered auditor" in comparison.content
    assert [
        item["validation_audits"] for item in store.load(review["id"])["submissions"]
    ] == original_records


def test_saved_audit_can_be_reopened_and_corrected_without_losing_original(
    workflow_review, client
):
    review = workflow_review
    item = review["submissions"][0]
    url = reverse("moderation:validation_audit", args=[review["id"], item["id"]])
    payload = {f"audit_{c['id']}": "complete" for c in item["checks"]}
    payload["notes"] = "Original audit note"
    assert client.post(url, payload).status_code == 302
    first = copy.deepcopy(
        store.load(review["id"])["submissions"][0]["validation_audits"][0]
    )
    page = client.get(url)
    assert page.context["editing_audit"]
    assert page.context["form"]["audit_identity"].value() == "complete"
    assert page.context["form"]["notes"].value() == "Original audit note"
    assert b"Save changes" in page.content
    assert b"Synthetic finding" not in page.content

    def later_tool_change(data):
        data["submissions"][0]["checks"][0]["message"] = "Different current tool text"

    store.update(review["id"], later_tool_change)
    assert client.post(url, {**payload, "audit_identity": "issue"}).status_code == 302
    saved = store.load(review["id"])
    history = saved["submissions"][0]["validation_audits"]
    assert len(history) == 2 and history[0] == first
    assert history[1]["findings"]["identity"] == "issue"
    assert history[1]["revision_of"] == first["at"]
    assert history[1]["automated_snapshot"] == first["automated_snapshot"]
    assert history[1]["ai_metadata"] == first["ai_metadata"]
    assert client.get(url).context["form"]["audit_identity"].value() == "issue"
    overview = client.get(reverse("moderation:validation_list", args=[review["id"]]))
    assert overview.context["audited_count"] == 1
    assert b"Edit audit" in overview.content
