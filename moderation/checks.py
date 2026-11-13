"""Deterministic completion checks. Ambiguity is kept for human review."""

import re

from .criteria import CRITERIA, result
from .documents import normalise

LABELS = (
    r"Student Name|Supervisor Name|Project Title|Assessment Title|Assessor|"
    r"Area/Activity|Job Title|Signature|Student sign|Supervisor sign|Date|"
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


def numeric_rating(value):
    """Read the entered score, including the result of an explicit calculation."""
    value = value.strip()
    if "=" in value:
        value = value.rsplit("=", 1)[1].strip()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:\(\s*[LMH]\s*\)|[LMH])?", value, re.I)
    return float(match[1]) if match else None


def field(paragraphs, label):
    separator = r"\s*:?\s*" if label.endswith("Name") else r"\s*:\s*"
    pattern = re.compile(r"(?<!\w)" + label + separator + r"(.*)", re.I)
    for index, p in enumerate(paragraphs):
        match = pattern.search(p["text"])
        if not match:
            continue
        value = re.split(r"(?:^|\s+)(?:" + LABELS + r")\s*:", match[1], flags=re.I)[0]
        if value.strip():
            return value.strip(), p
        if index + 1 < len(paragraphs):
            following = paragraphs[index + 1]
            text = following["text"]
            if (
                text
                and not re.match(r"^(?:" + LABELS + r")\b", text, re.I)
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
        if p.get("images"):
            extract["images"] = list(dict.fromkeys(p["images"]))
        if extract not in extracts:
            extracts.append(extract)
    return extracts


def area_activity_check(value, paragraph):
    """Only presence is deterministic; AI assesses the meaning of every entry."""
    return result(
        "location",
        "review" if value.strip() else "issue",
        "Area/Activity needs a content assessment: it must identify a clear "
        "manufacturing process, test procedure or named room. Review manually "
        "if AI is unavailable."
        if value.strip()
        else "Area/Activity is missing. Specify a clear manufacturing process, "
        "test procedure or named room.",
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
    title, title_p = field(scope, "Job Title")
    signature, sig_p = field(scope, "Signature")
    if not sig_p:
        signature, sig_p = field(scope, name_label.replace("Name", "sign"))
    date_value, date_p = date if date is not None else field(scope, "Date")
    has_image = bool(sig_p and sig_p["images"])
    image_paragraphs = []
    if sig_p:
        idx = scope.index(sig_p)
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
    return result(
        key,
        "issue" if missing else "complete",
        "Missing: " + ", ".join(missing) + "."
        if missing
        else "Required sign-off fields are present. Signature authenticity is not assessed.",
        evidence(name_p, title_p, sig_p, *image_paragraphs, date_p),
    )


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
                if "Student Project Ethics Approval Form" in p["text"]
            ),
            len(doc_ps),
        )
        ra_start = next(
            (
                i
                for i, p in enumerate(doc_ps[:split])
                if re.match(r"Date\s*:", p["text"], re.I)
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
        expected = normalise(student["name"])
        actual = normalise(assessor)
        if actual == expected and actual:
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
    checks["location"] = area_activity_check(location, location_p)

    risk_rows = []
    for table in tables:
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
            risk_rows.extend(
                row
                for row in table[header + 1 :]
                if len(row) >= 8 and any(cell.strip() for cell in row[1:])
            )
    table_evidence = [
        {"location": f"Risk row {idx}", "text": " | ".join(row)[:1800]}
        for idx, row in enumerate(risk_rows, 1)
    ]
    missing_cells = [
        str(i)
        for i, row in enumerate(risk_rows, 1)
        if any(not cell.strip() for cell in row[:9]) or len(row) < 9
    ]
    checks["risk_table"] = result(
        "risk_table",
        "issue" if not risk_rows or missing_cells else "complete",
        "No readable risk rows found."
        if not risk_rows
        else "Incomplete risk rows: " + ", ".join(missing_cells)
        if missing_cells
        else f"{len(risk_rows)} risk rows have populated required columns.",
        table_evidence,
    )
    bad_ratings = []
    for idx, row in enumerate(risk_rows, 1):
        if len(row) < 9 or any(
            not re.search(r"\d", cell) for cell in row[4:7] + row[8:9]
        ):
            bad_ratings.append(str(idx))
    checks["ratings"] = result(
        "ratings",
        "issue" if bad_ratings else "complete" if risk_rows else "unable",
        "Missing numeric values in risk rows: " + ", ".join(bad_ratings)
        if bad_ratings
        else "Numeric severity, likelihood, initial rating and final result are present."
        if risk_rows
        else "No readable ratings found.",
        table_evidence,
    )
    unchanged, unreadable = [], []
    for idx, row in enumerate(risk_rows, 1):
        initial = numeric_rating(row[6]) if len(row) > 6 else None
        final = numeric_rating(row[8]) if len(row) > 8 else None
        if initial is None or final is None:
            unreadable.append(str(idx))
        elif final >= initial:
            unchanged.append(f"Row {idx}: initial {initial:g}, final {final:g}")
    checks["risk_reduction"] = result(
        "risk_reduction",
        "issue"
        if unchanged
        else "unable"
        if unreadable or not risk_rows
        else "complete",
        "Final ratings must be lower than initial ratings. "
        + "; ".join(unchanged)
        + (". Cannot compare rows: " + ", ".join(unreadable) if unreadable else ".")
        if unchanged
        else "Cannot compare initial and final ratings in rows: "
        + ", ".join(unreadable)
        if unreadable
        else "Final ratings are lower than the entered initial ratings in every row."
        if risk_rows
        else "No readable risk ratings to compare.",
        table_evidence,
    )
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
        if "Generic to the University" in p["text"]
        or "related risk assessment that may require" in p["text"]
    ]
    answers = [p["text"].rsplit("?", 1)[-1].strip() for p in admin_ps]
    unanswered = [
        str(index)
        for index, answer in enumerate(answers, 1)
        if re.fullmatch(r"(?:Y\s*/\s*N|Yes\s*/\s*No)?\s*[.]?", answer, re.I)
    ]
    answered = len(admin_ps) == 2 and all(
        re.fullmatch(r"(?:Y|N|Yes|No)\s*[.]?", answer, re.I) for answer in answers
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
    specialist_ps, missing, follow_up, ambiguous = [], [], [], []
    for label in SPECIALISTS:
        start = next(
            (i for i, p in enumerate(risk) if p["text"].startswith(label + ":")), None
        )
        if start is None:
            missing.append(label)
            continue
        chunk = [risk[start]]
        for p in risk[start + 1 : start + 4]:
            if any(p["text"].startswith(other + ":") for other in SPECIALISTS) or p[
                "text"
            ].startswith("To be completed"):
                break
            chunk.append(p)
        specialist_ps.extend(chunk)
        answer = " ".join(p["text"] for p in chunk).split(":", 1)[1]
        answer = re.sub(
            r"Y\s*/\s*N\??|Please list reference No\s*:", " ", answer, flags=re.I
        )
        if re.search(r"\b(?:Y|Yes)\b", answer, re.I):
            follow_up.append(label)
        elif re.search(r"\b(?:if|unless|possibly|maybe)\b", answer, re.I):
            ambiguous.append(label)
        elif not re.search(r"\b(?:N|No)\b", answer, re.I):
            missing.append(label)
    messages = []
    if follow_up:
        messages.append(
            "Locate and review supporting assessments: " + ", ".join(follow_up) + "."
        )
    if ambiguous:
        messages.append("Clarify conditional answers: " + ", ".join(ambiguous) + ".")
    if missing:
        messages.append("Missing/unreadable answers: " + ", ".join(missing) + ".")
    add(
        "specialists",
        "review" if follow_up or ambiguous else "issue" if missing else "complete",
        " ".join(messages) or "All specialist assessments answered No.",
        *specialist_ps,
    )

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
    counts = {
        heading: len(
            re.findall(
                r"\b[\w]+(?:[-’'][\w]+)*\b",
                " ".join(p["text"] for p in responses[heading]),
            )
        )
        for heading in NARRATIVES[:3]
    }
    exceeded = [heading for heading, count in counts.items() if count > 200]
    add(
        "word_limits",
        "issue" if exceeded else "complete" if not missing_responses else "unable",
        "; ".join(f"{heading}: {count}/200 words" for heading, count in counts.items())
        + ". Counts exclude template instructions; verify near-boundary cases.",
    )
    declarations = [
        p
        for p in ethics
        if p["text"].startswith(("☐", "☒", "☑", "I confirm"))
        and any(
            phrase in p["text"]
            for phrase in (
                "Data Management policy",
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
    tutor = section(ethics, "Tutor sign off", "You must use this document")
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
        field([p], "Date") for p in ethics if re.match(r"Date\s*:", p["text"], re.I)
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
        else "Language review is pending. Check hazards relate to health and safety; supervisor assesses adequacy.",
    )
    checks["hs_relevance"]["evidence"] = table_evidence
    research_activities = responses["Research Activities"]
    activity_text = [" | ".join(row[1:]) for row in risk_rows] + [
        p["text"] for p in research_activities if p["text"].strip()
    ]
    checks["facilities"] = result(
        "facilities",
        "review" if location and activity_text else "unable",
        "Compare the stated workspace with the risk assessment activities/equipment "
        "and ethics research activities. Physical experiments, fabrication or chemical "
        "handling need an identified space for that work; distinguish these from "
        "simulation-only projects. Manual review required unless an evidence-backed "
        "AI comparison is available."
        if location and activity_text
        else "The workspace or activity descriptions could not be read. Check the original form.",
        evidence(location_p) + table_evidence + evidence(*research_activities),
    )
    bad_titles = []
    for p in risk:
        if "Job Title:" not in p["text"]:
            continue
        job_title, _ = field([p], "Job Title")
        if len(job_title.split()) > 12 or (
            title
            and len(normalise(job_title)) > 25
            and normalise(job_title) in normalise(title)
        ):
            bad_titles.append(p)
    add(
        "entry_quality",
        "review",
        "A job-title field may contain a project title."
        if bad_titles
        else "Language review is pending for inappropriate entries, placeholders and contradictory field content.",
        *bad_titles,
    )
    if is_pdf:
        for key in (
            "risk_table",
            "ratings",
            "risk_reduction",
            "example",
            "low_risk",
            "declarations",
            "physical",
            "tutor",
            "supervisor_statement",
            "student_ra",
            "supervisor_ra",
            "student_ethics",
            "supervisor_ethics",
        ):
            checks[key]["status"] = "review"
            checks[key]["message"] = (
                "PDF layout, tick boxes or signature images require visual review. "
                + checks[key]["message"]
            )
    if not readable:
        for check in checks.values():
            check["status"] = "unable"
            check["message"] = (
                "Insufficient readable text. Inspect the original document."
            )
    return [checks[key] for key, _, _ in CRITERIA], {
        "paragraphs": paragraphs,
        "risk_rows": risk_rows,
        "responses": responses,
        "location": location,
        "assessor": assessor,
        "activity_text": activity_text,
    }
