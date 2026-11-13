import csv
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .criteria import CRITERIA, STATUSES, effective_status, overall


def safe(value):
    value = str(value or "")
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@"))
        or value.startswith(("\t", "\r"))
        else value
    )


def summary_rows(review):
    yield [
        "Student number",
        "Student name",
        "Submitted",
        "Outcome",
        "AI checks",
        "Files",
    ] + [label for _, label, _ in CRITERIA]
    for submission in review["submissions"]:
        checks = {c["id"]: c for c in submission["checks"]}
        yield [
            submission["number"],
            submission["name"],
            submission["submitted"],
            STATUSES[overall(submission["checks"])] if checks else "Pending",
            submission["ai"]["state"],
            "; ".join(f["name"] for f in submission["files"]),
        ] + [
            STATUSES[effective_status(checks[key])] if key in checks else "Pending"
            for key, _, _ in CRITERIA
        ]


def csv_bytes(review):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerows([[safe(cell) for cell in row] for row in summary_rows(review)])
    return output.getvalue().encode("utf-8-sig")


def xlsx_bytes(review):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Snapshot"
    for row in summary_rows(review):
        sheet.append([safe(cell) for cell in row])
    details = workbook.create_sheet("Findings and decisions")
    details.append(
        [
            "Student number",
            "Student name",
            "Category",
            "Criterion",
            "Automated result",
            "Final result",
            "Method",
            "Explanation",
            "Evidence",
            "Moderator note",
            "Decision time",
        ]
    )
    for submission in review["submissions"]:
        for check in submission["checks"]:
            details.append(
                [
                    safe(cell)
                    for cell in [
                        submission["number"],
                        submission["name"],
                        check["category"],
                        check["label"],
                        STATUSES[check["status"]],
                        STATUSES[effective_status(check)],
                        check["source"],
                        check["message"],
                        "\n".join(
                            e["location"] + ": " + e["text"] for e in check["evidence"]
                        ),
                        check.get("note", ""),
                        check.get("decided_at", ""),
                    ]
                ]
            )
    for worksheet in workbook:
        worksheet.freeze_panes = "C2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="173D38")
        for column in worksheet.columns:
            worksheet.column_dimensions[column[0].column_letter].width = 26
        worksheet.column_dimensions["A"].width = 18
        worksheet.column_dimensions["B"].width = 30
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
