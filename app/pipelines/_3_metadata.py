"""
Metadata Extract — run exiftool on an evidence file and surface interesting fields.
"""
import json
import shutil
import subprocess
from pathlib import Path

MODULE_NAME  = "metadata"
MODULE_LABEL = "Metadata Extract"
MODULE_ICON  = "fa-file-circle-info"

_INTERESTING = {
    "GPSLatitude", "GPSLongitude", "GPSAltitude", "GPSPosition",
    "Author", "Creator", "LastModifiedBy", "Company",
    "Software", "CreateDate", "ModifyDate", "DateTimeOriginal",
    "Make", "Model", "SerialNumber", "LensModel",
    "Comment", "Description", "Subject", "Title",
    "Copyright", "Producer", "XMPToolkit",
}


def run(context: dict) -> dict:
    evidence = context.get("evidence")
    if not evidence:
        return {"status": "skipped", "findings": [{"type": "info", "title": "No evidence file in context", "detail": ""}]}

    fpath = Path(evidence.file_path) if evidence.file_path else None
    if not fpath or not fpath.exists():
        return {"status": "skipped", "findings": [{"type": "info", "title": "File not on disk", "detail": str(fpath)}]}

    if not shutil.which("exiftool"):
        return {"status": "skipped", "findings": [{"type": "info", "title": "exiftool not available", "detail": ""}]}

    try:
        result = subprocess.run(
            ["exiftool", "-json", str(fpath)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout or "[]")
        if not data:
            return {"status": "done", "findings": [{"type": "info", "title": "No metadata extracted", "detail": ""}]}

        tags = data[0]
        findings: list[dict] = []
        has_gps = False

        for key, val in tags.items():
            clean_key = key.split(":")[-1] if ":" in key else key
            if clean_key in _INTERESTING:
                ftype = "warning" if "GPS" in clean_key else "info"
                if "GPS" in clean_key:
                    has_gps = True
                findings.append({
                    "type":   ftype,
                    "title":  f"{clean_key}: {str(val)[:120]}",
                    "detail": "",
                })

        if not findings:
            return {"status": "done", "findings": [{"type": "info", "title": "No interesting metadata", "detail": ""}]}

        notes_lines = [f"\n\n### Metadata: {evidence.file_name}"]
        for f in findings:
            prefix = "⚠️" if f["type"] == "warning" else "·"
            notes_lines.append(f"  {prefix} {f['title']}")
        if has_gps:
            notes_lines.append("  ⚠️ **GPS coordinates found — potential device location leak**")

        return {"status": "done", "findings": findings, "notes": "\n".join(notes_lines)}

    except subprocess.TimeoutExpired:
        return {"status": "error", "findings": [{"type": "warning", "title": "exiftool timed out", "detail": ""}]}
    except Exception as e:
        return {"status": "error", "findings": [{"type": "warning", "title": "Metadata extract failed", "detail": str(e)}]}
