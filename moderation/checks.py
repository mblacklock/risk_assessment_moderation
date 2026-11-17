"""Deterministic completion checks. Ambiguity is kept for human review."""

import re

from .criteria import CRITERIA, WORD_LIMIT_REMINDER, result
from .documents import highlighted_yes_no, normalise, word_limit_guidance

LABELS = (
    r"Student Name|Supervisor Name|Project Title|Assessment Title|Assessor|"
    r"Area/Activity|Location|Job Title|Signature|Student sign|Supervisor sign|Date|"
    r"Ethics application|Project Aims|Research Activities|Ethical, Environmental|"
    r"Research Data|Data Management|Ethics, Health|Physical Risk|Supervisor Statement"
)
SPECIALISTS = [
    "Manual Handling",
    "COSHH",
    "PUWER",
    "DSEAR",
    "Young Persons",
    "New & Expectant Mothers",
]
NARRATIVES = [
    "Project Aims and Objectives",
    "Research Activities",
    "Ethical, Environmental, Societal Impact",
    "Research Data Management",
    "Research Data Storage",
]
BAND = r"(?:low|medium|high|[LMH])"
BAND_LABEL = rf"(?:\(?\s*{BAND}\s*\)?|\[\s*{BAND}\s*\])"
SECTION_HEADING = re.compile(
    r"^(?:Risk (?:Rating|Assessment Template)|Item No\.?|"
    r"Control Measures Required|Persons at risk|Severity|Likelihood|Final Result)\b",
    re.I,
)


def assessor_matches(assessor, submitter):
    """Allow inserted middle names while retaining the full submitted surname."""
    if normalise(assessor) == normalise(submitter) and normalise(assessor):
        return True
    # Keep hyphenated/compound names as separate meaningful tokens, never initials.
    actual = re.findall(r"[^\W\d_]+", assessor.casefold())
    expected = re.findall(r"[^\W\d_]+", submitter.casefold())
    return (
        len(expected) >= 2
        and len(actual) > len(expected)
        and len(expected[0]) > 1
        and actual[0] == expected[0]
        and actual[-(len(expected) - 1) :] == expected[1:]
    )


def numeric_rating(value):
    """Read the entered score, including the result of an explicit calculation."""
    value = value.strip()
    if "=" in value:
        calculation = re.fullmatch(
            r"\d+(?:\.\d+)?\s*[x×*]\s*\d+(?:\.\d+)?\s*=\s*(.+)", value, re.I
        )
        if calculation is None:
            return None
        value = calculation[1].strip()
    match = re.fullmatch(
        rf"(?:(?P<prefix>{BAND_LABEL})\s*(?:[–—-]\s*)?)?"
        rf"(?P<score>\d+(?:\.\d+)?)\s*(?P<suffix>{BAND_LABEL})?",
        value,
        re.I,
    )
    if not match or (match["prefix"] and match["suffix"]):
        return None
    return float(match["score"])


def rating_entries(value):
    """Each nonblank line is one entered score; never pick just the last result."""
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    entries = []
    for line in lines:
        # A wrapped band annotates the preceding score, never another score.
        if (
            entries
            and re.fullmatch(BAND_LABEL, line, re.I)
            and re.fullmatch(
                r"(?:\d+(?:\.\d+)?\s*[x×*]\s*)?"
                r"\d+(?:\.\d+)?\s*(?:=\s*\d+(?:\.\d+)?)?",
                entries[-1],
            )
        ):
            entries[-1] += " " + line
        else:
            entries.append(line)
    scores = [numeric_rating(entry) for entry in entries]
    return scores if entries and all(score is not None for score in scores) else None


def unused_risk_row(row):
    """Only an explicitly unused row with no substantive entries may be excluded."""
    values = [normalise(cell) for cell in row[1:]]
    return any(values) and all(
        value in {"", "na", "notapplicable", "unused"} for value in values
    )


