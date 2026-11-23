# Imported fixture is also used as a pytest parameter.
# ruff: noqa: F811
import copy
import hashlib

from openpyxl import Workbook

from moderation import release, store
from moderation.release_manual import read_records
from moderation.tests.test_release import fields, ready_workspace, workspace  # noqa: F401


def audit(item, at="2026-11-18T10:00:00+00:00"):
    item["validation_audits"] = [
        {
            "at": at,
            "reviewer": "Synthetic reviewer",
            "findings": {c["id"]: "complete" for c in item["checks"]},
        }
    ]


def test_audit_outcome_is_not_reopened_by_unsettled_automated_disagreement(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    item["checks"][0].update(status="issue", message="A technical parser conclusion")
    audit(item)
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    proposal = data["records"][item["number"]]["proposal"]
    assert proposal["outcome"] == "complete"
    assert not proposal["decision_gaps"]
    assert not proposal["student_corrections"]
    assert store.load(source["id"]) == source


def test_unrelated_audit_revision_keeps_the_latest_agreed_judgement(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["audit_adjudications"] = [
        {
            "criterion": "identity",
            "audit_at": item["validation_audits"][0]["at"],
            "at": "2026-11-18T11:00:00+00:00",
            "classification": "human_error",
            "reason": "Staff-agreed outcome: Issue found. The assessor is not the student.",
        }
    ]
    revised = copy.deepcopy(item["validation_audits"][0])
    revised.update(at="2026-11-18T12:00:00+00:00")
    revised["findings"]["specialists"] = "supervisor"
    item["validation_audits"].append(revised)
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    proposal = data["records"][item["number"]]["proposal"]
    assert not proposal["decision_gaps"]
    assert proposal["outcome"] == "issue"
    assert "own full name" in proposal["student_corrections"]
    assert proposal["supervisor_followup"]


def test_later_actual_criterion_edit_supersedes_earlier_judgement(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["validation_audits"][0]["findings"]["identity"] = "issue"
    item["audit_adjudications"] = [
        {
            "criterion": "identity",
            "audit_at": item["validation_audits"][0]["at"],
            "at": "2026-11-18T11:00:00+00:00",
            "reason": "Staff-agreed outcome: Issue found.",
        }
    ]
    revised = copy.deepcopy(item["validation_audits"][0])
    revised.update(at="2026-11-18T12:00:00+00:00")
    revised["findings"]["identity"] = "complete"
    item["validation_audits"].append(revised)
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    assert data["records"][item["number"]]["outcome"] == "complete"


def test_routing_annotation_is_not_a_new_human_judgement(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["audit_adjudications"] = [
        {
            "criterion": "identity",
            "audit_at": item["validation_audits"][0]["at"],
            "classification": "agreement",
            "agreed_outcome": "moderator",
            "reason": "Automatic name variants should be referred to staff; the original staff audit is retained.",
        }
    ]
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    proposal = data["records"][item["number"]]["proposal"]
    assert proposal["outcome"] == "complete" and not proposal["decision_gaps"]
    assert proposal["annotations"]


def manual_book(path, number, outcome="Pass", text="A private original comment."):
    book = Workbook()
    sheet = book.active
    sheet.title = "Students"
    sheet.append(
        ["Student number", "Student name", "Pass/Fail", "Feedback", "Research only"]
    )
    sheet.append([number, "Synthetic student", outcome, text, "PRIVATE EXTRA COLUMN"])
    book.save(path)


def test_original_operational_pass_not_changed_by_technical_audit_issue(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["validation_audits"][0]["findings"]["ratings"] = "issue"
    store.save(source)
    path = tmp_path / "original-manual.xlsx"
    manual_book(path, item["number"])
    before = path.read_bytes()
    data = release.create(
        cohort["id"],
        [source["id"]],
        expected_count=3,
        manual_workbooks={source["id"]: str(path)},
    )
    record = data["records"][item["number"]]
    assert record["outcome"] == "complete"
    technical = next(
        d for d in record["proposal"]["decisions"] if d["criterion"] == "ratings"
    )
    assert technical["technical_outcome"] == "issue"
    assert not technical["waived"]  # Explicit Pass is evidence, not an invented waiver.
    assert "PRIVATE EXTRA COLUMN" not in str(record)
    assert path.read_bytes() == before
    assert store.load(source["id"]) == source


def test_explicit_later_agreed_correction_is_not_hidden_by_original_pass(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["audit_adjudications"] = [
        {
            "criterion": "identity",
            "audit_at": item["validation_audits"][0]["at"],
            "classification": "human_error",
            "reason": "Staff-agreed outcome: Issue found. A new omission was confirmed.",
        }
    ]
    store.save(source)
    path = tmp_path / "manual.xlsx"
    manual_book(path, item["number"])
    data = release.create(
        cohort["id"],
        [source["id"]],
        expected_count=3,
        manual_workbooks={source["id"]: str(path)},
    )
    assert data["records"][item["number"]]["outcome"] == "issue"


def test_manual_workbook_is_read_only_keyed_and_original_text_is_private(tmp_path):
    path = tmp_path / "manual.xlsx"
    manual_book(
        path,
        "w10000000",
        outcome="Fail",
        text="Internal study comments, not public feedback.",
    )
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    records = read_records(path)
    assert records["w10000000"]["outcome"] == "issue"
    assert records["w10000000"]["row"] == 2
    assert "Internal" in records["w10000000"]["feedback"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_genuine_missing_decision_is_separate_from_wording(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    source["submissions"][0]["checks"][0].update(
        status="issue", message="Unconfirmed automated finding"
    )
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    proposal = data["records"]["w10000000"]["proposal"]
    assert len(proposal["decision_gaps"]) == 1
    assert not proposal["wording_gaps"]
    assert proposal["outcome"] == ""


def test_recovery_does_not_overwrite_staff_drafts_or_finalised_records(ready_workspace):
    data, cohort, source = ready_workspace
    number = "w10000000"
    token = release.digest(release.source_state(data)[number])
    data = release.save_record(
        data["revision"],
        number,
        fields(),
        finalise=True,
        confirm=True,
        source_token=token,
    )
    final = copy.deepcopy(data["records"][number])
    number2 = "w10000001"
    data = release.save_record(
        data["revision"],
        number2,
        fields(student_corrections="Staff-edited draft."),
        source_token=release.digest(release.source_state(data)[number2]),
    )
    recovered = release.recover_recorded_judgements(data["revision"])
    assert recovered["records"][number]["final_text"] == final["final_text"]
    assert recovered["records"][number2]["student_corrections"] == "Staff-edited draft."


def test_compact_editor_shows_feedback_first_without_historical_conflict_checklist(
    ready_workspace, client
):
    from django.urls import reverse

    data, cohort, source = ready_workspace
    page = client.get(reverse("moderation:release_editor", args=["w10000000"]))
    html = page.content.decode()
    assert html.index("Generated student feedback") < html.index("Review and finalise")
    assert "Specific saved decisions still missing" not in html
    assert "Edit wording or recorded outcome" in html
    assert 'name="resolve"' not in html


def test_missing_current_check_is_recovered_from_the_saved_staff_audit(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["checks"].pop()
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    proposal = data["records"][item["number"]]["proposal"]
    assert proposal["outcome"] == "complete"
    assert not proposal["decision_gaps"]


def test_guidance_row_is_not_repeated_as_a_required_rating_correction(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["audit_adjudications"] = [
        {
            "criterion": "risk_reduction",
            "audit_at": item["validation_audits"][0]["at"],
            "reason": "Staff-agreed outcome: Issue found. Genuine pairs are 2 to 2 and 2 to 4. Guidance-only row 13 and count artefacts are excluded.",
        }
    ]
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    assert "row 13" not in data["records"][item["number"]]["student_corrections"]
    assert (
        "Review the controls and ratings"
        in data["records"][item["number"]]["student_corrections"]
    )


def test_finalisation_of_settled_feedback_does_not_ask_for_another_resolution(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["checks"][0].update(status="issue", message="An old tool disagreement")
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    number = item["number"]
    assert not data["records"][number]["proposal"]["decision_gaps"]
    updated = release.save_record(
        data["revision"],
        number,
        fields(),
        finalise=True,
        confirm=True,
        source_token=release.digest(release.source_state(data)[number]),
    )
    assert updated["records"][number]["status"] == "finalised"


def test_later_saved_moderation_supersedes_earlier_adjudication(settings, tmp_path):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    item["audit_adjudications"] = [
        {
            "criterion": "identity",
            "at": "2026-11-18T11:00:00+00:00",
            "agreed_outcome": "issue",
        }
    ]
    check = next(c for c in item["checks"] if c["id"] == "identity")
    check.update(decision="complete", decided_at="2026-11-19T11:00:00+00:00")
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    assert data["records"][item["number"]]["outcome"] == "complete"


def test_old_correction_wording_does_not_become_supervisor_followup(
    settings, tmp_path
):
    cohort, source = workspace(settings, tmp_path)
    item = source["submissions"][0]
    audit(item)
    check = next(c for c in item["checks"] if c["id"] == "specialists")
    check.update(status="issue")
    item["elp_feedback"] = {
        "wording": {"specialists": "Select Yes or No; the answers are missing."}
    }
    item["audit_adjudications"] = [
        {"criterion": "specialists", "agreed_outcome": "supervisor"}
    ]
    store.save(source)
    data = release.create(cohort["id"], [source["id"]], expected_count=3)
    record = data["records"][item["number"]]
    assert record["outcome"] == "supervisor"
    assert "answers are missing" not in record["supervisor_followup"]
