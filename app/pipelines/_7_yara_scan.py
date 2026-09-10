"""
Yara Scan pipeline module — scan all case evidence files against enabled rules.
"""
import json
import logging
import time
from pathlib import Path

MODULE_NAME  = "yara_scan"
MODULE_LABEL = "Yara Scan"
MODULE_ICON  = "fa-shield-halved"

log = logging.getLogger(__name__)


def run(context: dict) -> dict:
    try:
        import yara
    except ImportError:
        return {"status": "skipped", "findings": [{"type": "warning",
                "title": "yara-python not installed", "detail": "pip install yara-python"}]}

    case = context.get("case")
    if not case:
        return {"status": "skipped", "findings": []}

    from ..database import SessionLocal
    from .. import models as m

    db = SessionLocal()
    try:
        rules_src = db.query(m.YaraRule).filter_by(enabled=1).all()
        if not rules_src:
            return {"status": "skipped", "findings": [
                {"type": "info", "title": "No enabled Yara rules", "detail": "Add rules at /yara"}
            ]}

        sources: dict[str, str] = {}
        for r in rules_src:
            try:
                yara.compile(source=r.content)
                sources[f"ns_{r.id}"] = r.content
            except yara.SyntaxError:
                pass

        if not sources:
            return {"status": "skipped", "findings": [
                {"type": "warning", "title": "All rules have syntax errors", "detail": ""}
            ]}

        compiled = yara.compile(sources=sources)
        findings: list[dict] = []
        match_count = 0

        for ev in (case.evidence or []):
            fp = Path(ev.file_path) if ev.file_path else None
            if not fp or not fp.exists():
                continue
            try:
                matches = compiled.match(str(fp), timeout=30)
                for match in matches:
                    match_count += 1
                    findings.append({
                        "type":   "critical" if "critical" in match.tags else "warning",
                        "title":  f"[{ev.evidence_number}] {match.rule}",
                        "detail": f"File: {ev.file_name}",
                    })
            except yara.TimeoutError:
                findings.append({"type": "info", "title": f"Scan timeout: {ev.file_name}", "detail": ""})
            except Exception as e:
                log.warning("Yara scan error on %s: %s", ev.file_path, e)

    finally:
        db.close()

    if match_count == 0:
        return {
            "status":   "done",
            "findings": [{"type": "info", "title": "No Yara matches found", "detail": ""}],
        }

    return {
        "status":   "done",
        "findings": findings,
        "notes":    f"\n\n### Yara Scan — {match_count} match(es)\n" +
                    "\n".join(f"- **{f['title']}**" for f in findings),
    }
