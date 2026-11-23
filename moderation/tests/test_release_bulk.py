# Imported fixture is also used as a pytest parameter.
# ruff: noqa: F811
import copy
import io
from unittest.mock import patch

import pytest
from django.core import signing
from django.urls import reverse
from openpyxl import load_workbook

from moderation import release, release_bulk, release_store, store
from moderation.tests.test_release import fields, ready_workspace, save, workspace  # noqa: F401


def state(data, scope="existing"):
    return release_bulk.overview(data, release.source_state(data), scope)


def token(data, scope="existing"):
    return release_bulk.preview_manifest(data, state(data, scope))


def test_readiness_separates_existing_and_independent_and_definite_human_results(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path, count=4, sourced=3)
    first, second, third = source["submissions"]
    first["checks"][0].update(
        status="moderator", message="An automated routing decision"
    )
    first["validation_audits"] = [
        {"findings": {c["id"]: "complete" for c in first["checks"]}}
    ]
    second["checks"][0].update(status="issue", message="Unconfirmed automated finding")
    third["checks"][0].update(
        status="issue", decision="issue", message="Assessor is not the student"
    )
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=4)
    before = copy.deepcopy(data)
    summary = state(data)
    assert summary["counts"] == {
        "total": 3,
        "ready": 2,
        "attention": 1,
        "finalised": 0,
        "edited": 0,
    }
    assert summary["outcomes"] == {"complete": 1, "supervisor": 0, "issue": 1}
    assert summary["independent_count"] == 1
    assert state(data, "independent")["counts"]["ready"] == 0
    assert release_store.load() == before


def test_ambiguous_waiver_and_missing_wording_are_excluded(ready_workspace):
    data, cohort, source = ready_workspace
    bundles = release.source_state(data)
    proposal = {
        "decision_gaps": ["Contradictory waiver judgements remain unresolved."],
        "wording_gaps": [],
    }
    with patch("moderation.release.propose", return_value=proposal):
        row = release_bulk.classify(data["records"]["w10000000"], bundles["w10000000"])
        assert row["readiness"] == "attention"
        assert row["reason_codes"] == ["conflict"]
    record = {**data["records"]["w10000000"], "outcome": "issue"}
    row = release_bulk.classify(record, bundles["w10000000"])
    assert row["readiness"] == "attention" and row["reason_codes"] == ["wording"]


def test_bulk_requires_confirmation_name_and_untampered_preview(ready_workspace):
    data, _, _ = ready_workspace
    preview = token(data)
    before = release_store.path().read_bytes()
    for kwargs in [{}, {"confirm": True, "moderator": ""}]:
        with pytest.raises(ValueError):
            release_bulk.finalise(
                preview, kwargs.pop("moderator", "Synthetic staff"), **kwargs
            )
    with pytest.raises(ValueError, match="invalid or expired"):
        release_bulk.finalise(preview + "x", "Synthetic staff", confirm=True)
    assert release_store.path().read_bytes() == before


def test_success_records_provenance_and_keeps_independent_students_out(ready_workspace):
    data, cohort, source = ready_workspace
    originals = (store.load(cohort["id"]), store.load(source["id"]))
    before = copy.deepcopy(data["records"]["w10000002"])
    with (
        patch(
            "moderation.jobs.snapshot", side_effect=AssertionError("No reprocessing")
        ),
        patch("moderation.ai.apply_ai", side_effect=AssertionError("No AI")),
    ):
        result = release_bulk.finalise(token(data), "Synthetic finaliser", confirm=True)
    assert len(result["finalised"]) == 2 and not result["excluded"]
    latest = release_store.load()
    assert latest["records"]["w10000002"] == before
    for number in ("w10000000", "w10000001"):
        record = latest["records"][number]
        assert record["moderator"] == "Synthetic finaliser"
        assert record["finalised_at"] == result["at"]
        history = record["history"][-1]
        assert (
            history["method"] == "bulk" and history["operation"] == result["operation"]
        )
        assert record["final_text"] == release.format_feedback(data["records"][number])
        assert record["source_evidence"] == data["records"][number]["source_evidence"]
    assert (store.load(cohort["id"]), store.load(source["id"])) == originals


