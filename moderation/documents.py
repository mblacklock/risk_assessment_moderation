"""Bounded document extraction. Uploaded archive paths are never extracted."""

import io
import posixpath
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

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
    return "".join(node.text or "" for node in element.findall(".//w:t", NS)).strip()


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
            if suffix not in {".pdf", ".docx"}:
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
                "No Word (.docx) or PDF submissions were found in this ZIP."
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
        paragraphs = []
        for p in body.findall(".//w:p", NS):
            text = texts[p]
            images = []
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
                paragraphs.append({"text": text, "images": images, "states": states})
        tables = []
        for table in body.findall(".//w:tbl", NS):
            rows = []
            for row in table.findall("w:tr", NS):
                rows.append(
                    [
                        "\n".join(texts[p] for p in cell.findall(".//w:p", NS)).strip()
                        for cell in row.findall("w:tc", NS)
                    ]
                )
            tables.append(rows)
        return {
            "filename": filename,
            "kind": "docx",
            "paragraphs": paragraphs,
            "tables": tables,
            "pages": None,
        }


def extract_pdf(data, filename):
    import pymupdf

    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        if pdf.needs_pass or len(pdf) > 60:
            raise ValueError("PDF is encrypted or exceeds 60 pages.")
        paragraphs = []
        for page in pdf:
            for line in page.get_text().splitlines():
                if line.strip():
                    paragraphs.append(
                        {"text": line.strip(), "images": [], "states": []}
                    )
        return {
            "filename": filename,
            "kind": "pdf",
            "paragraphs": paragraphs,
            "tables": [],
            "pages": len(pdf),
        }


def extract_document(data, filename):
    doc = (
        extract_docx(data, filename)
        if filename.lower().endswith(".docx")
        else extract_pdf(data, filename)
    )
    if sum(len(p["text"]) for p in doc["paragraphs"]) > 150_000:
        raise ValueError("Document text is too large for this review workflow.")
    return doc
