"""
Pipeline module — push extracted IOCs to the linked MISP event.
Runs after ioc_extract (expects context["iocs"]).
"""
import time
import logging

log = logging.getLogger(__name__)

_LABEL = "MISP Push"


def run(context: dict) -> dict:
    case = context.get("case")
    t0 = time.monotonic()
    findings: list[dict] = []
    notes = ""

    if not case.misp_event_id:
        return {
            "label":    _LABEL,
            "status":   "skipped",
            "ms":       0,
            "findings": [{"type": "info", "title": "No MISP event linked — skipping"}],
            "notes":    "",
        }

    iocs: list[dict] = context.get("iocs", [])
    if not iocs:
        return {
            "label":    _LABEL,
            "status":   "skipped",
            "ms":       0,
            "findings": [{"type": "info", "title": "No IOCs from previous modules"}],
            "notes":    "",
        }

    try:
        from ..integrations import misp as mp
        pushed, skipped = mp.bulk_add_iocs(
            case.misp_event_id,
            iocs,
            comment_prefix=f"ForensiQ {case.case_number} [pipeline]",
        )
        ms = int((time.monotonic() - t0) * 1000)

        if pushed:
            findings.append({
                "type":   "info",
                "title":  f"{pushed} IOC(s) pushed to MISP event #{case.misp_event_id}",
                "detail": f"{skipped} skipped (unsupported type or error)",
            })
            notes = (
                f"**MISP Push** — {pushed} IOCs pushed to event #{case.misp_event_id} "
                f"({skipped} skipped)."
            )
        else:
            findings.append({
                "type":  "warning",
                "title": f"No IOCs pushed ({skipped} skipped)",
            })

        return {
            "label":    _LABEL,
            "status":   "done",
            "ms":       ms,
            "findings": findings,
            "notes":    notes,
        }

    except Exception as e:
        log.exception("misp_push failed")
        return {
            "label":    _LABEL,
            "status":   "error",
            "ms":       int((time.monotonic() - t0) * 1000),
            "findings": [{"type": "critical", "title": f"Error: {e}"}],
            "notes":    "",
        }