def test_changed_source_is_excluded_at_execution_others_can_proceed(ready_workspace):
    data, _, source = ready_workspace
    preview = token(data)
    source["submissions"][0]["checks"][0]["message"] = "Source changed after preview"
    store.save(source)
    result = release_bulk.finalise(preview, "Synthetic staff", confirm=True)
    assert [r["number"] for r in result["finalised"]] == ["w10000001"]
    assert result["excluded"][0]["number"] == "w10000000"
    assert "changed" in result["excluded"][0]["reason"]
    assert release_store.load()["records"]["w10000000"]["status"] == "proposed"


def test_existing_finalised_records_are_never_replaced(ready_workspace):
    data, _, _ = ready_workspace
    preview = token(data)
    after = save(data)
    existing = copy.deepcopy(after["records"]["w10000000"])
    result = release_bulk.finalise(preview, "Bulk staff", confirm=True)
    assert len(result["finalised"]) == 1 and len(result["excluded"]) == 1
    assert release_store.load()["records"]["w10000000"] == existing
    assert state(release_store.load())["counts"]["finalised"] == 2


def test_staff_draft_requires_review_and_preserves_exact_public_wording(
    ready_workspace,
):
    data, _, _ = ready_workspace
    draft_fields = fields(
        outcome="issue",
        student_corrections="Specific staff wording.\nKeep this line break.",
    )
    after = release.save_record(
        data["revision"],
        "w10000000",
        draft_fields,
        source_token=release.digest(release.source_state(data)["w10000000"]),
    )
    preview = token(after)
    with pytest.raises(ValueError, match="staff-edited drafts"):
        release_bulk.finalise(preview, "Bulk staff", confirm=True)
    result = release_bulk.finalise(
        preview, "Bulk staff", confirm=True, confirm_edits=True
    )
    assert len(result["finalised"]) == 2
    record = release_store.load()["records"]["w10000000"]
    assert record["student_corrections"] == draft_fields["student_corrections"]
    assert record["final_text"] == release.format_feedback(draft_fields)
    assert record["history"][-1]["previous"]["status"] == "draft"


def test_an_edit_after_preview_is_not_approved_by_old_confirmation(ready_workspace):
    data, _, _ = ready_workspace
    preview = token(data)
    release.save_record(
        data["revision"],
        "w10000000",
        fields(outcome="supervisor", supervisor_followup="New follow-up wording."),
        source_token=release.digest(release.source_state(data)["w10000000"]),
    )
    result = release_bulk.finalise(
        preview, "Bulk staff", confirm=True, confirm_edits=True
    )
    assert len(result["excluded"]) == 1 and len(result["finalised"]) == 1
    record = release_store.load()["records"]["w10000000"]
    assert (
        record["status"] == "draft"
        and record["supervisor_followup"] == "New follow-up wording."
    )


def test_repeated_operation_is_a_true_no_op_and_new_empty_preview_cannot_finalise(
    ready_workspace,
):
    data, _, _ = ready_workspace
    preview = token(data)
    first = release_bulk.finalise(preview, "Staff", confirm=True)
    before = release_store.path().read_bytes()
    second = release_bulk.finalise(preview, "Staff", confirm=True)
    assert second["repeated"] and first["operation"] == second["operation"]
    assert release_store.path().read_bytes() == before
    with pytest.raises(ValueError, match="no ready feedback"):
        release_bulk.finalise(token(release_store.load()), "Staff", confirm=True)
    assert release_store.path().read_bytes() == before


def test_newly_eligible_records_are_not_added_to_an_old_preview(ready_workspace):
    data, _, source = ready_workspace
    source["submissions"][0]["checks"][0].update(status="issue")
    store.save(source)
    # Make current evidence the proposal baseline, with an unresolved finding.
    data = release.recover_recorded_judgements(data["revision"])
    preview = token(data)
    source["submissions"][0]["checks"][0].update(status="complete")
    store.save(source)

    # Recover only the newly settled student; the other student's preview remains
    # unchanged. A full recovery would deliberately invalidate both old tokens.
    def recover_one(register):
        bundle = release.source_state(register)["w10000000"]
        register["records"]["w10000000"] = release.new_record("w10000000", bundle)

    release_store.update(data["revision"], recover_one)
    result = release_bulk.finalise(preview, "Staff", confirm=True)
    assert [r["number"] for r in result["finalised"]] == ["w10000001"]
    assert release_store.load()["records"]["w10000000"]["status"] == "proposed"


