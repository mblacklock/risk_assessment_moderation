"""Bounded document extraction. Uploaded archive paths are never extracted."""

import io
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from .word_drawings import drawing_png, drawings

MAX_ZIP = 150 * 1024 * 1024
MAX_FILE = 25 * 1024 * 1024
MAX_EXPANDED = 500 * 1024 * 1024
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
}


def text_of(element):
    def own_text(node):
        if node.tag == f"{{{NS['w']}}}txbxContent":
            return ""
        if node.tag == f"{{{NS['w']}}}t":
            return node.text or ""
        if node.tag in {f"{{{NS['w']}}}br", f"{{{NS['w']}}}cr"}:
            return "\n"
        return "".join(own_text(child) for child in node)

    return own_text(element).strip()


def numbered_texts(body, numbering):
    """Include visible decimal list labels, which Word stores outside w:t."""

    def value(node, path, default=None):
        child = node.find(path, NS) if node is not None else None
        return child.get(f"{{{NS['w']}}}val", default) if child is not None else default

    abstracts = {
        n.get(f"{{{NS['w']}}}abstractNumId"): n
        for n in numbering.findall("w:abstractNum", NS)
    }
    definitions = {}
    for num in numbering.findall("w:num", NS):
        abstract = abstracts.get(value(num, "w:abstractNumId"))
        if abstract is None:
            continue
        levels = {
            int(level.get(f"{{{NS['w']}}}ilvl")): {
                "start": int(value(level, "w:start", "1")),
                "format": value(level, "w:numFmt", "decimal"),
                "text": value(level, "w:lvlText", "%1"),
            }
            for level in abstract.findall("w:lvl", NS)
        }
        for override in num.findall("w:lvlOverride", NS):
            level_id = int(override.get(f"{{{NS['w']}}}ilvl"))
            if level_id not in levels:
                continue
            replacement = override.find("w:lvl", NS)
            if replacement is not None:
                levels[level_id].update(
                    {
                        "start": int(value(replacement, "w:start", "1")),
                        "format": value(replacement, "w:numFmt", "decimal"),
                        "text": value(replacement, "w:lvlText", "%1"),
                    }
                )
            start = value(override, "w:startOverride")
            if start is not None:
                levels[level_id]["start"] = int(start)
        definitions[num.get(f"{{{NS['w']}}}numId")] = levels
    counters, texts = {}, {}
    for paragraph in body.findall(".//w:p", NS):
        text = text_of(paragraph)
        props = paragraph.find("w:pPr/w:numPr", NS)
        num_id = value(props, "w:numId")
        level_id = int(value(props, "w:ilvl", "0"))
        levels = definitions.get(num_id, {})
        level = levels.get(level_id)
        if level and num_id != "0":
            counter = counters.setdefault(num_id, {})
            counter[level_id] = counter.get(level_id, level["start"] - 1) + 1
            for deeper in list(counter):
                if deeper > level_id:
                    del counter[deeper]
            refs = [int(ref) - 1 for ref in re.findall(r"%([1-9])", level["text"])]
            if refs and all(
                levels.get(ref, {}).get("format") in {"decimal", "decimalZero"}
                for ref in refs
            ):
                label = re.sub(
                    r"%([1-9])",
                    lambda m: str(
                        counter.get(int(m[1]) - 1, levels[int(m[1]) - 1]["start"])
                    ),
                    level["text"],
                )
                text = (label + " " + text).strip()
        texts[paragraph] = text
    return texts


def normalise(value):
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def highlight_ranges(flags):
    ranges = []
    for index, marked in enumerate(flags):
        if marked:
            if ranges and ranges[-1][1] == index:
                ranges[-1][1] = index + 1
            else:
                ranges.append([index, index + 1])
    return ranges


def highlighted_yes_no(paragraph):
    text = paragraph["text"]
    pair = re.search(r"\b(?P<yes>Y(?:es)?)\s*/\s*(?P<no>N(?:o)?)\b", text, re.I)
    if not pair:
        return None
    ranges = paragraph.get("highlighted_ranges", [])
    if not ranges:
        # Only explicit run/span contrast is used, never inherited paragraph styling.
        ranges = paragraph.get("bold_ranges", [])
    marked = [any(start <= i < end for start, end in ranges) for i in range(len(text))]
    yes, no = [marked[pair.start(key) : pair.end(key)] for key in ("yes", "no")]
    if not any(yes + no):
        return None
    if all(yes) and not any(no):
        return "yes"
    if all(no) and not any(yes):
        return "no"
    return "ambiguous"


def word_limit_guidance(value):
    """Recognise standalone word-limit labels, not sentences in an answer."""
    return bool(
        re.fullmatch(
            r"\s*\(?\s*(?:\d+\s+)?words?\s+maximum\s*\)?\s*\.?\s*",
            value,
            re.I,
        )
    )


