import json

from moderation import release, release_store, store
from moderation.review_policy import checking_version
from moderation.tests.test_release import fields, workspace


def setup_policy(settings, tmp_path, version=None, kind="moderation"):
    cohort, source = workspace(settings, tmp_path)
    source["review_mode"] = "routine"
    check = source["submissions"][0]["checks"][1]
    assert check["id"] == "identity"
    check.update(status="issue", engine_version=version or checking_version())
    for item in source["submissions"]:
        item["state"] = "done"
    store.save(source)
    policy = {
        "schema": 1,
        "approvals": {
            "identity:Rule": {
                "version": checking_version(),
                "reference": "Synthetic validation evidence",
            }
        },
    }
    path = settings.REVIEW_ROOT / "global-approvals.json"
    path.write_text(json.dumps(policy))
    return release.create(
        cohort["id"],
        [source["id"]],
        expected_count=3,
        source_kinds={source["id"]: kind},
    ), path


def test_routine_feedback_reuses_version_matched_approval(settings, tmp_path):
    data, _ = setup_policy(settings, tmp_path)
    record = data["records"]["w10000000"]
    assert record["outcome"] == "issue"
    assert not record["proposal"]["decision_gaps"]
    assert "own full name" in record["student_corrections"]
    source = record["source_evidence"]["sources"][0]
    assert source["automatic_acceptances"]["identity"]["approval"]["reference"]
    decision = next(
        d for d in record["proposal"]["decisions"] if d["criterion"] == "identity"
    )
    assert "routine moderation policy" in decision["origin"]


def test_unknown_checker_version_still_requires_a_decision(settings, tmp_path):
    data, _ = setup_policy(settings, tmp_path, version="Unknown version")
    assert data["records"]["w10000000"]["proposal"]["decision_gaps"]


def test_validation_audits_are_not_replaced_by_routine_approvals(settings, tmp_path):
    data, _ = setup_policy(settings, tmp_path, kind="validation")
    assert data["records"]["w10000000"]["proposal"]["decision_gaps"]


def test_withdrawn_approval_invalidates_automatic_release(settings, tmp_path):
    data, path = setup_policy(settings, tmp_path)
    number = "w10000000"
    record = data["records"][number]
    data = release.save_record(
        data["revision"],
        number,
        fields(**{k: record[k] for k in release.PUBLIC_FIELDS}),
        finalise=True,
        confirm=True,
        source_token=release.digest(release.source_state(data)[number]),
    )
    path.write_text(json.dumps({"schema": 1, "approvals": {}}))
    bundle = release.source_state(data)[number]
    assert not release.release_valid(data["records"][number], bundle)
    assert release.propose(bundle)["decision_gaps"]
    assert release_store.load()["records"][number]["status"] == "finalised"