def test_independent_feedback_uses_same_explicit_process_only_in_separate_group(
    ready_workspace,
):
    data, _, _ = ready_workspace
    number = "w10000002"
    data = release.save_record(
        data["revision"],
        number,
        fields(),
        source_token=release.digest(release.source_state(data)[number]),
    )
    assert state(data)["counts"]["ready"] == 2
    assert state(data, "independent")["counts"]["ready"] == 1
    result = release_bulk.finalise(
        token(data, "independent"),
        "Independent finaliser",
        confirm=True,
        confirm_edits=True,
    )
    assert [r["number"] for r in result["finalised"]] == [number]
    assert release_store.load()["records"]["w10000000"]["status"] == "proposed"


def test_preview_and_download_are_read_only_and_public_only(ready_workspace, client):
    data, _, _ = ready_workspace
    before = release_store.path().read_bytes()
    page = client.get(reverse("moderation:release_bulk"))
    assert page.status_code == 200
    assert "2 records to finalise" in page.content.decode()
    assert "1 independent-feedback students are excluded" in page.content.decode()
    response = client.post(
        reverse("moderation:release_bulk"),
        {"action": "download", "preview_token": token(data)},
    )
    assert response.status_code == 200
    book = load_workbook(io.BytesIO(response.content), read_only=True)
    rows = list(book.active.values)
    assert len(rows) == 3 and len(rows[0]) == 4
    assert "not finalised" in rows[0][2]
    assert "Result: Pass" in rows[1][3]
    assert "source_fingerprint" not in str(rows)
    assert release_store.path().read_bytes() == before
    book.close()


def test_download_rejects_changed_preview_and_post_requires_confirmation(
    ready_workspace, client
):
    data, _, source = ready_workspace
    preview = token(data)
    response = client.post(
        reverse("moderation:release_bulk"),
        {"action": "finalise", "preview_token": preview, "moderator": "Staff"},
    )
    assert response.status_code == 409
    source["submissions"][0]["checks"][0]["message"] = "changed"
    store.save(source)
    response = client.post(
        reverse("moderation:release_bulk"),
        {"action": "download", "preview_token": preview},
    )
    assert response.status_code == 409
    assert all(
        r["status"] != "finalised" for r in release_store.load()["records"].values()
    )


def test_release_export_only_contains_current_finals_and_public_text(ready_workspace):
    data, _, source = ready_workspace
    release_bulk.finalise(token(data), "Staff", confirm=True)
    final = release_store.load()
    book = load_workbook(
        io.BytesIO(release.export_xlsx(final, release.source_state(final), True)),
        read_only=True,
    )
    assert book.active.max_row == 3
    assert len(list(book.active.values)[0]) == 5
    book.close()
    source["submissions"][0]["checks"][0].update(
        status="issue", message="private change"
    )
    store.save(source)
    book = load_workbook(
        io.BytesIO(release.export_xlsx(final, release.source_state(final), True)),
        read_only=True,
    )
    assert book.active.max_row == 2
    assert "private change" not in str(list(book.active.values))
    book.close()


def test_scope_readiness_outcome_and_batch_filters(ready_workspace, client):
    data, _, _ = ready_workspace
    response = client.get(
        reverse("moderation:release_index"),
        {
            "scope": "existing",
            "readiness": "ready",
            "outcome": "complete",
            "batch": "Synthetic assessment",
        },
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "w10000000" in html and "w10000001" in html
    assert "w10000002" not in html
    response = client.get(reverse("moderation:release_index"), {"scope": "independent"})
    assert (
        "w10000002" in response.content.decode()
        and "w10000000" not in response.content.decode()
    )


def test_expired_preview_cannot_be_approved(ready_workspace):
    data, _, _ = ready_workspace
    preview = token(data)
    with patch.object(signing.TimestampSigner, "timestamp", return_value="1"):
        old = release_bulk.preview_manifest(data, state(data))
    with pytest.raises(ValueError, match="expired"):
        release_bulk.finalise(old, "Staff", confirm=True)
    assert release_bulk.load_manifest(preview)["scope"] == "existing"