def bounded_zip(data, maximum=MAX_EXPANDED):
    archive = zipfile.ZipFile(io.BytesIO(data))
    entries = archive.infolist()
    if len(entries) > 2000 or sum(e.file_size for e in entries) > maximum:
        archive.close()
        raise ValueError("Archive expands beyond the supported size or file count.")
    names = [e.filename for e in entries]
    if len(names) != len(set(names)):
        archive.close()
        raise ValueError("Archive contains duplicate filenames.")
    for entry in entries:
        path = PurePosixPath(entry.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ":" in entry.filename:
            archive.close()
            raise ValueError("Archive contains an unsafe filename.")
        if entry.flag_bits & 1:
            archive.close()
            raise ValueError("Password-protected archives are not supported.")
    return archive


def archive_submissions(data):
    """Associate Blackboard text metadata with every listed document."""
    if len(data) > MAX_ZIP:
        raise ValueError("ZIP must be 150 MB or smaller.")
    with bounded_zip(data) as archive:
        entries = {e.filename: e for e in archive.infolist() if not e.is_dir()}
        metadata = {}
        for name, entry in entries.items():
            if not name.lower().endswith(".txt") or entry.file_size > 1024 * 1024:
                continue
            text = archive.read(entry).decode("utf-8-sig", errors="replace")
            who = re.search(r"^Name:\s*(.*?)\s*\(([^()]+)\)\s*$", text, re.M)
            date = re.search(r"^Date Submitted:\s*(.*)$", text, re.M)
            if who:
                for linked in re.findall(r"^\s*Filename:\s*(.+)$", text, re.M):
                    metadata[PurePosixPath(linked.strip()).name] = {
                        "name": who[1].strip(),
                        "number": who[2].strip(),
                        "submitted": date[1].strip() if date else "",
                        "attempt": name,
                    }
        groups = {}
        ignored = []
        for name, entry in entries.items():
            if name.startswith("__MACOSX/") or PurePosixPath(name).name.startswith("."):
                continue
            suffix = PurePosixPath(name).suffix.lower()
            if suffix not in {".pdf", ".docx", ".doc"}:
                if suffix != ".txt":
                    ignored.append(name)
                continue
            if entry.file_size > MAX_FILE:
                raise ValueError(f"Document exceeds the 25 MB limit: {name}")
            meta = metadata.get(PurePosixPath(name).name)
            if not meta:
                number = re.search(r"\b[wW]\d{7,10}\b", name)
                meta = {
                    "name": "Identity needs review",
                    "number": number[0].lower() if number else "Unknown",
                    "submitted": "",
                    "attempt": name,
                }
            group = groups.setdefault(meta["attempt"], {**meta, "files": []})
            group["files"].append({"name": name, "data": archive.read(entry)})
        if not groups:
            raise ValueError(
                "No Word (.doc/.docx) or PDF submissions were found in this ZIP."
            )
        if len(groups) > 500:
            raise ValueError("Please upload at most 500 submissions per review.")
        return list(groups.values()), ignored


def extract_docx(data, filename):
    with bounded_zip(data, 80 * 1024 * 1024) as archive:
        xml = archive.read("word/document.xml")
        if len(xml) > 10 * 1024 * 1024:
            raise ValueError("Word document XML is too large.")
        root = ET.fromstring(xml)
        styles = {}
        if "word/styles.xml" in archive.namelist():
            styles = {
                node.get(f"{{{NS['w']}}}styleId"): node
                for node in ET.fromstring(archive.read("word/styles.xml")).findall(
                    "w:style", NS
                )
            }

        def style_bold(style_id, seen=()):
            if style_id in seen or style_id not in styles:
                return False
            node = styles[style_id]
            strong = node.find("w:rPr/w:b", NS)
            if strong is not None:
                return strong.get(f"{{{NS['w']}}}val", "1") not in {"0", "false", "off"}
            base = node.find("w:basedOn", NS)
            return (
                style_bold(base.get(f"{{{NS['w']}}}val"), (*seen, style_id))
                if base is not None
                else False
            )

        body = root.find("w:body", NS)
        if body is None:
            raise ValueError("Word document body is missing.")
        texts = (
            numbered_texts(body, ET.fromstring(archive.read("word/numbering.xml")))
            if "word/numbering.xml" in archive.namelist()
            else {p: text_of(p) for p in body.findall(".//w:p", NS)}
        )
        relationships = {}
        if "word/_rels/document.xml.rels" in archive.namelist():
            rels = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
            for rel in rels:
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                path = (
                    target.lstrip("/")
                    if target.startswith("/")
                    else posixpath.normpath(posixpath.join("word", target))
                )
                relationships[rel.get("Id")] = path
        drawing_nodes = drawings(body)
        drawing_ids = {node: index for index, node in enumerate(drawing_nodes)}
        source_paragraphs = body.findall(".//w:p", NS)
        parents = {child: parent for parent in body.iter() for child in parent}
        floating = set()
        associations = {}
        for box in body.findall(".//w:txbxContent", NS):
            box_ps = box.findall(".//w:p", NS)
            floating.update(box_ps)
            node = parents.get(box)
            anchor = None
            while node is not None and node.tag != f"{{{NS['w']}}}p":
                if node.tag.endswith("}anchor"):
                    anchor = node
                node = parents.get(node)
            if node is None or anchor is None:
                continue
            vertical = anchor.find(
                "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}positionV"
            )
            horizontal = anchor.find(
                "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}positionH"
            )
            try:
                placed = (
                    vertical is not None
                    and vertical.get("relativeFrom") == "paragraph"
                    and abs(int(vertical[0].text)) <= 127000
                    and horizontal is not None
                    and horizontal.get("relativeFrom") == "character"
                    and 0 <= int(horizontal[0].text) <= 381000
                )
            except (ValueError, TypeError, IndexError):
                placed = False
            if placed and re.search(r"\bJob Title\s*:\s*$", texts[node], re.I):
                value = " ".join(texts[p] for p in box_ps).strip()
                if value:
                    texts[node] += " " + value
                    associations[node] = value
        drawn_fields = {}
        uncertain_fields = set()
        for index, source in enumerate(source_paragraphs):
            nodes = [node for node in source.iter() if node in drawing_ids]
            if not nodes:
                continue
            target = source
            if not texts[source] and index + 1 < len(source_paragraphs):
                following = source_paragraphs[index + 1]
                if parents[source] is parents[following]:
                    target = following
            if not re.match(
                r"^(?:Signature|Student sign|Supervisor sign)\s*:", texts[target], re.I
            ):
                continue
            for node in nodes:
                # Page-positioned graphics can belong to a different field.
                vertical = node.find(
                    "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}positionV"
                )
                horizontal = node.find(
                    "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}positionH"
                )
                try:
                    if node.tag.endswith("anchor") and (
                        vertical is None or horizontal is None
                    ):
                        raise ValueError("Unknown drawing placement")
                    if vertical is not None and (
                        vertical.get("relativeFrom") != "paragraph"
                        or not -127000 <= int(vertical[0].text) <= 381000
                    ):
                        raise ValueError("Ambiguous drawing placement")
                    if horizontal is not None and (
                        horizontal.get("relativeFrom") not in {"column", "character"}
                        or not 0 <= int(horizontal[0].text) <= 3810000
                    ):
                        raise ValueError("Ambiguous horizontal placement")
                    drawing_png(node)
                except (
                    ValueError,
                    TypeError,
                    IndexError,
                    ZeroDivisionError,
                    RuntimeError,
                ):
                    uncertain_fields.add(target)
                else:
                    drawn_fields.setdefault(target, []).append(
                        f"word-drawing-{drawing_ids[node]}.png"
                    )
        paragraphs = []
        for source_index, p in enumerate(body.findall(".//w:p", NS)):
            text = texts[p]
            images = []
            images.extend(drawn_fields.get(p, []))
            for node in p.findall(".//a:blip", NS) + p.findall(".//v:imagedata", NS):
                ref = node.get(f"{{{NS['r']}}}embed") or node.get(f"{{{NS['r']}}}id")
                target = relationships.get(ref)
                if target and target in archive.namelist():
                    images.append(target)
            # Content controls have authoritative state even when glyphs differ.
            states = []
            for box in p.findall(".//w14:checkbox", NS):
                checked = box.find("w14:checked", NS)
                states.append(
                    checked is not None
                    and checked.get(f"{{{NS['w14']}}}val", "0") in {"1", "true"}
                )
            for box in p.findall(".//w:checkBox", NS):
                checked = box.find("w:checked", NS)
                if checked is None:
                    checked = box.find("w:default", NS)
                states.append(
                    checked is not None
                    and checked.get(f"{{{NS['w']}}}val", "1") in {"1", "true"}
                )
            if text or images or states:
                paragraph = {
                    "text": text,
                    "images": images,
                    "states": states,
                    "source_index": source_index,
                }
                if p in uncertain_fields:
                    paragraph["signature_drawing_uncertain"] = True
                if p in floating:
                    paragraph["floating_text_unassociated"] = True
                ancestor = parents.get(p)
                while ancestor is not None and ancestor.tag != f"{{{NS['w']}}}tbl":
                    ancestor = parents.get(ancestor)
                if ancestor is not None:
                    heading = ancestor.find("w:tr", NS)
                    header_text = text_of(heading) if heading is not None else ""
                    if (
                        "hazard" in header_text.casefold()
                        and "severity" in header_text.casefold()
                    ):
                        paragraph["risk_table_cell"] = True
                if p in associations:
                    paragraph["textbox_association"] = {
                        "field": "Job Title",
                        "text": associations[p],
                        "placement": "paragraph/character anchor adjacent to field",
                    }
                raw, marked, bold = "", [], []
                explicit_bold = False
                paragraph_style = p.find("w:pPr/w:pStyle", NS)
                inherited_bold = style_bold(
                    paragraph_style.get(f"{{{NS['w']}}}val")
                    if paragraph_style is not None
                    else "Normal"
                )
                for run in p.findall(".//w:r", NS):
                    # Preserve spaces here: offsets must match the paragraph text.
                    value = "".join(
                        node.text or "" for node in run.findall(".//w:t", NS)
                    )
                    highlight = run.find("w:rPr/w:highlight", NS)
                    active = (
                        highlight is not None
                        and highlight.get(f"{{{NS['w']}}}val", "none") != "none"
                    )
                    raw += value
                    marked.extend([active] * len(value))
                    strong = run.find("w:rPr/w:b", NS)
                    explicit_bold |= strong is not None
                    run_style = run.find("w:rPr/w:rStyle", NS)
                    effective_bold = (
                        strong.get(f"{{{NS['w']}}}val", "1")
                        not in {"0", "false", "off"}
                        if strong is not None
                        else inherited_bold
                        or (
                            run_style is not None
                            and style_bold(run_style.get(f"{{{NS['w']}}}val"))
                        )
                    )
                    bold.extend([effective_bold] * len(value))
                offset = text.find(raw.strip()) if raw.strip() else -1
                if offset >= 0 and any(marked):
                    leading = len(raw) - len(raw.lstrip())
                    flags = [False] * offset + marked[
                        leading : leading + len(raw.strip())
                    ]
                    paragraph["highlighted_ranges"] = highlight_ranges(flags)
                if offset >= 0 and any(bold) and explicit_bold:
                    leading = len(raw) - len(raw.lstrip())
                    paragraph["bold_ranges"] = highlight_ranges(
                        [False] * offset + bold[leading : leading + len(raw.strip())]
                    )
                paragraphs.append(paragraph)
        tables, table_positions, continuation_cells = [], [], []
        for table in body.findall(".//w:tbl", NS):
            first_p = table.find(".//w:p", NS)
            table_positions.append(
                source_paragraphs.index(first_p) if first_p is not None else None
            )
            rows = []
            continuations = []
            for row in table.findall("w:tr", NS):
                cells = row.findall("w:tc", NS)
                continuations.append(
                    [
                        i
                        for i, cell in enumerate(cells)
                        if (merge := cell.find("w:tcPr/w:vMerge", NS)) is not None
                        and merge.get(f"{{{NS['w']}}}val", "continue") == "continue"
                    ]
                )
                rows.append(
                    [
                        "\n".join(texts[p] for p in cell.findall(".//w:p", NS)).strip()
                        for cell in row.findall("w:tc", NS)
                    ]
                )
            tables.append(rows)
            continuation_cells.append(continuations)
        return {
            "filename": filename,
            "kind": "docx",
            "paragraphs": paragraphs,
            "tables": tables,
            "table_positions": table_positions,
            "continuation_cells": continuation_cells,
            "pages": None,
            "highlight_reader_version": 1,
            "drawing_reader_version": 1,
            "linebreak_reader_version": 1,
        }


def pdf_paragraphs(page, tutor_tables, tables=()):
    """Reflow wrapped lines within a block, keeping fields and selections distinct."""
    boundaries = re.compile(
        r"^(?:Date(?:\s*:|\s+\d)|Assessor\s*:|Area/Activity|Assessment Title|Student Name|"
        r"Supervisor Name|Job Title|Signature\s*:|Student sign|Supervisor sign|"
        r"Project Title|Ethics application|Please |Describe |Standard phrases|"
        r"To be completed|I consider|NB\b|Can this risk|Is there a related|"
        r"Physical risk assessment form completed|Tutor sign off|"
        r"Project Aims|Research Activities|Ethical, Environmental|Research Data|"
        r"Data Management, Retention|Ethics, Health|Physical Risk|Supervisor Statement|"
        r"[☐☒☑]|\d+\s*[-.]\s*$)",
        re.I,
    )
    import pymupdf

    highlights = [
        path["rect"]
        for path in page.get_drawings()
        if path.get("fill")
        and max(path["fill"]) - min(path["fill"]) > 0.15
        and path.get("fill_opacity", 1) >= 0.2
    ]
    for annotation in page.annots(types=[pymupdf.PDF_ANNOT_HIGHLIGHT]) or []:
        points = annotation.vertices or []
        highlights.extend(
            pymupdf.Quad(points[i : i + 4]).rect for i in range(0, len(points), 4)
        )
    positioned = []
    for block in page.get_text(
        "rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    )["blocks"]:
        if block["type"] != 0:
            continue
        parts, flags, bold_flags, origin, bounds = [], [], [], None, []

        def flush():
            if parts:
                paragraph = {"text": " ".join(parts), "images": [], "states": []}
                paragraph["pdf_bbox"] = [
                    min(b[0] for b in bounds),
                    min(b[1] for b in bounds),
                    max(b[2] for b in bounds),
                    max(b[3] for b in bounds),
                ]
                paragraph["page"] = page.number + 1
                if any(flags):
                    paragraph["highlighted_ranges"] = highlight_ranges(flags)
                if any(bold_flags):
                    paragraph["bold_ranges"] = highlight_ranges(bold_flags)
                positioned.append((origin, paragraph))
                parts.clear()
                flags.clear()
                bold_flags.clear()
                bounds.clear()

        for line in block["lines"]:
            characters = [c for span in line["spans"] for c in span["chars"]]
            raw = "".join(c["c"] for c in characters)
            text = raw.strip()
            line_flags = []
            line_bold = [
                bool(span.get("flags", 0) & 16)
                for span in line["spans"]
                for c in span["chars"]
                for _ in c["c"]
            ]
            for c in characters:
                x0c, y0c, x1c, y1c = c["bbox"]
                selected = any(
                    rect.contains(pymupdf.Point((x0c + x1c) / 2, (y0c + y1c) / 2))
                    for rect in highlights
                )
                line_flags.extend([selected] * len(c["c"]))
            leading = len(raw) - len(raw.lstrip())
            line_flags = line_flags[leading : leading + len(text)]
            x0, y0, x1, y1 = line["bbox"]
            if any(
                t.bbox[0] <= (x0 + x1) / 2 <= t.bbox[2]
                and t.bbox[1] <= (y0 + y1) / 2 <= t.bbox[3]
                for t in tutor_tables
            ):
                flush()
                continue
            if not text or boundaries.match(text):
                flush()
            if text:
                if not parts:
                    origin = (y0, x0)
                else:
                    flags.append(False)
                    bold_flags.append(False)
                parts.append(text)
                flags.extend(line_flags)
                bold_flags.extend(line_bold[leading : leading + len(text)])
                bounds.append(line["bbox"])
        flush()
    for table in tutor_tables:
        for cells, row in zip(table.rows, table.extract(), strict=True):
            values = [value or "" for value in row]
            text = " ".join(" ".join(value.split()) for value in values).strip()
            if "tutorsignoff" in normalise(text):
                text = "Tutor sign off"
            state = values[-1].strip().casefold()
            states = (
                [True] if state in {"x", "☒", "☑"} else [False] if state == "☐" else []
            )
            positioned.append(
                (
                    (cells.bbox[1], cells.bbox[0]),
                    {"text": text, "images": [], "states": states},
                )
            )
    ordered = sorted(positioned, key=lambda pair: pair[0])
    rows = []
    for position, paragraph in ordered:
        if not rows or position[0] - rows[-1][0][0][0] > 3:
            rows.append([])
        rows[-1].append((position, paragraph))
    paragraphs = [
        p for row in rows for _, p in sorted(row, key=lambda pair: pair[0][1])
    ]
    pdf_checkbox_states(page, paragraphs)
    attach_pdf_signature_images(page, paragraphs, tables)
    return paragraphs


def pdf_checkbox_states(page, paragraphs):
    """Read isolated vector boxes beside risk options; uncertain graphics stay manual."""
    import pymupdf

    paths = page.get_drawings()
    boxes = [
        pymupdf.Rect(item[1])
        for path in paths
        for item in path["items"]
        if item[0] == "re"
        and 6 <= pymupdf.Rect(item[1]).width <= 18
        and 6 <= pymupdf.Rect(item[1]).height <= 18
        and 0.75 <= pymupdf.Rect(item[1]).width / pymupdf.Rect(item[1]).height <= 1.3
    ]
    images = page.get_image_info()
    for paragraph in paragraphs:
        if paragraph["states"] or re.search(r"[☐☒☑]", paragraph["text"]):
            continue
        options = re.findall(r"\b(?:Low|Medium) Risk\b", paragraph["text"], re.I)
        if not options:
            continue
        states = []
        for option in options:
            labels = [
                r
                for r in page.search_for(option)
                if pymupdf.Rect(paragraph.get("pdf_bbox", [0, 0, 0, 0])).intersects(r)
            ]
            candidates = [
                box
                for box in boxes
                if any(
                    0 <= label.x0 - box.x1 <= 24
                    and abs((label.y0 + label.y1) / 2 - (box.y0 + box.y1) / 2) <= 6
                    for label in labels
                )
            ]
            if len(candidates) != 1:
                states.append(None)
                continue
            box = candidates[0]
            inner = pymupdf.Rect(box.x0 + 1.5, box.y0 + 1.5, box.x1 - 1.5, box.y1 - 1.5)
            if any(
                inner.intersects(pymupdf.Rect(img["bbox"])) for img in images
            ) or any(
                inner.intersects(annotation.rect) for annotation in page.annots() or []
            ):
                states.append(None)
                continue
            ink = any(
                item[0] == "l"
                and inner.contains(item[1])
                and inner.contains(item[2])
                and abs(item[1].x - item[2].x) > 1
                and abs(item[1].y - item[2].y) > 1
                for path in paths
                for item in path["items"]
            )
            text = page.get_text("text", clip=inner).strip()
            uncertain = any(
                inner.intersects(path["rect"])
                and (
                    any(item[0] not in {"re", "l"} for item in path["items"])
                    or (
                        path.get("fill") is not None
                        and min(path["fill"]) < 0.8
                        and path.get("fill_opacity", 1) > 0.2
                    )
                )
                for path in paths
            )
            states.append(
                True
                if ink or text in {"x", "X", "✓", "✔"}
                else None
                if text or uncertain
                else False
            )
        paragraph["states"] = states
        paragraph["pdf_selection_note"] = (
            "Vector checkbox selection inspected beside the risk option; ambiguous marks remain unreadable."
        )


def attach_pdf_signature_images(page, paragraphs, tables=()):
    """Associate nearby embedded images with signature fields, never page branding."""
    import pymupdf

    labels = [
        rect
        for label in ("Signature:", "Student sign:", "Supervisor sign:")
        for rect in page.search_for(label)
    ]
    dates = page.search_for("Date:")
    images = page.get_image_info(xrefs=True)
    for paragraph in paragraphs:
        if not re.match(
            r"^(?:Signature|Student sign|Supervisor sign)\s*:", paragraph["text"], re.I
        ):
            continue
        bounds = paragraph.get("pdf_bbox")
        if bounds is None:
            continue
        nearby_labels = [
            label
            for label in labels
            if abs(label.y0 - bounds[1]) <= 3 and bounds[0] - 3 <= label.x0 <= bounds[2]
        ]
        if len(nearby_labels) != 1:
            continue
        label = nearby_labels[0]
        right = min(
            [
                rect.x0 - 2
                for rect in [*labels, *dates]
                if rect.x0 > label.x1 and abs(rect.y0 - label.y0) < 10
            ]
            or [page.rect.width - 20]
        )
        bottom = min(
            [
                rect.y0 - 2
                for rect in [*labels, *dates]
                if rect.y0 > label.y1 + 4 and rect.x0 < right and rect.x1 > label.x0
            ]
            or [label.y0 + 100]
        )
        top = label.y0 - 8
        owner_top = None
        owner_details = [
            p["pdf_bbox"]
            for p in paragraphs
            if p.get("pdf_bbox")
            and re.match(r"^(?:Student Name|Supervisor Name)\s*:", p["text"], re.I)
            and 0 < label.y0 - p["pdf_bbox"][3] <= 80
            and p["pdf_bbox"][0] <= label.x0 + 10 <= p["pdf_bbox"][2]
        ]
        if owner_details:
            owner_bottom = max(rect[3] for rect in owner_details)
            if not any(owner_bottom < other.y0 < label.y0 for other in labels):
                owner_top = owner_bottom + 2
                top = max(label.y0 - 45, owner_top)
        cells = [
            pymupdf.Rect(cell)
            for table in tables
            for row in table.rows
            for cell in row.cells
            if cell
            and pymupdf.Rect(cell).contains(label)
            and pymupdf.Rect(cell).height <= 160
            and pymupdf.Rect(cell).width >= label.width + 15
        ]
        if cells:
            cell = min(cells, key=lambda rect: rect.width * rect.height)
            top = max(label.y0 - 45, cell.y0 + 1, owner_top or 0)
            right = min(right, cell.x1 - 1)
            bottom = min(bottom, cell.y1 - 1)
        candidates = []
        for image in images:
            rect = pymupdf.Rect(image["bbox"])
            if (
                image["xref"] > 0
                and image["width"] > 1
                and image["height"] > 1
                and image["width"] * image["height"] <= 16_000_000
                and 6 < rect.width <= right - label.x0 + 6
                and 4 < rect.height <= 100
                and rect.x0 >= label.x0 - 3
                and rect.x1 <= right + 3
                and top <= rect.y0 <= label.y1 + 30
                and (rect.y0 >= label.y0 - 8 or rect.y1 >= label.y0)
                and rect.y1 <= bottom
            ):
                candidates.append(f"pdf-image-{image['xref']}.png")
        # Multiple separate images in the field are left for visual review.
        if len(candidates) == 1:
            paragraph["images"] = list(dict.fromkeys(candidates))
        elif not candidates and pdf_signature_area_blank(
            page, label, right, bottom, images
        ):
            paragraph["signature_field_blank"] = True


def pdf_signature_area_blank(page, label, right, bottom, images):
    """Only call a readable field blank when neither ink nor nearby graphics remain."""
    import pymupdf

    possible = (
        pymupdf.Rect(label.x0 - 2, label.y0 - 40, right, min(bottom, label.y0 + 70))
        & page.rect
    )
    strip = (
        pymupdf.Rect(label.x1 + 3, label.y0 - 2, right - 2, label.y1 + 2) & page.rect
    )
    if strip.is_empty or strip.width < 20:
        return False
    if any(pymupdf.Rect(image["bbox"]).intersects(possible) for image in images):
        return False
    if any(annotation.rect.intersects(possible) for annotation in page.annots() or []):
        return False
    if any(widget.rect.intersects(possible) for widget in page.widgets() or []):
        return False
    for path in page.get_drawings():
        if not path["rect"].intersects(possible):
            continue
        for item in path["items"]:
            if item[0] == "l":
                a, b = item[1:3]
                rect = pymupdf.Rect(
                    min(a.x, b.x) - 0.5,
                    min(a.y, b.y) - 0.5,
                    max(a.x, b.x) + 0.5,
                    max(a.y, b.y) + 0.5,
                )
                if not rect.intersects(possible):
                    continue
                if abs(a.y - b.y) < 0.5 and abs(a.x - b.x) >= possible.width * 0.8:
                    continue
                if abs(a.x - b.x) < 0.5 and abs(a.y - b.y) >= possible.height * 0.8:
                    continue
                return False
            elif item[0] == "re":
                rect = pymupdf.Rect(item[1])
                if rect.height <= 1 and rect.width >= possible.width * 0.8:
                    continue
                if rect.width <= 1 and rect.height >= possible.height * 0.8:
                    continue
                if rect.intersects(possible) and not rect.contains(possible):
                    return False
            else:
                return False
    try:
        pixels = page.get_pixmap(
            clip=strip, colorspace=pymupdf.csGRAY, alpha=False
        ).samples
    except (ValueError, RuntimeError):
        return False
    return bool(pixels) and min(pixels) >= 240 and max(pixels) - min(pixels) <= 3


def pdf_table_rows(page, table):
    return [
        [
            page.get_text("text", clip=cell, sort=True).strip() if cell else ""
            for cell in row.cells
        ]
        for row in table.rows
    ]


def extract_pdf(data, filename):
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        if pdf.needs_pass or len(pdf) > 60:
            raise ValueError("PDF is encrypted or exceeds 60 pages.")
        paragraphs, risk_rows, table_groups, table_positions = [], [], [], []
        columns = None
        last_items = {}
        reliable = True
        for page in pdf:
            detected = page.find_tables(
                strategy="lines_strict", use_layout=False
            ).tables
            tutor_tables = [
                t
                for t in detected
                if "tutorsignoff"
                in normalise(" ".join(str(v or "") for v in t.extract()[0]))
            ]
            paragraphs.extend(pdf_paragraphs(page, tutor_tables, detected))
            for source_index, paragraph in enumerate(paragraphs):
                paragraph["source_index"] = source_index
            header = next(
                (
                    t
                    for t in detected
                    if len(
                        [
                            cell
                            for cell, value in zip(
                                t.rows[0].cells, t.extract()[0], strict=True
                            )
                            if cell and (value or "").strip()
                        ]
                    )
                    == 9
                    and "hazard"
                    in " ".join(str(v or "") for v in t.extract()[0]).casefold()
                    and "severity"
                    in " ".join(str(v or "") for v in t.extract()[0]).casefold()
                ),
                None,
            )
            if header:
                cells = [
                    cell
                    for cell, value in zip(
                        header.rows[0].cells, header.extract()[0], strict=True
                    )
                    if cell and (value or "").strip()
                ]
                columns = [cell[0] for cell in cells] + [cells[-1][2]]
                bounds = list(header.bbox)
                horizontal_edges = sorted(
                    {edge for row in header.rows for edge in (row.bbox[1], row.bbox[3])}
                )
                saw_item = False
                row_limit = len(header.rows)
                for index, (row, values) in enumerate(
                    zip(header.rows[1:], header.extract()[1:], strict=True), 1
                ):
                    saw_item |= bool(
                        re.fullmatch(r"[A-Za-z]*\d+[.)]?", (values[0] or "").strip())
                    )
                    end_label = re.match(
                        r"^(?:Does this risk assessment|To be completed|Student Name\s*:|Supervisor Name\s*:|Manual Handling\s*:)",
                        " ".join(value or "" for value in values).strip(),
                        re.I,
                    )
                    if (
                        saw_item
                        and end_label
                        and any(
                            cell and cell[2] - cell[0] > (bounds[2] - bounds[0]) * 0.95
                            for cell in row.cells
                        )
                    ):
                        bounds[3] = row.bbox[1]
                        row_limit = index
                        break
                if header.col_count == 9:
                    rows = pdf_table_rows(page, header)[:row_limit]
                else:
                    aligned = page.find_tables(
                        clip=bounds,
                        vertical_strategy="explicit",
                        vertical_lines=columns,
                        horizontal_strategy="lines_strict",
                        use_layout=False,
                    ).tables
                    rows = [
                        row
                        for table in aligned
                        if table.col_count == 9
                        for row in pdf_table_rows(page, table)
                    ]
                    if not rows:
                        aligned = page.find_tables(
                            clip=bounds,
                            vertical_strategy="explicit",
                            vertical_lines=columns,
                            horizontal_strategy="explicit",
                            horizontal_lines=[
                                y
                                for y in horizontal_edges
                                if bounds[1] <= y <= bounds[3]
                            ],
                            use_layout=False,
                        ).tables
                        rows = [
                            row
                            for table in aligned
                            if table.col_count == 9
                            for row in pdf_table_rows(page, table)
                        ]
                if not rows:
                    reliable = False
                    columns = None
                    continue
                if not risk_rows:
                    risk_rows.append([value or "" for value in rows[0]])
                table_groups.append([[value or "" for value in rows[0]]])
                table_positions.append(
                    next(
                        (
                            i
                            for i, p in enumerate(paragraphs)
                            if p.get("page") == page.number + 1
                            and p.get("pdf_bbox", [0, 0])[1] >= header.bbox[1]
                        ),
                        len(paragraphs) - 1,
                    )
                )
                rows = rows[1:]
                if (
                    rows
                    and re.fullmatch(r"[A-Za-z]*1[.)]?", (rows[0][0] or "").strip())
                    and re.search(r"Area\s*/\s*Activity\s*:", page.get_text(), re.I)
                ):
                    last_items = {}
            elif columns:
                continuation = page.find_tables(
                    vertical_strategy="explicit",
                    vertical_lines=columns,
                    horizontal_strategy="lines_strict",
                    use_layout=False,
                ).tables
                rows = [
                    row
                    for table in continuation
                    if table.col_count == 9
                    for row in pdf_table_rows(page, table)
                ]
            else:
                continue
            found = False
            for row in rows:
                row = [" ".join((value or "").split()) for value in row]
                if (
                    header
                    and not last_items
                    and not any(row[1:])
                    and normalise(row[0]) in {"item", "no", "itemno"}
                ):
                    continue
                identifier = re.fullmatch(r"([A-Za-z]*)(\d+)[.)]?", row[0])
                section_heading = not any(row[1:]) and re.match(
                    r"^(?:[A-Za-z][.)]\s+|(?:Section|Part)\s+[A-Za-z0-9]+\b)",
                    row[0],
                    re.I,
                )
                if section_heading:
                    continue
                if identifier:
                    prefix, number = identifier[1].upper(), int(identifier[2])
                    if number != last_items.get(prefix, 0) + 1:
                        reliable = False
                    risk_rows.append(row)
                    table_groups[-1].append(row)
                    last_items[prefix] = number
                    found = True
                elif last_items and not row[0] and row[2] and row[7]:
                    # A continuation hazard in the same bounded nine-column table.
                    risk_rows.append(row)
                    table_groups[-1].append(row)
                    found = True
                elif (
                    last_items
                    and row[7]
                    and all(not value for i, value in enumerate(row) if i != 7)
                ):
                    risk_rows[-1][7] += " " + row[7]
                    found = True
                elif header and any(row):
                    reliable = False
            if not found and not header:
                columns = None
        return {
            "filename": filename,
            "kind": "pdf",
            "paragraphs": paragraphs,
            "tables": [table for table in table_groups if len(table) > 1],
            "table_positions": [
                position
                for table, position in zip(table_groups, table_positions, strict=True)
                if len(table) > 1
            ],
            "pages": len(pdf),
            "pdf_reader_version": 9,
            "highlight_reader_version": 1,
            "risk_table_reliable": reliable,
            "text_coverage_reliable": all(
                len(page.get_text().strip()) >= 100
                and not any(
                    pymupdf.Rect(img["bbox"]).get_area() > page.rect.get_area() * 0.7
                    for img in page.get_image_info()
                )
                for page in pdf
            ),
        }


def extract_document(data, filename):
    legacy = filename.lower().endswith(".doc")
    if legacy:
        from .legacy_word import convert_legacy_doc

        data = convert_legacy_doc(data)
    doc = (
        extract_docx(data, filename)
        if legacy or filename.lower().endswith(".docx")
        else extract_pdf(data, filename)
    )
    if legacy:
        doc["converted_from"] = "doc"
    if sum(len(p["text"]) for p in doc["paragraphs"]) > 150_000:
        raise ValueError("Document text is too large for this review workflow.")
    return doc