def rating_checks(rows):
    missing, ambiguous, mismatched, unchanged = [], [], [], []
    missing_details = []
    extracts = []
    comparisons = 0
    assessed_rows = 0
    unused = []
    technical_defects = []
    for index, row in enumerate(rows, 1):
        if unused_risk_row(row):
            unused.append(str(index))
            continue
        assessed_rows += 1
        cells = [row[column] if len(row) > column else "" for column in (4, 5, 6, 8)]
        extracts.append(
            {
                "location": f"Risk row {index}",
                "text": " | ".join(
                    f"{label}: {value}"
                    for label, value in zip(
                        ("Severity", "Likelihood", "Initial scores", "Final scores"),
                        cells,
                        strict=True,
                    )
                ),
            }
        )
        missing_fields = [
            label
            for label, cell in zip(
                (
                    "Severity",
                    "Likelihood",
                    "Risk Rating (initial score)",
                    "Final Result (post-control score)",
                ),
                cells,
                strict=True,
            )
            if not re.search(r"\d", cell)
        ]
        if missing_fields:
            missing.append(str(index))
            missing_details.append(
                f"Row {index}: enter a numeric value for "
                + ", ".join(missing_fields)
                + "."
            )
            continue
        values = [rating_entries(cell) for cell in cells]
        if any(value is None for value in values):
            ambiguous.append(str(index))
            for label, cell in zip(
                ("Severity", "Likelihood", "Initial rating", "Final Result"),
                cells,
                strict=True,
            ):
                if re.search(r"\d\s*[–—-]\s*\d", cell):
                    technical_defects.append(
                        f"Row {index}, {label}: a range was entered instead of one score ({cell.strip()})."
                    )
                elif re.search(r"\d\s*\(\s*\d\s*\)", cell):
                    technical_defects.append(
                        f"Row {index}, {label}: invalid band annotation ({cell.strip()})."
                    )
                elif re.search(r"\d\s*[x×*]\s*\d", cell, re.I) and "=" not in cell:
                    technical_defects.append(
                        f"Row {index}, {label}: a multiplication expression has no entered result ({cell.strip()})."
                    )
            continue
        counts = [len(value) for value in values]
        if len(set(counts)) != 1:
            mismatched.append(
                f"Row {index}: {counts[0]} severity, {counts[1]} likelihood, {counts[2]} initial and {counts[3]} final entries"
            )
            continue
        for entry, (initial, final) in enumerate(
            zip(values[2], values[3], strict=True), 1
        ):
            comparisons += 1
            if final >= initial:
                label = (
                    f"Row {index}" if counts[2] == 1 else f"Row {index}, entry {entry}"
                )
                unchanged.append(f"{label}: initial {initial:g}, final {final:g}")
    completion_notes = []
    if technical_defects:
        completion_notes.append(
            "Technical entry defects need moderator judgement; do not silently repair the entries. "
            + " ".join(technical_defects)
        )
    if unused:
        completion_notes.append(
            "No numeric ratings required for wholly unused/N/A rows: "
            + ", ".join(unused)
            + "."
        )
    if missing:
        completion_notes.append(
            " ".join(missing_details)
            + " Complete the missing rating fields in each affected row. Final Result records the risk remaining after the listed controls; a final score alone is sufficient and a multiplication expression is optional."
        )
    if mismatched:
        completion_notes.append(
            "Rating entry counts do not match. "
            + "; ".join(mismatched)
            + ". Correct or clarify which ratings belong together."
        )
    if ambiguous:
        completion_notes.append(
            "Multiple or unclear rating entries could not be read reliably in rows: "
            + ", ".join(ambiguous)
            + ". Check the original and the pairing of ratings manually."
        )
    ratings = result(
        "ratings",
        "issue"
        if missing or mismatched
        else "review"
        if ambiguous
        else "complete"
        if assessed_rows
        else "skipped"
        if unused
        else "unable",
        " ".join(completion_notes)
        if completion_notes
        else "Numeric severity, likelihood, initial rating and final result are present with matching entry counts."
        if rows
        else "No readable ratings found.",
        extracts,
    )
    if technical_defects:
        ratings["technical_defects"] = technical_defects
    notes = []
    if unchanged:
        notes.append(
            "Final ratings must be lower than initial ratings. "
            + "; ".join(unchanged)
            + "."
        )
    if mismatched:
        notes.append(
            "Rating entry counts do not match. "
            + "; ".join(mismatched)
            + ". Correct or clarify the entries before comparing these rows."
        )
    if missing:
        notes.append(
            "Comparison skipped for rows: "
            + ", ".join(missing)
            + ". Numeric values are missing or unreadable. Complete the fields identified by Risk ratings completed before comparing these scores."
        )
    if ambiguous:
        notes.append(
            "Rating entries or their pairing need manual review in rows: "
            + ", ".join(ambiguous)
            + "."
        )
    if comparisons:
        notes.append(
            f"Compared {comparisons} initial/final score pairs in listed order; substantive hazard/control alignment remains for the supervisor."
        )
    reduction = result(
        "risk_reduction",
        "issue"
        if unchanged or mismatched
        else "review"
        if ambiguous
        else "skipped"
        if missing
        else "unable"
        if not assessed_rows and not unused
        else "skipped"
        if not assessed_rows
        else "complete",
        " ".join(notes)
        if notes
        else "No assessed risk rows to compare; wholly unused/N/A rows were excluded."
        if unused
        else "No readable risk ratings to compare.",
        extracts,
    )
    if reduction["status"] == "skipped" and missing:
        reduction["blocked_by"] = "ratings"
    if reduction["status"] == "complete":
        reduction["message"] = (
            "Final ratings are lower than the entered initial ratings in every matched entry. "
            + reduction["message"]
        )
    return ratings, reduction


def field(paragraphs, label):
    separator = (
        r"(?:\s*:\s*|\s+(?=\d))"
        if label == "Date"
        else r"\s*:?\s*"
        if label.endswith("Name")
        else r"\s*:\s*"
    )
    pattern = re.compile(r"(?<!\w)" + label + separator + r"(.*)", re.I)
    for index, p in enumerate(paragraphs):
        if p.get("floating_text_unassociated"):
            continue
        match = pattern.search(p["text"])
        if not match:
            continue
        value = re.split(
            r"(?:^|\s+)(?:(?:" + LABELS + r")\s*:|Date\s+(?=\d))", match[1], flags=re.I
        )[0]
        if value.strip():
            return value.strip(), p
        if index + 1 < len(paragraphs):
            following = paragraphs[index + 1]
            text = following["text"]
            if (
                text
                and not following.get("floating_text_unassociated")
                and not re.match(r"^(?:" + LABELS + r")\b", text, re.I)
                and not SECTION_HEADING.match(text.strip())
                and not text.startswith(
                    ("☐", "☒", "Please", "To be completed", "NB", "I consider")
                )
            ):
                return text.strip(), following
        return "", p
    return "", None


