from types import SimpleNamespace
from unittest.mock import patch

from django.urls import reverse

from moderation import jobs, store
from moderation.ai import Judgement, ai_work_counts, apply_ai, eligible_ai_checks
from moderation.checks import check_documents
from moderation.criteria import effective_status
from moderation.documents import extract_document
from moderation.exports import csv_bytes
from moderation.tests.test_review import STUDENT, archive_bytes, document_bytes
from moderation.workflow import review_progress


def blank_checks():
    return check_documents(
        [extract_document(document_bytes(location=""), "synthetic.docx")], STUDENT
    )


def test_blank_workspace_skips_facilities_without_passing_or_duplicating_omission():
    checks, _ = blank_checks()
    found = {c["id"]: c for c in checks}
    assert found["location"]["status"] == "issue"
    assert found["facilities"]["status"] == "skipped"
    assert found["facilities"]["blocked_by"] == "location"
    assert not review_progress(found["facilities"])["needs_review"]
    assert "facilities" not in eligible_ai_checks(checks)
    assert "location" not in eligible_ai_checks(checks)
    item = {"id": "synthetic", "checks": checks, "ai": {"state": "pending"}}
    assert ai_work_counts([item], True)[0] == 3
    item["ai"] = {
        "state": "complete",
        "facilities_pending": True,
        "needs_manual_review": ["facilities"],
    }
    assert ai_work_counts([item], True) == (0, [])


def test_ai_schema_never_requests_facilities_when_workspace_is_blank():
    checks, extracted = blank_checks()

    def parse(**kwargs):
        schema = kwargs["text_format"]
        assert "facilities" not in schema.model_fields
        assert "location" not in schema.model_fields
        judgement = Judgement(
            status="complete",
            explanation="Synthetic assessment",
            quotes=["Eye strain from screen use"],
        )
        return SimpleNamespace(
            output_parsed=schema(**{key: judgement for key in schema.model_fields}),
            usage=None,
        )

    with patch("moderation.ai.OpenAI") as api:
        api.return_value.responses.parse.side_effect = parse
        result = apply_ai(checks, extracted, STUDENT)
    assert not result.get("facilities_pending")
    assert next(c for c in checks if c["id"] == "facilities")["status"] == "skipped"


def test_present_workspace_still_requires_separate_consistency_assessment():
    checks, _ = check_documents(
        [extract_document(document_bytes(location="Computing room"), "synthetic.docx")],
        STUDENT,
    )
    assert next(c for c in checks if c["id"] == "facilities")["status"] == "review"
    assert "facilities" in eligible_ai_checks(checks)


def test_saved_blank_facilities_skip_clears_retry_and_retains_history(
    settings, tmp_path, client, monkeypatch
):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    with patch.object(jobs, "start"):
        r = jobs.create_review(
            archive_bytes(document_bytes(location="")), "Synthetic dependency", False
        )
    jobs.run(r["id"])
    r = store.load(r["id"])
    item = r["submissions"][0]
    old = next(c for c in item["checks"] if c["id"] == "facilities")
    old.pop("blocked_by")
    old.update(
        status="unable",
        message="Workspace unavailable",
        decision="review",
        note="Staff note",
        history=[{"note": "Retain"}],
    )
    item["ai"] = {
        "state": "complete",
        "facilities_pending": True,
        "needs_manual_review": ["facilities"],
    }
    r["use_ai"] = True
    store.save(r)
    with patch.object(jobs, "apply_ai") as ai:
        updated = jobs.snapshot(r["id"])
        ai.assert_not_called()
    new = next(
        c for c in updated["submissions"][0]["checks"] if c["id"] == "facilities"
    )
    assert effective_status(new) == "skipped"
    assert new["decision"] == old["decision"] and new["note"] == old["note"]
    assert new["history"] == old["history"]
    assert new["superseded_blocked_facilities_finding"] == old
    assert not updated["submissions"][0]["ai"].get("facilities_pending")
    assert jobs.snapshot(r["id"]) == updated
    assert b"Skipped" in csv_bytes(updated)
    url = reverse("moderation:submission", args=[r["id"], item["id"]])
    response = client.get(url)
    assert next(c for c in response.context["checks"] if c["id"] == "facilities")[
        "blocked"
    ]
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    with patch.object(jobs, "start"):
        response = client.post(
            reverse("moderation:resume", args=[r["id"]]), {"action": "retry_ai"}
        )
    assert response.status_code == 302
    assert store.load(r["id"])["submissions"][0]["state"] == "done"
