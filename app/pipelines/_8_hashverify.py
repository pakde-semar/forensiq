"""
Hash Verify pipeline module — batch re-verify all evidence file integrity.
"""
import logging
from pathlib import Path

MODULE_NAME  = "hashverify"
MODULE_LABEL = "Hash Verify"
MODULE_ICON  = "fa-shield-check"

log = logging.getLogger(__name__)


def run(context: dict) -> dict:
    from ..core.hashing import hash_file

    case = context.get("case")
    if not case:
        return {"status": "skipped", "findings": []}

    findings  = []
    ok = tampered = missing = no_hash = 0

    for ev in (case.evidence or []):
        fp = Path(ev.file_path) if ev.file_path else None
        if not fp or not fp.exists():
            missing += 1
            findings.append({"type": "warning",
                              "title": f"MISSING: {ev.evidence_number} — {ev.file_name}",
                              "detail": "File not found on disk"})
            continue

        if not ev.md5 and not ev.sha256:
            no_hash += 1
            continue

        try:
            md5, sha256 = hash_file(fp)
            md5_ok  = (not ev.md5)    or ev.md5    == md5
            sha_ok  = (not ev.sha256) or ev.sha256 == sha256
            if md5_ok and sha_ok:
                ok += 1
            else:
                tampered += 1
                findings.append({"type": "critical",
                                  "title": f"TAMPERED: {ev.evidence_number} — {ev.file_name}",
                                  "detail": f"Hash mismatch detected"})
        except Exception as e:
            findings.append({"type": "error",
                              "title": f"ERROR: {ev.evidence_number}", "detail": str(e)})

    total = ok + tampered + missing + no_hash
    if total == 0:
        return {"status": "skipped", "findings": [
            {"type": "info", "title": "No evidence files to verify", "detail": ""}
        ]}

    status = "done"
    if tampered:
        status = "error"

    summary = f"{ok} OK, {tampered} TAMPERED, {missing} MISSING, {no_hash} NO HASH"
    if not findings:
        findings = [{"type": "info", "title": f"All {ok} file(s) intact", "detail": ""}]

    return {
        "status":   status,
        "findings": findings,
        "notes":    f"\n\n### Hash Verify — {summary}\n" +
                    "\n".join(f"- **{f['title']}**" for f in findings
                               if f["type"] in ("critical", "warning")),
    }
