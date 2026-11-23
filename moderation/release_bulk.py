"""Explicit bulk release of reviewed feedback; never runs the checking engine."""

import copy
import io
import uuid
from collections import Counter

from django.core import signing
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from . import release, release_store, store

SALT = "moderation.feedback-bulk-preview.v1"
SCOPES = {"existing", "independent"}
REASONS = {
    "source": "Source evidence changed or the finalised record is no longer current.",
    "decision": "A specific final academic judgement is missing or unresolved.",
    "conflict": "Contradictory or ambiguous source decisions need resolution.",
    "wording": "Required student-facing wording is missing or unsuitable.",
    "awaiting": "Awaiting independent moderator feedback.",
}


def record_token(record, bundle):
    # Include staff edits and history as well as the live source. An old preview
    # must never approve a draft saved in another tab, even with the same outcome.
    return release.digest({"record": record, "source": release.digest(bundle)})


def classify(record, bundle):
    scope = "existing" if bundle["sources"] else "independent"
    row = {
        "number": record["number"],
        "name": record["name"],
        "source_batch": record["source_batch"],
        "scope": scope,
        "outcome": record["outcome"],
        "outcome_label": release.OUTCOMES.get(record["outcome"], "Decision required"),
        "feedback": release.format_feedback(record),
        "edited": record["status"] == "draft",
        "readiness": "attention",
        "reasons": [],
        "reason_codes": [],
        "token": record_token(record, bundle),
    }
    if release.release_valid(record, bundle):
        return {**row, "readiness": "finalised", "feedback": record["final_text"]}

    def problem(code, detail=None):
        if code not in row["reason_codes"]:
            row["reason_codes"].append(code)
        row["reasons"].append(detail or REASONS[code])

    if record["status"] == "finalised" or record[
        "source_fingerprint"
    ] != release.digest(bundle):
        problem("source")
    if scope == "independent" and record["status"] == "awaiting_feedback":
        problem("awaiting")
    else:
        proposal = release.propose(bundle)
        for gap in proposal.get("decision_gaps", []):
            conflict = any(
                term in gap.casefold()
                for term in (
                    "conflict",
                    "contradict",
                    "multiple assessment",
                    "ambiguous",
                )
            )
            problem("conflict" if conflict else "decision", gap)
        if proposal.get("wording_gaps") and record["status"] != "draft":
            for gap in proposal["wording_gaps"]:
                problem("wording", gap)
        if record["outcome"] not in release.OUTCOMES:
            if not proposal.get("decision_gaps"):
                problem("decision", "No final academic outcome is recorded.")
        else:
            try:
                release.validate_final(
                    {**record, "moderator": "Bulk readiness verification"}
                )
            except ValueError as error:
                problem("wording", str(error))
    if not row["reasons"]:
        row["readiness"] = "ready"
    return row


def overview(register, bundles, scope="existing"):
    if scope not in SCOPES:
        raise ValueError(
            "Choose existing moderation or independent moderator feedback."
        )
    all_rows = [classify(r, bundles[n]) for n, r in register["records"].items()]
    rows = sorted(
        (r for r in all_rows if r["scope"] == scope),
        key=lambda r: (r["name"].casefold(), r["number"]),
    )
    ready = [r for r in rows if r["readiness"] == "ready"]
    counts = Counter(r["readiness"] for r in rows)
    outcomes = Counter(r["outcome"] for r in ready)
    reasons = Counter(
        code
        for r in rows
        if r["readiness"] == "attention"
        for code in r["reason_codes"]
    )
    return {
        "scope": scope,
        "rows": rows,
        "ready": ready,
        "counts": {
            "total": len(rows),
            "ready": counts["ready"],
            "attention": counts["attention"],
            "finalised": counts["finalised"],
            "edited": sum(r["edited"] for r in ready),
        },
        "outcomes": {key: outcomes[key] for key in release.OUTCOMES},
        "reasons": [
            {"label": REASONS[code], "count": count} for code, count in reasons.items()
        ],
        "existing_count": sum(r["scope"] == "existing" for r in all_rows),
        "independent_count": sum(r["scope"] == "independent" for r in all_rows),
    }