def evidence(*paragraphs):
    extracts = []
    for p in paragraphs:
        if p is None:
            continue
        extract = {"location": p.get("ref", ""), "text": p["text"][:1800]}
        choice = highlighted_yes_no(p)
        if choice:
            extract["selection_note"] = (
                "Highlight selection is ambiguous; inspect the original."
                if choice == "ambiguous"
                else (
                    "Bold choice: "
                    if p.get("bold_ranges") and not p.get("highlighted_ranges")
                    else "Highlighted choice: "
                )
                + choice.title()
            )
        if p.get("images"):
            extract["images"] = list(dict.fromkeys(p["images"]))
        if p.get("textbox_association"):
            extract["text"] += (
                " [Textbox placement: " + p["textbox_association"]["placement"] + "]"
            )
        if p.get("pdf_selection_note"):
            extract["selection_note"] = p["pdf_selection_note"]
        if extract not in extracts:
            extracts.append(extract)
    return extracts


def area_activity_check(value, paragraph):
    """Only presence is deterministic; AI assesses the meaning of every entry."""
    return result(
        "location",
        "review" if value.strip() else "issue",
        "Area/Activity needs a content assessment: it must identify a clear "
        "manufacturing process, test procedure or named room for physical work. A dedicated Location field can identify the workspace. A clear computer-based activity description is sufficient for its computer-work RA section. Assess each section with its actual RA and ethics activities. Review manually if AI is unavailable."
        if value.strip()
        else "Area/Activity is missing. Specify a clear manufacturing process, "
        "test procedure or named room for physical work, or a clear computer-based activity for a computer-work section. A dedicated Location field may identify the workspace.",
        evidence(paragraph),
    )


def section(paragraphs, start, stop):
    first = next((i for i, p in enumerate(paragraphs) if start in p["text"]), None)
    if first is None:
        return []
    last = next(
        (i for i in range(first + 1, len(paragraphs)) if stop in paragraphs[i]["text"]),
        len(paragraphs),
    )
    return paragraphs[first:last]


def selection(p, position=0):
    if not p:
        return None
    if len(p["states"]) > position:
        return p["states"][position]
    glyphs = re.findall(r"[☐☒☑]", p["text"])
    if len(glyphs) > position:
        return glyphs[position] in {"☒", "☑"}
    return None


def combine_signoff(key, scope, name_label, date=None, name_required=True):
    name, name_p = field(scope, name_label)
    if not name and name_required:
        # A generic label is meaningful only inside the already selected role section.
        generic_start = next(
            (
                i
                for i, p in enumerate(scope)
                if re.match(r"^\s*Name\s*:", p["text"], re.I)
            ),
            None,
        )
        if generic_start is not None:
            name, name_p = field(scope[generic_start:], "Name")
    title, title_p = field(scope, "Job Title")
    signature, sig_p = field(scope, "Signature")
    if not sig_p:
        signature, sig_p = field(scope, name_label.replace("Name", "sign"))
    date_value, date_p = date if date is not None else field(scope, "Date")
    has_image = bool(sig_p and sig_p["images"])
    image_paragraphs = []
    if sig_p:
        idx = scope.index(sig_p)
        if idx > 0 and name_required and name_p and title_p:
            preceding = scope[idx - 1]
            if (
                preceding["images"]
                and not preceding["text"].strip()
                and scope.index(name_p) < idx - 1
                and scope.index(title_p) < idx - 1
            ):
                has_image = True
                image_paragraphs.append(preceding)
        for p in scope[idx + 1 : idx + 3]:
            if re.match(r"^(Supervisor sign|Student sign|Date|NB)\b", p["text"], re.I):
                break
            has_image = has_image or bool(p["images"])
            if p["images"]:
                image_paragraphs.append(p)
    missing = []
    if name_required and not name:
        missing.append("name")
    if name_required and not title:
        missing.append("job title")
    if not signature and not has_image:
        missing.append("signature")
    if not date_value:
        missing.append("date")
    check = result(
        key,
        "issue" if missing else "complete",
        "Missing: " + ", ".join(missing) + "."
        if missing
        else "Required sign-off fields are present, including an embedded signature image. "
        "Signature authenticity is not assessed."
        if has_image
        else "Required sign-off fields are present. Signature authenticity is not assessed.",
        evidence(name_p, title_p, sig_p, *image_paragraphs, date_p),
    )
    check["signature_presence"] = (
        "image"
        if has_image
        else "typed"
        if signature
        else "blank"
        if sig_p and sig_p.get("signature_field_blank")
        else "unknown"
    )
    if "signature" in missing and sig_p and sig_p.get("signature_drawing_uncertain"):
        check.update(
            status="review",
            message="A drawing is present near the signature field, but its placement or format could not be verified. Inspect the original; signature presence is uncertain.",
        )
    if any(p.get("floating_text_unassociated") for p in scope) and any(
        item in missing for item in ("name", "job title")
    ):
        check.update(
            status="review",
            message="Floating textbox text could not be associated reliably with the sign-off fields. Inspect the original before treating name/job title as missing.",
        )
        check["evidence"] += evidence(
            *(p for p in scope if p.get("floating_text_unassociated"))
        )
    return check


