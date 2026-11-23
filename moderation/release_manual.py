"""Read-only, explicitly linked original moderator spreadsheets."""

import hashlib
from pathlib import Path

from openpyxl import load_workbook


def read_records(path):
    path = Path(path)
    fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {}
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in workbook:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, ())
            columns = {
                str(v).strip().casefold(): i
                for i, v in enumerate(header)
                if v is not None
            }
            if not {"student number", "pass/fail", "feedback"}.issubset(columns):
                continue
            for row_number, row in enumerate(rows, 2):

                def value(label):
                    index = columns[label]
                    return (
                        str(row[index]).strip()
                        if index < len(row) and row[index] is not None
                        else ""
                    )

                number, outcome, feedback = (
                    value("student number").casefold(),
                    value("pass/fail"),
                    value("feedback"),
                )
                if not number or not (outcome or feedback):
                    continue
                if number in result:
                    raise ValueError(
                        "Duplicate populated manual moderation records must be resolved before reconciliation."
                    )
                result[number] = {
                    "path": str(path),
                    "sheet": sheet.title,
                    "row": row_number,
                    "outcome": {"pass": "complete", "fail": "issue"}.get(
                        outcome.casefold()
                    ),
                    "outcome_original": outcome,
                    "feedback": feedback,
                    "file_sha256": fingerprint,
                    "role": "Original independent moderation, before subsequent agreed interpretations",
                }
    finally:
        workbook.close()
    return result
