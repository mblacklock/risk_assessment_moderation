"""Bounded previews of Word freehand paths; no handwriting recognition."""

import math
from xml.etree import ElementTree as ET

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"


def drawings(body):
    return [n for n in body.iter() if n.tag in {WP + "anchor", WP + "inline"}]


def drawing_png(node):
    """Render supported numeric freeform geometry, rejecting other drawing types."""
    import pymupdf

    extent = node.find(WP + "extent")
    if extent is None or node.find(".//" + A + "blip") is not None:
        raise ValueError("Not a freeform drawing")
    transform = node.find(".//" + A + "xfrm")
    if transform is not None and any(
        transform.get(key, "0") not in {"0", "false"}
        for key in ("rot", "flipH", "flipV")
    ):
        raise ValueError("Unsupported drawing transform")
    width, height = [float(extent.get(key, "0")) / 12700 for key in ("cx", "cy")]
    if not (6 < width <= 250 and 4 < height <= 100):
        raise ValueError("Drawing is outside supported signature dimensions")
    paths = node.findall(".//" + A + "custGeom/" + A + "pathLst/" + A + "path")
    if not paths or sum(len(path) for path in paths) > 4000:
        raise ValueError("Unsupported drawing geometry")
    elements = []
    curves = 0
    for path in paths:
        sx, sy = width / float(path.get("w", "0")), height / float(path.get("h", "0"))
        commands = []
        for command in path:
            kind = command.tag.removeprefix(A)
            code, count = {
                "moveTo": ("M", 1),
                "lnTo": ("L", 1),
                "cubicBezTo": ("C", 3),
                "quadBezTo": ("Q", 2),
                "close": ("Z", 0),
            }.get(kind, (None, -1))
            points = command.findall(A + "pt")
            if code is None or len(points) != count:
                raise ValueError("Unsupported path command")
            values = [
                value
                for point in points
                for value in (
                    float(point.get("x")) * sx + 3,
                    float(point.get("y")) * sy + 3,
                )
            ]
            if any(not math.isfinite(v) or abs(v) > 2000 for v in values):
                raise ValueError("Invalid path coordinate")
            commands.append(code + " ".join(str(v) for v in values))
            curves += kind in {"cubicBezTo", "quadBezTo"}
        elements.append('<path d="' + " ".join(commands) + '"/>')
    if curves < 3:
        raise ValueError(
            "A simple line or decoration does not establish signature presence"
        )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width + 6}" height="{height + 6}"><g fill="none" stroke="#15243c" stroke-width="1">'
        + "".join(elements)
        + "</g></svg>"
    )
    with pymupdf.open(stream=svg.encode(), filetype="svg") as doc:
        return doc[0].get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=True).tobytes("png")


def word_drawing_png(data, index):
    from .documents import NS, bounded_zip

    with bounded_zip(data, 80 * 1024 * 1024) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        return drawing_png(drawings(root.find("w:body", NS))[index])
