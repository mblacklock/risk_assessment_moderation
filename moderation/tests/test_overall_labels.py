import io

import pytest
from django.http import QueryDict
from openpyxl import load_workbook

from moderation.criteria import OVERALL_LABELS, STATUSES, overall, result
from moderation.exports import summary_rows, xlsx_bytes
from moderation.views import grid_context


@pytest.mark.parametrize(
    ("statuses", "label"),
    [
        (["complete"], "Pass"),
        (["complete", "supervisor"], "Pass — supervisor follow-up"),
        (["supervisor", "issue"], "Fail — correction required"),
        (["review", "supervisor"], "Needs moderator review"),
        (["unable"], "Needs moderator review"),
        (["moderator"], "Needs moderator review"),
    ],
)
def test_overall_grade_labels_preserve_check_level_outcomes(statuses, label):
    checks = [result("readable", status, "Synthetic finding") for status in statuses]
    assert OVERALL_LABELS[overall(checks)] == label
    assert STATUSES["complete"] == "Complete"
    assert STATUSES["supervisor"] == "Supervisor check"
    assert STATUSES["issue"] == "Issue found"


def test_summary_uses_overall_grades_but_finding_exports_keep_check_labels():
    item = {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Synthetic Student",
        "number": "w12345678",
        "submitted": "",
        "files": [],
        "ai": {"state": "off"},
        "state": "done",
        "checks": [
            result("specialists", "supervisor", "Supporting assessment follow-up")
        ],
    }
    review = {
        "id": "00000000-0000-0000-0000-000000000002",
        "submissions": [item],
        "state": "done",
        "use_ai": False,
    }
    rows = list(summary_rows(review))
    assert rows[1][3] == "Pass — supervisor follow-up"
    assert rows[1][rows[0].index("Specialist assessments")] == "Supervisor check"
    workbook = load_workbook(io.BytesIO(xlsx_bytes(review)))
    assert workbook["Snapshot"]["D2"].value == "Pass — supervisor follow-up"
    assert workbook["Findings and decisions"]["F2"].value == "Supervisor check"
    context = grid_context(review, QueryDict())
    assert context["rows"][0]["outcome_label"] == "Pass — supervisor follow-up"
    assert context["overall_totals"]["supervisor"] == 1
    item["checks"].append(result("location", "issue", "Workspace missing"))
    context = grid_context(review, QueryDict())
    assert context["overall_totals"]["supervisor"] == 0
    assert context["overall_totals"]["issue"] == 1
