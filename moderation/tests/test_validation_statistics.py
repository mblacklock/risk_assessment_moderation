from moderation.criteria import CRITERIA, REMINDER_CHECKS
from moderation.validation import check_statistics, summarise_cases


def case(human, tool, source="Rule", version="v1", model="Not applicable"):
    return {
        "id": "identity",
        "human_status": human,
        "tool_status": tool,
        "same": human == tool,
        "source": source,
        "version": version,
        "model": model,
    }


def test_agreement_denominator_and_correction_comparisons_keep_uncertainty_separate():
    cases = [
        case("complete", "complete"),
        case("issue", "issue"),
        case("supervisor", "supervisor"),
        case("issue", "complete"),
        case("issue", "supervisor"),
        case("complete", "issue"),
        case("supervisor", "issue"),
        case("complete", "supervisor"),
        case("supervisor", "complete"),
        case("issue", "review"),
        case("review", "issue"),
        case("review", "unable"),
        case("skipped", "complete"),
        case("complete", "skipped"),
    ]
    result = summarise_cases(cases)
    assert result["total"] == 14
    assert result["compared"] == 9 and result["agreed"] == 3
    assert result["agreement"] == "3/9 (33.3%)"
    assert result["possible_missed"] == 2
    assert result["possible_extra"] == 2
    assert result["followup_differences"] == 2
    assert result["tool_uncertain"] == 2
    assert result["audit_uncertain"] == 2
    assert result["skipped"] == 2


def test_no_definite_pairs_does_not_report_perfect_agreement():
    result = summarise_cases([case("review", "review"), case("issue", "unable")])
    assert result["agreement"] == "No definite pairs"
    assert result["agreed"] == result["compared"] == 0
    assert result["possible_missed"] == result["possible_extra"] == 0


def test_tool_coverage_is_independent_of_auditor_certainty():
    result = summarise_cases(
        [case("complete", "complete")] * 18
        + [case("review", "issue"), case("issue", "review")]
    )
    assert result["agreement"] == "18/18 (100.0%)"
    assert result["tool_definite"] == 19
    assert result["coverage"] == "19/20 (95.0%)"
    assert result["tool_uncertain"] == 1
    assert summarise_cases([])["coverage"] == "No audited cases"


def test_statistics_break_down_original_sources_versions_and_models_and_retain_cases():
    comparisons = [
        {"submission": {"id": "one"}, "rows": [case("complete", "complete")]},
        {
            "submission": {"id": "two"},
            "rows": [case("issue", "complete", "AI", "v2", "model-a")],
        },
        {
            "submission": {"id": "three"},
            "rows": [case("complete", "issue", "AI", "v2", "model-b")],
        },
        {"submission": {"id": "four"}, "rows": [case("issue", "review", version="")]},
    ]
    stats = check_statistics(comparisons)
    assert [row["id"] for row in stats] == [
        key for key, _, _ in CRITERIA if key not in REMINDER_CHECKS
    ]
    identity = next(row for row in stats if row["id"] == "identity")
    assert identity["total"] == 4 and identity["compared"] == 3
    assert identity["mixed_versions"] and len(identity["strata"]) == 4
    assert identity["unknown_versions"] == 1
    assert identity["possible_missed"] == identity["possible_extra"] == 1
    assert [row["submission"]["id"] for row in identity["cases"]] == [
        "one",
        "two",
        "three",
        "four",
    ]
