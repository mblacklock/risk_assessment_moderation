# ruff: noqa: F811
import copy

from moderation import release
from moderation.criteria import overall
from moderation.feedback import feedback_items, feedback_readiness, feedback_signature
from moderation.tests.test_feedback import (
    acknowledge,
    feedback_review,  # noqa: F401
    finding,
    generate,
)  # noqa: F401
from moderation.tests.test_release import ready_workspace  # noqa: F401


def test_admin_does_not_block_feedback_but_remains_a_moderation_issue(feedback_review):
    item = feedback_review["submissions"][0]
    finding(feedback_review, "admin").update(
        status="issue", message="Administrative questions unanswered"
    )
    original = copy.deepcopy(item["checks"])
    assert feedback_readiness(feedback_review, item)[0]
    assert feedback_items(item) == []
    assert overall(item["checks"]) == "issue"
    assert item["checks"] == original


def test_release_omits_admin_from_wording_and_outcome_preserving_source(
    ready_workspace,
):
    data, _, _ = ready_workspace
    bundle = release.source_state(data)["w10000000"]
    check = next(c for c in bundle["sources"][0]["checks"] if c["id"] == "admin")
    check.update(
        status="issue",
        decision="issue",
        message="Administrative question(s) 1, 2 unanswered.",
    )
    original = copy.deepcopy(bundle)
    proposal = release.propose(bundle)
    assert proposal["outcome"] == "complete"
    assert not proposal["student_corrections"] and not proposal["issues"]
    decision = next(d for d in proposal["decisions"] if d["criterion"] == "admin")
    assert decision["proposed"] == "issue" and decision["feedback_excluded"]
    assert bundle == original


def test_other_student_corrections_still_fail_and_admin_gaps_do_not_block(
    ready_workspace,
):
    data, _, _ = ready_workspace
    bundle = release.source_state(data)["w10000000"]
    checks = {c["id"]: c for c in bundle["sources"][0]["checks"]}
    checks["admin"].update(status="moderator")
    checks["identity"].update(status="issue", decision="issue")
    proposal = release.propose(bundle)
    assert proposal["outcome"] == "issue" and not proposal["decision_gaps"]
    assert "own full name" in proposal["student_corrections"]
    assert "Generic" not in release.format_feedback(proposal)


def test_old_final_feedback_is_held_until_explicitly_updated_for_new_policy(
    ready_workspace,
):
    data, _, _ = ready_workspace
    record = copy.deepcopy(data["records"]["w10000000"])
    record.pop("feedback_exclusions")
    record.update(
        status="finalised",
        final_text="Old final feedback including administrative questions",
    )
    original = copy.deepcopy(record)
    bundle = release.source_state(data)["w10000000"]
    assert not release.release_valid(record, bundle)
    assert record == original


def test_format_two_upgrade_preserves_other_edited_feedback_and_history(
    feedback_review, client
):
    from moderation import store

    r = feedback_review
    finding(r, "admin").update(
        status="issue", message="Administrative question(s) 1, 2 unanswered."
    )
    ratings = finding(r, "ratings")
    ratings.update(
        status="issue", message="Row 1: enter a numeric value for Final Result."
    )
    acknowledge(ratings)
    item = r["submissions"][0]
    old = {
        "id": "legacy-format-two",
        "format_version": 2,
        "signature": feedback_signature(item),
        "wording": {
            "admin": "Old administrative requirement",
            "ratings": "Please enter the final score for the workstation row.",
        },
        "text": "Old student feedback",
    }
    item.update(elp_feedback=old, feedback_history=[copy.deepcopy(old)])
    store.save(r)
    assert generate(client, r).status_code == 302
    updated = store.load(r["id"])["submissions"][0]
    assert "workstation row" in updated["elp_feedback"]["text"]
    assert "administrative requirement" not in updated["elp_feedback"]["text"]
    assert updated["feedback_history"][0] == old
