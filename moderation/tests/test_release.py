import copy
import io
import json
import uuid
from unittest.mock import patch

import pytest
from django.urls import reverse
from openpyxl import load_workbook

from moderation import release, release_store, store
from moderation.criteria import CRITERIA, REMINDER_CHECKS


def sample_item(number, file_id, index):
    return {
        "id": str(uuid.uuid4()),
        "number": number,
        "name": f"Synthetic student {index}",
        "submitted": "2026-10-21T10:00:00+00:00",
        "attempt": f"Assessment_{number}_attempt_2026-10-21-10-00-00.txt",
        "files": [{"id": file_id, "name": "Synthetic.txt"}],
        "checks": [
            {
                "id": key,
                "label": label,
                "category": category,
                "status": "complete",
                "source": "Rule",
                "decision": "",
                "message": "Present",
                "evidence": [],
            }
            for key, label, category in CRITERIA
            if key not in REMINDER_CHECKS
        ],
    }


def workspace(settings, tmp_path, count=3, sourced=2):
    settings.REVIEW_ROOT = tmp_path / "reviews"
    settings.ALLOWED_HOSTS = ["testserver"]
    cohort = {
        "id": str(uuid.uuid4()),
        "title": "All v2",
        "created": "2026-11-18",
        "state": "done",
        "latest_only": True,
        "submissions": [],
    }
    source = {
        **cohort,
        "id": str(uuid.uuid4()),
        "title": "Synthetic assessment",
        "submissions": [],
    }
    for index in range(count):
        number = f"w{10000000 + index}"
        file_id = str(uuid.uuid4())
        item = sample_item(number, file_id, index)
        cohort["submissions"].append(item)
        store.review_dir(cohort["id"]).mkdir(parents=True, exist_ok=True)
        (store.review_dir(cohort["id"]) / file_id).write_bytes(
            f"Synthetic attachment {index}".encode()
        )
        if index < sourced:
            copy_item = copy.deepcopy(item)
            copy_item["id"] = str(uuid.uuid4())
            source["submissions"].append(copy_item)
            store.review_dir(source["id"]).mkdir(parents=True, exist_ok=True)
            (store.review_dir(source["id"]) / file_id).write_bytes(
                f"Synthetic attachment {index}".encode()
            )
    store.save(cohort)
    store.save(source)
    return cohort, source