def check_documents(documents, student):
    paragraphs, tables = [], []
    is_pdf = False
    for number, doc in enumerate(documents, 1):
        is_pdf |= doc["kind"] == "pdf"
        for idx, p in enumerate(doc["paragraphs"], 1):
            paragraphs.append({**p, "ref": f"Document {number}, paragraph {idx}"})
        tables.extend(doc["tables"])
    # Scope by document rather than concatenation: risk and ethics may be separate files.
    risk, ethics = [], []
    for doc in documents:
        doc_ps = [
            p
            for p in paragraphs
            if p["ref"].startswith(f"Document {documents.index(doc) + 1},")
        ]
        split = next(
            (
                i
                for i, p in enumerate(doc_ps)
                if re.search(
                    r"(?:Student Project Ethics Approval Form|^Ethics (?:approval|application|assessment|form))",
                    p["text"],
                    re.I,
                )
            ),
            len(doc_ps),
        )
        ra_start = next(
            (
                i
                for i, p in enumerate(doc_ps[:split])
                if re.match(r"Date(?:\s*:|\s+\d)", p["text"], re.I)
            ),
            0,
        )
        risk.extend(doc_ps[ra_start:split])
        ethics.extend(doc_ps[split:])
    checks = {}

    def add(key, status, message, *ps):
        checks[key] = result(key, status, message, evidence(*ps))

    readable = sum(len(p["text"]) for p in paragraphs) > 150
    add(
        "readable",
        "complete" if readable else "unable",
        "Text extracted from all documents."
        if readable
        else "Very little readable text. A scan or unsupported form needs manual review.",
    )
    assessor, assessor_p = field(risk, "Assessor")
    if student["name"] == "Identity needs review":
        add(
            "identity",
            "review",
            "No reliable submitter name in ZIP metadata.",
            assessor_p,
        )
    else:
        actual = normalise(assessor)
        if assessor_matches(assessor, student["name"]):
            add(
                "identity",
                "complete",
                "Assessor matches the submitting student.",
                assessor_p,
            )
        elif actual and set(re.findall(r"[a-z]+", assessor.lower())) & set(
            re.findall(r"[a-z]+", student["name"].lower())
        ):
            add(
                "identity",
                "review",
                "Partial name match; confirm the assessor is the student.",
                assessor_p,
            )
        else:
            add("identity", "issue", f"Assessor must be {student['name']}.", assessor_p)
    title, title_p = field(risk, "Assessment Title")
    ra_date, ra_date_p = field(risk, "Date")
    add(
        "project",
        "complete" if title and ra_date else "issue",
        "Assessment title and date present."
        if title and ra_date
        else "Assessment title or date is missing.",
        title_p,
        ra_date_p,
    )
    location, location_p = field(risk, "Area/Activity")
    risk_sections = []
    for doc_number, doc in enumerate(documents, 1):
        doc_risk = [p for p in risk if p["ref"].startswith(f"Document {doc_number},")]
        starts = [
            i
            for i, p in enumerate(doc_risk)
            if re.match(r"^Area\s*/\s*Activity\s*:", p["text"], re.I)
        ]
        if not starts and any(
            re.match(r"^Location\s*:", p["text"], re.I) for p in doc_risk
        ):
            starts = [0]
        if (
            not starts
            and doc_risk
            and any(
                any("hazard" in cell.casefold() for cell in row)
                and any("severity" in cell.casefold() for cell in row)
                for table in doc["tables"]
                for row in table
            )
        ):
            starts = [0]
        for i in range(1, len(starts)):
            while starts[i] > starts[i - 1] + 1 and re.match(
                r"^(?:Location|Date|Assessment Title|Assessor)\s*:",
                doc_risk[starts[i] - 1]["text"],
                re.I,
            ):
                starts[i] -= 1
        for index, start in enumerate(starts):
            scope = doc_risk[
                0 if index == 0 else start : starts[index + 1]
                if index + 1 < len(starts)
                else len(doc_risk)
            ]
            area, area_p = field(scope, "Area/Activity")
            workspace, workspace_p = field(scope, "Location")
            risk_sections.append(
                {
                    "document": doc_number,
                    "section": index + 1,
                    "area_activity": area,
                    "location": workspace,
                    "evidence": evidence(area_p, workspace_p),
                    "risk_rows": [],
                    "start": scope[0].get("source_index"),
                    "page": scope[0].get("page"),
                    "association_uncertain": False,
                }
            )
    if risk_sections:
        location = "\n".join(
            s["area_activity"] + ("; " + s["location"] if s["location"] else "")
            for s in risk_sections
        ).strip()
    checks["location"] = area_activity_check(location, location_p)
    if risk_sections:
        checks["location"]["evidence"] = [
            e for s in risk_sections for e in s["evidence"]
        ]
        if any(not (s["area_activity"] or s["location"]) for s in risk_sections):
            checks["location"].update(
                status="issue",
                message="An RA section has no Area/Activity or dedicated Location entry. Complete the missing section's information.",
            )

    risk_rows = []
    continuation_evidence = []
    for doc_number, doc in enumerate(documents, 1):
        for table_index, table in enumerate(doc["tables"]):
            header = next(
                (
                    i
                    for i, row in enumerate(table)
                    if any("Hazard" in cell for cell in row)
                    and any("Severity" in cell for cell in row)
                ),
                None,
            )
            if header is not None:
                rows = []
                activity = ""
                parent_row = None
                for row_index, source_row in enumerate(table[header + 1 :], header + 1):
                    row = list(source_row)
                    if len(row) < 8 or not any(cell.strip() for cell in row[1:]):
                        activity = ""
                        continue
                    merges = doc.get("continuation_cells", [])
                    merged_activity = bool(
                        merges
                        and table_index < len(merges)
                        and row_index < len(merges[table_index])
                        and 1 in merges[table_index][row_index]
                    )
                    if (
                        not row[1].strip()
                        and activity
                        and row[2].strip()
                        and (merged_activity or not row[0].strip())
                    ):
                        row[1] = activity
                        continuation_evidence.append(
                            {
                                "location": f"Risk row {len(risk_rows) + len(rows) + 1}",
                                "text": f"Activity shared from Risk row {parent_row}: {activity}. Association established within the same table by a merged cell or unnumbered continuation hazard.",
                            }
                        )
                    elif not row[1].strip():
                        activity = ""
                    if row[1].strip():
                        if source_row[1].strip():
                            parent_row = len(risk_rows) + len(rows) + 1
                        activity = row[1]
                    rows.append(row)
                risk_rows.extend(rows)
                contexts = [s for s in risk_sections if s["document"] == doc_number]
                position = doc.get("table_positions", [None] * len(doc["tables"]))[
                    table_index
                ]
                candidates = [
                    s
                    for s in contexts
                    if position is not None
                    and s["start"] is not None
                    and s["start"] <= position
                ]
                if candidates:
                    candidates[-1]["risk_rows"].extend(rows)
                elif len(contexts) == 1:
                    contexts[0]["risk_rows"].extend(rows)
                elif contexts:
                    for context in contexts:
                        context["association_uncertain"] = True
    table_evidence = [
        {"location": f"Risk row {idx}", "text": " | ".join(row)[:1800]}
        for idx, row in enumerate(risk_rows, 1)
    ]
    descriptive_fields = (
        (
            1,
            "Activity/equipment/materials",
            "Describe the activity, equipment or materials involved.",
        ),
        (2, "Hazard", "Identify the health-and-safety hazard."),
        (3, "Persons at risk", "Identify who could be harmed."),
        (
            7,
            "Control Measures Required",
            "Describe the measures used to control the stated hazard.",
        ),
    )
    incomplete = []
    unused_rows = []
    required_instructions = set()
    for index, row in enumerate(risk_rows, 1):
        if unused_risk_row(row):
            unused_rows.append(str(index))
            continue
        missing_labels = []
        for column, label, instruction in descriptive_fields:
            if (
                len(row) <= column
                or not row[column].strip()
                or (column == 3 and re.fullmatch(r"[\d\s.,–—/\-]+", row[column]))
            ):
                missing_labels.append(label)
                required_instructions.add(instruction)
        if missing_labels:
            incomplete.append(
                f"Row {index}: complete " + ", ".join(missing_labels) + "."
            )
    checks["risk_table"] = result(
        "risk_table",
        "issue"
        if not risk_rows or incomplete
        else "review"
        if unused_rows
        else "complete",
        "No readable risk rows found. Complete the risk table with the activity/equipment/materials, hazard, persons at risk and control measures for each row."
        if not risk_rows
        else " ".join(incomplete)
        + " "
        + " ".join(
            instruction
            for _, _, instruction in descriptive_fields
            if instruction in required_instructions
        )
        if incomplete
        else f"{len(risk_rows) - len(unused_rows)} risk rows have populated activity, hazard, persons-at-risk and control-measures fields. Ratings are checked separately.",
        table_evidence,
    )
    checks["risk_table"]["evidence"] = table_evidence + continuation_evidence
    if unused_rows:
        checks["risk_table"]["message"] += (
            " Wholly unused/N/A rows: "
            + ", ".join(unused_rows)
            + ". Moderator to decide whether unused-row cleanup is needed; these rows do not require ratings."
        )
    checks["ratings"], checks["risk_reduction"] = rating_checks(risk_rows)
    retained = [
        p
        for p in risk
        if re.search(
            r"remove this row|Unknown medical conditions leading to illness/collapse",
            p["text"],
            re.I,
        )
    ]
    add(
        "example",
        "issue" if retained else "complete" if risk_rows else "unable",
        "Template example row remains."
        if retained
        else "No retained example row detected."
        if risk_rows
        else "Could not inspect the risk table.",
        *retained,
    )
    admin_ps = [
        p
        for p in risk
        if (
            re.search(r"\bgeneric\b", p["text"], re.I)
            and re.search(
                r"\b(?:share[ds]?|label(?:led)?|university)\b", p["text"], re.I
            )
        )
        or (
            re.search(r"\brelated\b.*\brisk assessment\b", p["text"], re.I)
            and re.search(r"\b(?:review|updat\w*)\b", p["text"], re.I)
        )
    ]
    marked_answers = [highlighted_yes_no(p) for p in admin_ps]
    answers = [
        choice.title()
        if choice in {"yes", "no"}
        else p["text"].rsplit("?" if "?" in p["text"] else ":", 1)[-1].strip()
        for p, choice in zip(admin_ps, marked_answers, strict=True)
    ]
    unanswered = [
        str(index)
        for index, answer in enumerate(answers, 1)
        if marked_answers[index - 1] != "ambiguous"
        and re.fullmatch(r"(?:Y\s*/\s*N|Yes\s*/\s*No)?\s*[.]?", answer, re.I)
    ]
    answered = (
        len(admin_ps) == 2
        and len(
            {
                "generic" if re.search(r"\bgeneric\b", p["text"], re.I) else "related"
                for p in admin_ps
            }
        )
        == 2
        and all(
            re.fullmatch(r"(?:Y|N|Yes|No)\s*[.]?", answer, re.I) for answer in answers
        )
    )
    add(
        "admin",
        "issue" if unanswered else "complete" if answered else "review",
        "Administrative question(s) " + ", ".join(unanswered) + " unanswered. "
        "Select Yes or No; leaving the Y/N options unchanged does not answer the question."
        if unanswered
        else "Both administrative questions answered."
        if answered
        else "Could not interpret both administrative answers. Inspect the original form.",
        *admin_ps,
    )
    specialist_ps, missing, follow_up, ambiguous, misplaced, absent = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    qualified = []
    for label in SPECIALISTS:
        start = next(
            (
                i
                for i, p in enumerate(risk)
                if p["text"].startswith(label + ":")
                and not p.get("risk_table_cell")
                and not any(
                    normalise(p["text"]) in normalise(row[2])
                    for row in risk_rows
                    if len(row) > 2
                )
            ),
            None,
        )
        if start is None:
            absent.append(label)
            continue
        chunk = [risk[start]]
        for p in risk[start + 1 : start + 4]:
            if any(p["text"].startswith(other + ":") for other in SPECIALISTS) or p[
                "text"
            ].startswith("To be completed"):
                break
            chunk.append(p)
        specialist_ps.extend(chunk)
        full_answer = " ".join(p["text"] for p in chunk).split(":", 1)[1]
        pieces = re.split(
            r"(?:Please\s+list\s+)?reference\s*(?:No\.?|number)?\s*:",
            full_answer,
            maxsplit=1,
            flags=re.I,
        )
        answer = pieces[0]
        reference_answer = pieces[1].strip() if len(pieces) > 1 else ""
        answer = re.sub(
            r"Y\s*/\s*N\??|Please list reference No\s*:", " ", answer, flags=re.I
        )
        marked_answer = highlighted_yes_no(risk[start])
        if marked_answer == "ambiguous":
            ambiguous.append(label)
        elif marked_answer == "yes":
            follow_up.append(label)
        elif marked_answer == "no":
            pass
        elif re.fullmatch(r"[\s.?]*", answer):
            if re.fullmatch(
                r"(?:Yes|No|Y|N)\b(?:[\s.,;:—–-]+.*)?", reference_answer, re.I
            ):
                misplaced.append(label)
                if re.match(r"^(?:Yes|Y)\b", reference_answer, re.I):
                    follow_up.append(label)
            else:
                missing.append(label)
        elif re.fullmatch(r"(?:Y|Yes)\s*[.]?", answer.strip(), re.I) or (
            re.search(r"\b(?:Y|Yes)\b", answer, re.I)
            and re.search(r"\b(?:if|when|unless)\b", answer, re.I)
        ):
            follow_up.append(label)
        elif not re.fullmatch(r"(?:N|No)\s*[.]?", answer.strip(), re.I):
            if re.match(r"^(?:Yes|No|Y|N)\b[\s.,;:—–-]+\S", answer.strip(), re.I):
                qualified.append(label)
                if re.match(r"^(?:Yes|Y)\b", answer.strip(), re.I):
                    follow_up.append(label)
            else:
                ambiguous.append(label)
    messages = []
    if absent:
        messages.append(
            "Specialist questionnaire coverage could not be established for: "
            + ", ".join(absent)
            + ". Inspect the original and supporting assessment documents; narrative hazard headings do not answer these questions."
        )
    if misplaced:
        messages.append(
            "Interpretable Yes/No answers appear in reference fields while the primary options remain unchanged: "
            + ", ".join(misplaced)
            + ". Moderator to decide whether to accept the placement or request selection in the primary answer field. Any Yes supporting-assessment follow-up remains required."
        )
    if qualified:
        messages.append(
            "An interpretable Yes/No answer includes additional qualifications or formatting: "
            + ", ".join(qualified)
            + ". Moderator to inspect the wording and confirm whether it answers the primary question; preserve any Yes supporting-assessment follow-up."
        )
    if follow_up:
        messages.append(
            "Supervisor to locate and review supporting assessments: "
            + ", ".join(follow_up)
            + ". A Yes answer identifies follow-up, not a student completion error."
        )
    if ambiguous:
        messages.append(
            "Moderator to inspect unclear specialist answers in the original: "
            + ", ".join(ambiguous)
            + ". No reliable Yes/No answer could be established."
        )
    if missing:
        messages.append(
            "Unanswered specialist questions: "
            + ", ".join(missing)
            + ". Select Yes or No in each primary answer field; unchanged Y/N options and answers misplaced in reference fields do not complete the question."
        )
    add(
        "specialists",
        "issue"
        if missing
        else "moderator"
        if ambiguous or misplaced or absent or qualified
        else "supervisor"
        if follow_up
        else "complete",
        " ".join(messages) or "All specialist assessments answered No.",
        *specialist_ps,
    )
    if follow_up:
        checks["specialists"]["supporting_assessments"] = follow_up

    student_ra = section(
        risk, "To be completed by the person", "To be completed by the Line"
    )
    supervisor_ra = section(risk, "To be completed by the Line", "NB")
    checks["student_ra"] = combine_signoff("student_ra", student_ra, "Student Name")
    checks["supervisor_ra"] = combine_signoff(
        "supervisor_ra", supervisor_ra, "Supervisor Name"
    )
    ethics_fields = [
        field(ethics, label)
        for label in ("Student Name", "Project Title", "Supervisor Name")
    ]
    missing = [
        label
        for label, (value, _) in zip(
            ("student name", "project title", "supervisor name"),
            ethics_fields,
            strict=True,
        )
        if not value
    ]
    add(
        "ethics_details",
        "issue" if missing else "complete",
        "Missing: " + ", ".join(missing) + "."
        if missing
        else "Ethics identity and project fields present.",
        *(p for _, p in ethics_fields),
    )
    low = next(
        (
            p
            for p in ethics
            if "Low Risk" in p["text"] and "classified" not in p["text"]
        ),
        None,
    )
    medium = next((p for p in ethics if "Medium Risk" in p["text"]), None)
    low_state = selection(low)
    medium_state = selection(medium, 1 if medium is low else 0)
    status = (
        "complete"
        if low_state is True and medium_state is False
        else "review"
        if low_state is None or medium_state is None
        else "issue"
    )
    add(
        "low_risk",
        status,
        "Low Risk selected; Medium Risk unselected."
        if status == "complete"
        else "Ethics MUST be Low Risk only. Confirm selections; Medium or conflicting choices are unacceptable.",
        low,
        medium,
    )

    responses = {}
    for idx, heading in enumerate(NARRATIVES):
        stop = (
            NARRATIVES[idx + 1]
            if idx + 1 < len(NARRATIVES)
            else "Data Management, Retention"
        )
        block = section(ethics, heading, stop)[1:]
        responses[heading] = [
            p
            for p in block
            if not p["text"].startswith(("Please ", "Describe ", "Standard phrases"))
            and not word_limit_guidance(p["text"])
        ]
    missing_responses = [
        heading
        for heading, ps in responses.items()
        if not any(p["text"].strip() for p in ps)
    ]
    add(
        "narrative",
        "issue" if missing_responses else "complete",
        "No response: " + "; ".join(missing_responses)
        if missing_responses
        else "All five ethics response sections contain text.",
        *(p for ps in responses.values() for p in ps),
    )
    add("word_limits", "skipped", WORD_LIMIT_REMINDER)
    declarations = [
        p
        for p in ethics
        if p["text"].startswith(("☐", "☒", "☑", "I confirm"))
        and any(
            phrase in p["text"].casefold()
            for phrase in (
                "data management policy",
                "data retention schedule",
                "health and safety policy",
                "mandatory completion",
            )
        )
    ]
    states = [selection(p) for p in declarations]
    add(
        "declarations",
        "complete"
        if len(states) == 3 and all(s is True for s in states)
        else "review"
        if any(s is None for s in states)
        else "issue",
        "All three student declarations selected."
        if len(states) == 3 and all(s is True for s in states)
        else "All three student declarations must be selected.",
        *declarations,
    )
    physical = section(
        ethics, "Physical risk assessment form completed?", "Supervisor Statement"
    )
    option = next((p for p in physical if "Yes" in p["text"]), None)
    no_option = next((p for p in physical if "No" in p["text"]), None)
    yes_state, no_state = (
        selection(option),
        selection(no_option, 1 if no_option is option else 0),
    )
    add(
        "physical",
        "complete"
        if yes_state is True and no_state is False
        else "review"
        if yes_state is None or no_state is None
        else "issue",
        "Risk assessment completed: Yes."
        if yes_state is True and no_state is False
        else "Risk assessment completed must be Yes only.",
        *physical,
    )
    tutor = section(ethics, "Tutor sign off", "Student Name")
    tutor_boxes = [selection(p) for p in tutor if selection(p) is not None]
    add(
        "tutor",
        "complete"
        if len(tutor_boxes) == 3 and all(tutor_boxes)
        else "issue"
        if tutor_boxes
        else "review",
        "All three tutor checks selected."
        if len(tutor_boxes) == 3 and all(tutor_boxes)
        else "Tutor checklist is incomplete or unreadable.",
        *tutor,
    )
    statement = next(
        (p for p in ethics if "I confirm that I reviewed the content" in p["text"]),
        None,
    )
    state = selection(statement)
    add(
        "supervisor_statement",
        "complete" if state is True else "issue" if state is False else "review",
        "Supervisor confirmation selected."
        if state is True
        else "Supervisor confirmation must be selected.",
        statement,
    )
    dates = [
        field(ethics[index : index + 2], "Date")
        for index, p in enumerate(ethics)
        if re.match(r"Date(?:\s*:|\s+\d)", p["text"], re.I)
    ]
    student_scope = section(ethics, "Student sign:", "Supervisor sign:")
    supervisor_scope = section(ethics, "Supervisor sign:", "\x00")
    checks["student_ethics"] = combine_signoff(
        "student_ethics",
        student_scope,
        "Student Name",
        dates[0] if dates else ("", None),
        name_required=False,
    )
    checks["supervisor_ethics"] = combine_signoff(
        "supervisor_ethics",
        supervisor_scope,
        "Supervisor Name",
        dates[1] if len(dates) > 1 else ("", None),
        name_required=False,
    )
    hazards = [row[2] for row in risk_rows if len(row) >= 3]
    non_hs = [
        hazard
        for hazard in hazards
        if re.search(
            r"loss or corruption of .*data|miss(?:ed|ing) deadlines?|poor grades?|plagiarism|"
            r"(?:loss|corruption) of (?:simulation |project )?(?:data|files)",
            hazard,
            re.I,
        )
    ]
    add(
        "hs_relevance",
        "review",
        "Potential non-H&S hazards: " + "; ".join(non_hs)
        if non_hs
        else "Check hazards relate to health and safety. Manual content assessment is required "
        "unless a verified AI assessment is available; the supervisor assesses adequacy.",
    )
    checks["hs_relevance"]["evidence"] = table_evidence
    research_activities = responses["Research Activities"]
    activity_text = [" | ".join(row[1:]) for row in risk_rows] + [
        p["text"] for p in research_activities if p["text"].strip()
    ]
    location_missing = not location.strip() or any(
        not (s["area_activity"] or s["location"]) for s in risk_sections
    )
    checks["facilities"] = result(
        "facilities",
        "skipped" if location_missing else "review" if activity_text else "unable",
        "Skipped because Area/Activity is blank. The missing entry is reported by Specific area or activity; consistency cannot be assessed until it is completed."
        if location_missing
        else "Compare the stated workspace with the risk assessment activities/equipment "
        "and ethics research activities. Physical experiments, fabrication or chemical "
        "handling need an identified space for that work; distinguish these from "
        "simulation-only projects. Manual review required unless an evidence-backed "
        "AI comparison is available."
        if location and activity_text
        else "The workspace or activity descriptions could not be read. Check the original form.",
        evidence(location_p) + table_evidence + evidence(*research_activities),
    )
    if location_missing:
        checks["facilities"]["blocked_by"] = "location"
        checks["facilities"]["evidence"] = evidence(location_p)
    bad_titles = []
    project_titles = []
    for p in risk:
        if not re.search(r"\bJob Title\s*:", p["text"], re.I):
            continue
        job_title, _ = field([p], "Job Title")
        if (
            title
            and normalise(job_title)
            and (
                normalise(job_title) == normalise(title)
                or (
                    len(normalise(job_title)) > 25
                    and normalise(job_title) in normalise(title)
                )
            )
        ):
            project_titles.append(p)
            bad_titles.append(p)
        elif len(job_title.split()) > 12:
            bad_titles.append(p)
    add(
        "entry_quality",
        "issue" if project_titles else "review",
        "A job-title field contains the project title. Enter Student for the student "
        "and a staff role for the supervisor."
        if project_titles
        else "A job-title field may contain a project title."
        if bad_titles
        else "Review job titles (Student for the student; a staff role for the supervisor), "
        "inappropriate entries, placeholders and contradictory field content. Manual assessment "
        "required unless an evidence-backed AI assessment is available.",
        *bad_titles,
    )
    if is_pdf:
        uncertain = []
        if not risk_rows or any(
            doc["kind"] == "pdf"
            and doc.get("tables")
            and not doc.get("risk_table_reliable", False)
            for doc in documents
        ):
            uncertain.extend(("risk_table", "ratings", "risk_reduction", "example"))
        if len(states) != 3:
            uncertain.append("declarations")
        if len(tutor_boxes) != 3:
            uncertain.append("tutor")
        for key in (
            "student_ra",
            "supervisor_ra",
            "student_ethics",
            "supervisor_ethics",
        ):
            if checks[key]["status"] != "complete":
                if checks[key].get("signature_presence") == "blank":
                    checks[key]["message"] = (
                        "Missing: signature. The PDF signature field is visibly blank."
                    )
                else:
                    uncertain.append(key)
        for key in uncertain:
            checks[key]["status"] = "review"
            checks[key]["message"] = (
                "Signature presence could not be established reliably from the PDF. "
                "Inspect the signature area in the original; no missing-signature "
                "conclusion has been verified."
                if checks[key].get("signature_presence") == "unknown"
                else "PDF evidence could not be read reliably for this check; inspect the original. "
                + checks[key]["message"]
            )
    if not readable:
        for check in checks.values():
            check["status"] = "unable"
            check["message"] = (
                "Insufficient readable text. Inspect the original document."
            )
    if not ethics and readable:
        absence_reliable = all(
            sum(len(p["text"]) for p in doc["paragraphs"]) >= 150
            and (doc["kind"] != "pdf" or doc.get("text_coverage_reliable", False))
            for doc in documents
        ) and not any(
            re.search(r"\bethics\b", p["text"], re.I)
            or any(heading in p["text"] for heading in NARRATIVES)
            for p in paragraphs
        )
        checks["ethics_details"].update(
            status="issue" if absence_reliable else "review",
            missing_form=absence_reliable,
            message="The ethics form is missing from the supplied readable documents. Upload the completed ethics form, including its declarations and sign-offs."
            if absence_reliable
            else "An ethics form could not be identified reliably. Inspect the originals before deciding whether it is missing; extraction uncertainty is not a student error.",
        )
        for key in (
            "low_risk",
            "narrative",
            "declarations",
            "physical",
            "student_ethics",
            "supervisor_ethics",
            "tutor",
            "supervisor_statement",
        ):
            checks[key].update(
                status="skipped",
                blocked_by="ethics_details",
                message="Not assessed because the ethics form is absent or could not be identified. Resolve Ethics information table first; skipped is not a pass.",
            )
        responses = {heading: [] for heading in NARRATIVES}
    return [checks[key] for key, _, _ in CRITERIA], {
        "paragraphs": paragraphs,
        "risk_rows": risk_rows,
        "responses": responses,
        "location": location,
        "assessor": assessor,
        "activity_text": activity_text,
        "risk_sections": risk_sections,
        "module_code_context": [
            p["text"]
            for p in paragraphs
            if re.match(
                r"^(?:Course|Module)(?:\s+(?:code|number))?\s*:", p["text"], re.I
            )
        ],
    }
