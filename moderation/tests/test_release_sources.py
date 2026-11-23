# ruff: noqa: F811
import copy

from moderation import release, release_bulk, release_store, store
from moderation.tests.test_release import ready_workspace, save, workspace  # noqa: F401


def test_technical_refresh_does_not_reopen_feedback_but_invalidates_live_preview(
    ready_workspace,
):
    data, _, source = ready_workspace
    data = save(data)
    original = copy.deepcopy(data)
    before = release.source_state(data)["w10000000"]
    checks = source["submissions"][0]["checks"]
    for check in checks:
        check.update(
            category="Reorganised group",
            engine_version="Refreshed",
            pdf_refresh_history=[{"message": "Earlier extract"}],
        )
    checks[0]["message"] = "Text extraction completed; same completion outcome."
    checks.reverse()
    store.save(source)
    bundle = release.source_state(data)["w10000000"]
    assert not release.source_changed(data["records"]["w10000000"], bundle)
    assert release.release_valid(data["records"]["w10000000"], bundle)
    assert release_bulk.record_token(
        data["records"]["w10000000"], before
    ) != release_bulk.record_token(data["records"]["w10000000"], bundle)
    assert release_store.load() == original


def test_new_ambiguous_result_remains_a_material_change(ready_workspace):
    data, _, source = ready_workspace
    source["submissions"][0]["checks"][0]["status"] = "moderator"
    store.save(source)
    bundle = release.source_state(data)["w10000000"]
    assert release.source_changed(data["records"]["w10000000"], bundle)
    row = release_bulk.classify(data["records"]["w10000000"], bundle)
    assert "source" in row["reason_codes"]
    assert "automated result changed" in row["reasons"][0]


def test_changed_file_and_changed_human_decision_always_block(ready_workspace):
    data, cohort, source = ready_workspace
    check = source["submissions"][0]["checks"][0]
    check.update(
        decision="complete", note="A new staff judgement", decided_at="2026-11-23"
    )
    store.save(source)
    assert release.source_changed(
        data["records"]["w10000000"], release.source_state(data)["w10000000"]
    )
    source["submissions"][0]["checks"][0] = copy.deepcopy(
        cohort["submissions"][0]["checks"][0]
    )
    store.save(source)
    file = source["submissions"][0]["files"][0]
    (store.review_dir(source["id"]) / file["id"]).write_bytes(b"Changed document")
    assert release.source_changed(
        data["records"]["w10000000"], release.source_state(data)["w10000000"]
    )


def test_changed_required_wording_is_material_even_with_same_issue_status(
    ready_workspace,
):
    data, _, _ = ready_workspace
    old = release.source_state(data)["w10000000"]
    bundle = copy.deepcopy(old)
    check = next(c for c in bundle["sources"][0]["checks"] if c["id"] == "ratings")
    check.update(
        status="issue",
        decision="issue",
        message="Row 1: enter a numeric value for Final Result.",
    )
    baseline = {
        **data["records"]["w10000000"],
        "source_evidence": copy.deepcopy(bundle),
        "source_fingerprint": release.digest(bundle),
    }
    check["message"] = "Row 2: enter a numeric value for Final Result."
    assert release.source_changed(baseline, bundle)


def conversation(bundle, **changes):
    source = bundle["sources"][0]
    return {
        "review_id": source["review_id"],
        "attachment_hashes": source["attachment_hashes"],
        "submitted": source["submitted"],
        "acceptance": {
            "at": "2026-11-15T23:34:05+00:00",
            "quote": "I am happy with this batch.",
        },
        "decisions": [],
        **changes,
    }


def test_batch_acceptance_alone_is_not_a_blanket_pass(ready_workspace):
    data, _, _ = ready_workspace
    bundle = release.source_state(data)["w10000000"]
    bundle["sources"][0]["checks"][0]["status"] = "moderator"
    bundle["sources"][0]["conversation_decisions"] = conversation(bundle)
    proposed = release.propose(bundle)
    assert proposed["decision_gaps"] and proposed["outcome"] == ""
    assert proposed["conversation_acceptance"]["quote"]


def test_explicit_conversation_decision_is_recovered_with_source_binding(
    ready_workspace,
):
    data, _, _ = ready_workspace
    bundle = release.source_state(data)["w10000000"]
    check = next(c for c in bundle["sources"][0]["checks"] if c["id"] == "student_ra")
    check["status"] = "moderator"
    recovered = conversation(
        bundle,
        decisions=[
            {
                "criterion": "student_ra",
                "agreed_outcome": "issue",
                "at": "2026-11-15T23:34:05+00:00",
                "reason": "The signature area was confirmed blank.",
                "provenance": {"path": "Synthetic conversation", "line": 10},
            }
        ],
    )
    bundle["sources"][0]["conversation_decisions"] = recovered
    proposed = release.propose(bundle)
    assert proposed["outcome"] == "issue" and not proposed["decision_gaps"]
    assert "sign-off" in proposed["student_corrections"]
    recovered["attachment_hashes"] = ["different-file"]
    assert release.propose(bundle)["decision_gaps"]


def test_later_recorded_adjudication_supersedes_old_conversation(ready_workspace):
    data, _, _ = ready_workspace
    bundle = release.source_state(data)["w10000000"]
    source = bundle["sources"][0]
    source["conversation_decisions"] = conversation(
        bundle,
        decisions=[
            {
                "criterion": "student_ra",
                "agreed_outcome": "issue",
                "at": "2026-11-15T23:34:05+00:00",
            }
        ],
    )
    source["audit_adjudications"] = [
        {
            "criterion": "student_ra",
            "agreed_outcome": "complete",
            "at": "2026-11-18T12:00:00+00:00",
        }
    ]
    assert release.propose(bundle)["outcome"] == "complete"


def test_recovery_can_be_limited_to_the_imported_students(ready_workspace):
    data, _, _ = ready_workspace
    untouched = copy.deepcopy(data["records"]["w10000001"])
    result = release.recover_recorded_judgements(
        data["revision"], numbers={"w10000000"}
    )
    assert result["records"]["w10000001"] == untouched


def test_automatic_referral_does_not_reopen_a_definite_human_outcome(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    item["validation_audits"] = [
        {"findings": {c["id"]: "complete" for c in item["checks"]}}
    ]
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    data = save(data)
    item["checks"][0].update(status="moderator", message="An automatic referral")
    store.save(source)
    bundle = release.source_state(data)["w10000000"]
    assert release.release_valid(data["records"]["w10000000"], bundle)
    assert release.propose(bundle)["outcome"] == "complete"
