"""Local legacy Word conversion. Original submissions are never modified."""

import base64
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $word.Options.UpdateLinksAtOpen = $false
    [object]$sourcePath = $env:RA_DOC_SOURCE
    [object]$targetPath = $env:RA_DOC_TARGET
    [object]$no = $false
    [object]$yes = $true
    [object]$format = 16
    $document = $word.Documents.Open([ref]$sourcePath, [ref]$no, [ref]$yes, [ref]$no)
    $document.SaveAs2([ref]$targetPath, [ref]$format)
} finally {
    [object]$discard = 0
    if ($null -ne $document) { $document.Close([ref]$discard); [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($document) }
    if ($null -ne $word) { $word.Quit([ref]$discard); [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
}
"""


def convert_legacy_doc(data):
    """Use installed Microsoft Word with macros disabled, caching the DOCX locally."""
    from django.conf import settings

    if os.name != "nt":
        raise ValueError(
            "Legacy .doc needs Microsoft Word on Windows. Save a copy as .docx or PDF and upload it."
        )
    cache = settings.REVIEW_ROOT / ".converted-docx"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (hashlib.sha256(data).hexdigest() + ".docx")
    if target.exists():
        return target.read_bytes()
    with tempfile.TemporaryDirectory(prefix="legacy-", dir=cache) as folder:
        source = Path(folder) / "original.doc"
        converted = Path(folder) / "converted.docx"
        source.write_bytes(data)
        env = {
            **os.environ,
            "RA_DOC_SOURCE": str(source.resolve()),
            "RA_DOC_TARGET": str(converted.resolve()),
        }
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii"),
                ],
                env=env,
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError(
                "Legacy Word conversion did not finish. Save this .doc as .docx or PDF and retry."
            ) from error
        if result.returncode or not converted.exists():
            raise ValueError(
                "Could not convert legacy .doc with Microsoft Word. Save it as .docx or PDF and retry."
            )
        payload = converted.read_bytes()
        if len(payload) > 80 * 1024 * 1024:
            raise ValueError("Converted Word document is too large.")
        target.write_bytes(payload)
    return payload