def preview_manifest(register, state):
    return signing.dumps(
        {
            "register": register["id"],
            "operation": uuid.uuid4().hex,
            "scope": state["scope"],
            "records": {r["number"]: r["token"] for r in state["ready"]},
            "edited": state["counts"]["edited"],
        },
        salt=SALT,
        compress=True,
    )


def load_manifest(token):
    try:
        manifest = signing.loads(token, salt=SALT, max_age=7200)
        if manifest["scope"] not in SCOPES or not isinstance(manifest["records"], dict):
            raise ValueError
        return manifest
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "The feedback preview is invalid or expired. Open a fresh bulk preview."
        ) from error


def finalise(token, moderator, *, confirm=False, confirm_edits=False):
    if not confirm:
        raise ValueError(
            "Confirm that you have reviewed the proposed cohort feedback before finalising."
        )
    moderator = moderator.strip()
    if not moderator or len(moderator) > 200:
        raise ValueError(
            "Enter the finalising moderator's name (up to 200 characters)."
        )
    manifest = load_manifest(token)
    if manifest["edited"] and not confirm_edits:
        raise ValueError(
            "Explicitly confirm review of the staff-edited drafts in this preview."
        )
    # One lock and atomic register save: no half-completed operation. This reads
    # raw source files afresh and never updates moderation or validation records.
    with store.LOCK:
        register = release_store.load()
        if not register or manifest["register"] != register["id"]:
            raise ValueError("The release register changed. Open a fresh bulk preview.")
        previous = next(
            (
                h
                for h in register["history"]
                if h.get("action") == "bulk_finalise"
                and h.get("operation") == manifest["operation"]
            ),
            None,
        )
        if previous:
            return {**previous["result"], "repeated": True}
        if not manifest["records"]:
            raise ValueError("There is no ready feedback in this preview to finalise.")
        bundles = release.source_state(register)
        state = overview(register, bundles, manifest["scope"])
        current = {r["number"]: r for r in state["rows"]}
        result = {
            "operation": manifest["operation"],
            "at": store.now(),
            "moderator": moderator,
            "finalised": [],
            "excluded": [],
            "repeated": False,
        }
        for number, expected in manifest["records"].items():
            row = current.get(number)
            if not row or row["readiness"] != "ready" or row["token"] != expected:
                result["excluded"].append(
                    {
                        "number": number,
                        "name": (row or {}).get("name", ""),
                        "reason": "; ".join((row or {}).get("reasons", []))
                        or "The record changed or was already finalised after the preview. Open a fresh preview.",
                    }
                )
                continue
            record = register["records"][number]
            previous_record = copy.deepcopy(
                {k: v for k, v in record.items() if k != "history"}
            )
            # Keep every public field exactly as previewed, including staff edits.
            record.update(
                status="finalised",
                final_text=row["feedback"],
                generated_text=row["feedback"],
                finalised_at=result["at"],
                moderator=moderator,
            )
            record["history"].append(
                {
                    "at": result["at"],
                    "action": "finalise",
                    "method": "bulk",
                    "operation": result["operation"],
                    "moderator": moderator,
                    "previous": previous_record,
                }
            )
            result["finalised"].append(
                {"number": number, "name": row["name"], "outcome": row["outcome"]}
            )
        register["history"].append(
            {
                "at": result["at"],
                "action": "bulk_finalise",
                "operation": result["operation"],
                "scope": manifest["scope"],
                "result": copy.deepcopy(result),
            }
        )
        register.update(
            revision=uuid.uuid4().hex, updated=result["at"], last_finaliser=moderator
        )
        release_store.save(register)
        return result


def review_xlsx(rows):
    """A public-text-only review copy, deliberately distinct from release export."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Review before finalisation"
    sheet.append(
        [
            "Student number",
            "Student name",
            "Proposed outcome — not finalised",
            "Proposed student-facing feedback — review copy",
        ]
    )
    for row in rows:
        sheet.append(
            [row["number"], row["name"], row["outcome_label"], row["feedback"]]
        )
        for cell in sheet[sheet.max_row]:
            cell.data_type = "s"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="173D38")
    for column, width in [("A", 20), ("B", 30), ("C", 36), ("D", 110)]:
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()