@pytest.fixture
def ready_workspace(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    return data, cohort, source


def fields(**changes):
    return {
        "outcome": "complete",
        "student_corrections": "",
        "supervisor_completion": "",
        "supervisor_followup": "",
        "moderator": "Synthetic moderator",
        "resolution": "",
        "original_moderator_feedback": "",
        **changes,
    }


def save(data, number="w10000000", **changes):
    bundle = release.source_state(data)[number]
    return release.save_record(
        data["revision"],
        number,
        fields(**changes),
        finalise=True,
        confirm=True,
        source_token=release.digest(bundle),
    )


def test_106_unique_roster_65_sources_preserved_and_no_checking_calls(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path, count=106, sourced=65)
    before_cohort = store.load(cohort["id"])
    before_source = store.load(source["id"])
    with (
        patch("moderation.jobs.snapshot", side_effect=AssertionError("No refresh")),
        patch("moderation.jobs.start", side_effect=AssertionError("No analysis")),
        patch("moderation.ai.apply_ai", side_effect=AssertionError("No AI")),
    ):
        data = release.create(cohort["id"], [source["id"]])
    assert len(data["records"]) == 106
    assert (
        sum(bool(r["source_evidence"]["sources"]) for r in data["records"].values())
        == 65
    )
    assert (
        sum(r["status"] == "awaiting_feedback" for r in data["records"].values()) == 41
    )
    assert not any(r["status"] == "finalised" for r in data["records"].values())
    assert store.load(cohort["id"]) == before_cohort
    assert store.load(source["id"]) == before_source
    assert release_store.load() == data


def test_duplicate_students_and_missing_roster_fail_closed(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    cohort["submissions"].append(copy.deepcopy(cohort["submissions"][0]))
    store.save(cohort)
    with pytest.raises(ValueError, match="ambiguous|duplicate"):
        release.create(cohort["id"], [source["id"]], expected_count=3)
    assert release_store.load() is None


def test_latest_attempt_and_all_attachments_are_used(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    older = copy.deepcopy(cohort["submissions"][0])
    older.update(id=str(uuid.uuid4()), submitted="2026-10-20T10:00:00+00:00")
    cohort["submissions"].append(older)
    store.save(cohort)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    assert len(data["records"]) == 3
    assert data["records"]["w10000000"]["attempt"] == "2026-10-21T10:00:00+00:00"


def test_superseded_agreement_and_explicit_waiver_preserve_originals(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "ratings")
    check.update(status="issue", message="Technical defect")
    item["validation_audits"] = [
        {"at": "audit-1", "findings": {c["id"]: c["status"] for c in item["checks"]}}
    ]
    item["audit_adjudications"] = [
        {
            "audit_at": "audit-1",
            "criterion": "ratings",
            "reason": "Staff-agreed outcome: Issue found.",
        },
        {
            "audit_at": "audit-1",
            "criterion": "ratings",
            "reason": "Staff-agreed outcome: Pass.",
        },
    ]
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    assert data["records"][item["number"]]["outcome"] == "complete"
    assert (
        len(
            data["records"][item["number"]]["source_evidence"]["sources"][0][
                "audit_adjudications"
            ]
        )
        == 2
    )
    assert store.load(source["id"]) == source
    assert release.recorded_waiver(
        {
            "classification": "Technical rating-entry defect; moderator would waive resubmission"
        }
    )
    assert not release.recorded_waiver({"reason": "Perhaps waive it?"})


def test_historical_waiver_is_not_promoted_to_fail(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "ratings")
    check.update(status="issue", message="Technical defect")
    store.save(source)
    historical = {
        "review_id": source["id"],
        "adjudications": [
            {
                "student_number": item["number"],
                "check": "ratings",
                "classification": "Technical rating-entry defect; moderator would waive resubmission",
                "agreed_outcome": "issue",
                "reason": "An annotation needs cleanup.",
            }
        ],
    }
    path = store.review_dir(source["id"]) / "evaluation-decisions.json"
    path.write_text(json.dumps(historical), encoding="utf-8")
    before = path.read_bytes()
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    record = data["records"][item["number"]]
    assert record["outcome"] == "complete" and record["proposal"]["waivers"]
    assert not record["student_corrections"]
    assert path.read_bytes() == before


def test_stale_feedback_wording_retained_but_not_finalised(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    check = next(c for c in item["checks"] if c["id"] == "location")
    check.update(status="issue", message="Missing location", decision="issue")
    item["elp_feedback"] = {
        "signature": "old",
        "wording": {"location": "A previously edited public action."},
        "text": "Original public text",
    }
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    record = data["records"][item["number"]]
    assert "A previously edited public action." in record["student_corrections"]
    assert record["status"] != "finalised"
    assert not record["proposal"]["decision_gaps"]
    assert not record["proposal"]["wording_gaps"]
    assert record["proposal"]["annotations"]
    assert store.load(source["id"]) == source


def test_finalisation_replacement_history_and_refresh_protect_existing(ready_workspace):
    data, cohort, source = ready_workspace
    record = data["records"]["w10000000"]
    token = release.digest(release.source_state(data)[record["number"]])
    with pytest.raises(ValueError, match="Explicitly confirm"):
        release.save_record(
            data["revision"],
            record["number"],
            fields(),
            finalise=True,
            source_token=token,
        )
    data = save(data)
    original = copy.deepcopy(data["records"][record["number"]])
    data = release.refresh(data["revision"])
    assert data["records"][record["number"]]["final_text"] == original["final_text"]
    with pytest.raises(ValueError, match="replacement"):
        save(data)
    data = release.save_record(
        data["revision"],
        record["number"],
        fields(
            outcome="supervisor",
            supervisor_followup="Review the supporting assessment.",
        ),
        finalise=True,
        confirm=True,
        replace=True,
        source_token=token,
    )
    revised = data["records"][record["number"]]
    assert revised["history"][-1]["previous"]["final_text"] == original["final_text"]
    assert "Supervisor follow-up (non-blocking)" in revised["final_text"]


def test_changed_evidence_blocks_export_before_refresh_and_stale_editor(
    ready_workspace,
):
    data, cohort, source = ready_workspace
    data = save(data)
    stale = release.digest(release.source_state(data)["w10000000"])
    source["submissions"][0]["checks"][0]["message"] = "Changed saved evidence"
    store.save(source)
    bundles = release.source_state(data)
    assert not release.release_valid(data["records"]["w10000000"], bundles["w10000000"])
    sheet = load_workbook(io.BytesIO(release.export_xlsx(data, bundles))).active
    assert sheet["C2"].value is None and sheet["D2"].value is None
    with pytest.raises(ValueError, match="editor was open"):
        release.save_record(
            data["revision"],
            "w10000000",
            fields(),
            finalise=True,
            confirm=True,
            replace=True,
            source_token=stale,
        )


def test_manual_moderator_entry_does_not_infer_from_original_text(ready_workspace):
    data, cohort, source = ready_workspace
    number = "w10000002"
    token = release.digest(release.source_state(data)[number])
    original = "Private original moderator judgement; not automatically classified."
    with pytest.raises(ValueError, match="explicit final outcome"):
        release.save_record(
            data["revision"],
            number,
            fields(outcome="", original_moderator_feedback=original),
            finalise=True,
            confirm=True,
            source_token=token,
        )
    data = release.save_record(
        data["revision"],
        number,
        fields(
            outcome="issue",
            student_corrections="Add your signature.",
            original_moderator_feedback=original,
        ),
        finalise=True,
        confirm=True,
        source_token=token,
    )
    assert data["records"][number]["original_moderator_feedback"] == original
    assert original not in data["records"][number]["final_text"]


def test_final_validation_blocks_ambiguous_or_contradictory_output():
    for changes in [
        {"outcome": "issue"},
        {"student_corrections": "Required correction"},
        {"outcome": "supervisor"},
        {"supervisor_followup": "Follow up"},
        {
            "outcome": "issue",
            "student_corrections": "AI evidence could not be verified.",
        },
    ]:
        with pytest.raises(ValueError):
            release.validate_final(fields(**changes))


def test_export_only_finalised_public_fields_and_formula_safety(ready_workspace):
    data, cohort, source = ready_workspace
    data = save(
        data,
        outcome="issue",
        student_corrections="=A public instruction.\n\nA second correction.",
        resolution="PRIVATE RESOLUTION",
        original_moderator_feedback="PRIVATE ORIGINAL",
    )
    bundles = release.source_state(data)
    workbook = load_workbook(io.BytesIO(release.export_xlsx(data, bundles)))
    assert workbook.sheetnames == ["Student feedback"]
    sheet = workbook.active
    assert sheet.max_row == 4 and sheet.max_column == 5
    assert (
        sheet["C2"].value == "Fail" and "1. =A public instruction." in sheet["D2"].value
    )
    assert sheet["D2"].data_type == "s" and sheet["D2"].alignment.wrap_text
    assert sheet["C3"].value is None and sheet["D3"].value is None
    assert "PRIVATE" not in str(list(sheet.values))
    final = load_workbook(io.BytesIO(release.export_xlsx(data, bundles, True))).active
    assert final.max_row == 2


def test_conflicts_missing_wording_and_attempt_mismatch_held(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    first = source["submissions"][0]
    first["validation_audits"] = [
        {"at": "a1", "findings": {c["id"]: "complete" for c in first["checks"]}}
    ]
    first["audit_adjudications"] = [
        {
            "audit_at": "a1",
            "criterion": "location",
            "classification": "unresolved",
            "reason": "This classification is ambiguous.",
        }
    ]
    store.save(source)
    bundle = release.evidence_bundle(
        {
            "cohort_review_id": cohort["id"],
            "source_review_ids": [source["id"]],
            "expected_count": 3,
        }
    )[first["number"]]
    assert release.propose(bundle)["outcome"] == ""
    assert release.propose(bundle)["issues"]
    second = copy.deepcopy(bundle["sources"][0])
    bundle["sources"].append(second)
    assert "Multiple assessment sources" in release.propose(bundle)["issues"][0]
    bundle["sources"] = [second]
    second["attachment_hashes"] = ["different"]
    assert "does not match" in release.propose(bundle)["issues"][0]


def test_supplemental_decisions_reused_only_for_matching_attempts(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    old = copy.deepcopy(source)
    old.update(id=str(uuid.uuid4()), title="Old all")
    store.review_dir(old["id"]).mkdir(parents=True)
    for index, item in enumerate(old["submissions"]):
        for file in item["files"]:
            (store.review_dir(old["id"]) / file["id"]).write_bytes(
                f"Synthetic attachment {index}".encode()
            )
    check = next(c for c in old["submissions"][0]["checks"] if c["id"] == "identity")
    check.update(status="issue", decision="complete")
    store.save(old)
    data = release.create(cohort["id"], [source["id"]], [old["id"]], expected_count=3)
    record = data["records"]["w10000000"]
    assert len(record["source_evidence"]["supplemental"]) == 1
    assert (
        next(
            d for d in record["proposal"]["decisions"] if d["criterion"] == "identity"
        )["origin"]
        == "Saved moderation decision"
    )


def test_release_ui_preview_does_not_save_and_finalisation_is_explicit(
    ready_workspace, client
):
    data, cohort, source = ready_workspace
    page = client.get(reverse("moderation:release_index"))
    assert page.status_code == 200 and page.context["bulk"]["counts"]["total"] == 2
    assert page.context["bulk"]["independent_count"] == 1
    number = "w10000002"
    url = reverse("moderation:release_editor", args=[number])
    page = client.get(url)
    assert b"Original moderator feedback" in page.content
    payload = {
        **fields(outcome="issue", student_corrections="Complete your sign-off."),
        "revision": data["revision"],
        "source_token": release.digest(release.source_state(data)[number]),
        "action": "preview",
    }
    assert client.post(url, payload).status_code == 200
    assert release_store.load() == data
    response = client.post(url, {**payload, "action": "finalise", "confirm": "on"})
    assert response.status_code == 302
    assert release_store.load()["records"][number]["status"] == "finalised"
    assert client.get(reverse("moderation:release_export")).status_code == 200
    assert (
        client.get(reverse("moderation:release_index") + "?q=does-not-exist").context[
            "rows"
        ]
        == []
    )


def test_unresolved_decision_requires_private_resolution_without_leaking_it(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    source["submissions"][0]["checks"][0].update(
        status="review", message="An uncertain source finding", note="PRIVATE EVIDENCE"
    )
    source["submissions"][0]["ai"] = {"state": "pending"}
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    token = release.digest(release.source_state(data)["w10000000"])
    with pytest.raises(ValueError, match="resolved"):
        save(data)
    with patch("moderation.jobs.start", side_effect=AssertionError("No AI")):
        data = release.save_record(
            data["revision"],
            "w10000000",
            fields(resolution="PRIVATE: staff accepted the evidence."),
            finalise=True,
            confirm=True,
            resolve=True,
            source_token=token,
        )
    assert "PRIVATE" not in data["records"]["w10000000"]["final_text"]
    assert store.load(source["id"])["submissions"][0]["ai"]["state"] == "pending"


def test_stale_register_revision_rejected_without_replacing_draft(ready_workspace):
    data, cohort, source = ready_workspace
    revision = data["revision"]
    updated = release.refresh(revision)
    assert updated["revision"] != revision
    with pytest.raises(ValueError, match="register changed"):
        save(data)
    assert release_store.load() == updated


def test_missing_criterion_and_unresolved_audit_disagreement_are_held(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    item["validation_audits"] = [
        {
            "at": "audit-1",
            "findings": {c["id"]: "complete" for c in item["checks"]},
        }
    ]
    item["checks"][0]["status"] = "issue"
    absent = item["checks"].pop()["id"]
    item["validation_audits"][0]["findings"].pop(absent)
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    proposal = data["records"][item["number"]]["proposal"]
    assert proposal["outcome"] == ""
    assert not any(
        "audit and automated outcome differ" in x for x in proposal["issues"]
    )
    assert any("Final judgements are absent" in x for x in proposal["decision_gaps"])


@pytest.mark.parametrize(
    "criterion,reason",
    [
        (
            "facilities",
            "Staff-agreed mapping: another criterion owns the omission. Agreed facilities outcome: Skipped pending clarification, not Pass.",
        ),
        (
            "declarations",
            "Staff-authorised bulk review. Agreed outcome: Skipped because the ethics form is missing.",
        ),
    ],
)
def test_explicit_recorded_skip_labels_are_read_without_guessing(criterion, reason):
    assert (
        release.adjudicated_status({"criterion": criterion, "reason": reason})
        == "skipped"
    )
    assert (
        release.adjudicated_status(
            {
                "criterion": "hs_relevance",
                "reason": "Manual routing was appropriate; final judgement is not decided.",
            }
        )
        is None
    )
