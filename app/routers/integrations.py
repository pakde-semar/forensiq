from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models
from ..core import audit
from ..integrations import flowintel as fw
from ..integrations import misp as mp

router = APIRouter(prefix="/cases/{case_id}/integrations", tags=["integrations"])
templates = Jinja2Templates(directory="app/templates")


# ─── Flowintel ───────────────────────────────────────────────────────────────

@router.post("/flowintel/link")
def flowintel_link(
    case_id: int,
    flowintel_case_id: int = Form(...),
    investigator: str     = Form(""),
    db: Session = Depends(get_db),
):
    """Link this ForensiQ case to an existing Flowintel case."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case:
        case.flowintel_case_id = flowintel_case_id
        db.commit()
        audit.log(db, case_id,
                  f"Linked to Flowintel case #{flowintel_case_id}",
                  investigator=investigator, app_name="Flowintel")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/flowintel/create")
def flowintel_create(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create a new Flowintel case from this ForensiQ case and link it."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    result = fw.create_case(
        title      = f"[{case.case_number}] {case.name}",
        description= case.notes or "",
    )
    if result and result.get("id"):
        case.flowintel_case_id = result["id"]
        db.commit()
        audit.log(db, case_id,
                  f"Created Flowintel case #{result['id']} from ForensiQ",
                  investigator=investigator, app_name="Flowintel")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/flowintel/sync")
def flowintel_sync(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Pull latest notes + FIR suggestion from Flowintel into ForensiQ."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case or not case.flowintel_case_id:
        return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)

    notes, suggestion = fw.sync_notes_to_forensiq(case.flowintel_case_id)

    # Append Flowintel notes as a block (don't overwrite existing)
    sep  = "\n\n---\n**[Flowintel sync]**\n"
    if notes:
        case.notes = (case.notes or "").rstrip() + sep + notes
        db.commit()

    msg = "Synced notes from Flowintel"
    if suggestion:
        msg += f" | FIR suggestion: {suggestion['decision']} (score {suggestion['score']})"
    audit.log(db, case_id, msg, investigator=investigator, app_name="Flowintel")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.get("/flowintel/observables")
def flowintel_observables(case_id: int, request: Request, db: Session = Depends(get_db)):
    """Return Flowintel observables as JSON fragment for HTMX."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case or not case.flowintel_case_id:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "not linked"}, status_code=400)
    obs = fw.get_observables(case.flowintel_case_id)
    from fastapi.responses import JSONResponse
    return JSONResponse({"observables": obs})


# ─── MISP ────────────────────────────────────────────────────────────────────

@router.post("/misp/link")
def misp_link(
    case_id: int,
    misp_event_id: str = Form(...),
    investigator: str  = Form(""),
    db: Session = Depends(get_db),
):
    """Link this case to an existing MISP event."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case:
        case.misp_event_id = misp_event_id.strip()
        db.commit()
        audit.log(db, case_id,
                  f"Linked to MISP event {misp_event_id}",
                  investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/misp/create")
def misp_create(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Create a new MISP draft event from this case and link it."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    event = mp.create_event(
        title=f"[ForensiQ {case.case_number}] {case.name}",
    )
    if event and event.get("id"):
        case.misp_event_id = str(event["id"])
        db.commit()
        audit.log(db, case_id,
                  f"Created MISP event #{event['id']}",
                  investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/misp/pull_iocs")
def misp_pull_iocs(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Pull IOCs from linked MISP event and append to case notes."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case or not case.misp_event_id:
        return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)

    iocs = mp.get_iocs_from_event(case.misp_event_id)
    if iocs:
        lines = [f"\n\n---\n**[MISP IOCs — event {case.misp_event_id}]**"]
        lines.append("| Type | Value | Category | Comment |")
        lines.append("|------|-------|----------|---------|")
        for ioc in iocs:
            lines.append(f"| {ioc['type']} | `{ioc['value']}` | {ioc['category']} | {ioc['comment']} |")
        case.notes = (case.notes or "").rstrip() + "\n".join(lines)
        db.commit()
        audit.log(db, case_id,
                  f"Pulled {len(iocs)} IOCs from MISP event {case.misp_event_id}",
                  investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/misp/push_hash")
def misp_push_hash(
    case_id: int,
    ev_id: int         = Form(...),
    investigator: str  = Form(""),
    db: Session = Depends(get_db),
):
    """Push evidence file hash to linked MISP event."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    ev   = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if not case or not ev or not case.misp_event_id:
        return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)

    ok = mp.add_ioc_to_event(
        case.misp_event_id,
        ioc_type  = "md5",
        ioc_value = ev.md5,
        comment   = f"{ev.file_name} ({ev.evidence_number})",
    )
    if ok and ev.sha256:
        mp.add_ioc_to_event(
            case.misp_event_id,
            ioc_type  = "sha256",
            ioc_value = ev.sha256,
            comment   = f"{ev.file_name} ({ev.evidence_number})",
        )
    audit.log(db, case_id,
              f"Pushed hashes for {ev.file_name} to MISP event {case.misp_event_id}"
              + (" ✓" if ok else " (failed)"),
              investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/misp/publish")
def misp_publish(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Publish the linked MISP event."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case and case.misp_event_id:
        ok = mp.publish_event(case.misp_event_id)
        audit.log(db, case_id,
                  f"MISP event {case.misp_event_id} {'published ✓' if ok else 'publish failed'}",
                  investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/misp/unlink")
def misp_unlink(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Remove the MISP event link from this case."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case and case.misp_event_id:
        old = case.misp_event_id
        case.misp_event_id = ""
        db.commit()
        audit.log(db, case_id, f"Unlinked MISP event {old}",
                  investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.get("/misp/event-detail")
def misp_event_detail(case_id: int, db: Session = Depends(get_db)):
    """Return linked MISP event details as JSON for inline display."""
    from fastapi.responses import JSONResponse
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case or not case.misp_event_id:
        return JSONResponse({"error": "not linked"}, status_code=400)
    event = mp.get_event(case.misp_event_id)
    if not event:
        return JSONResponse({"error": "Event not found or MISP unreachable"}, status_code=404)
    return JSONResponse({
        "id":          event.get("id"),
        "uuid":        event.get("uuid", ""),
        "info":        event.get("info", ""),
        "date":        event.get("date", ""),
        "published":   event.get("published", False),
        "orgc":        event.get("Orgc", {}).get("name", ""),
        "attr_count":  event.get("attribute_count", len(event.get("Attribute", []))),
        "tags":        [t.get("name", "") for t in event.get("Tag", [])],
        "threat_level": event.get("threat_level_id", ""),
        "analysis":    event.get("analysis", ""),
        "distribution": event.get("distribution", ""),
        "url":         mp.event_url(case.misp_event_id),
    })


@router.post("/misp/push_iocs")
def misp_push_iocs(
    case_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Extract IOCs from case notes + evidence, then push to linked MISP event."""
    import re
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case or not case.misp_event_id:
        return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)

    # Collect text to extract from
    text_parts = [case.notes or ""]
    for ev in case.evidence:
        text_parts.append(ev.notes or "")
        text_parts.append(ev.file_name or "")
        if ev.md5:
            text_parts.append(ev.md5)
        if ev.sha256:
            text_parts.append(ev.sha256)
    text = "\n".join(text_parts)

    _PRIVATE = re.compile(
        r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.0\.0\.0|::1)"
    )
    patterns = {
        "IPv4":   re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "Domain": re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"),
        "URL":    re.compile(r"https?://[^\s\"'<>]+"),
        "MD5":    re.compile(r"\b[0-9a-fA-F]{32}\b"),
        "SHA256": re.compile(r"\b[0-9a-fA-F]{64}\b"),
        "SHA1":   re.compile(r"\b[0-9a-fA-F]{40}\b"),
        "Email":  re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
        "CVE":    re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.I),
    }

    iocs: list[dict] = []
    seen: set[str] = set()
    for ioc_type, pat in patterns.items():
        for m in pat.finditer(text):
            val = m.group(0).rstrip(".,;)")
            if val in seen:
                continue
            if ioc_type == "IPv4" and _PRIVATE.match(val):
                continue
            seen.add(val)
            iocs.append({"type": ioc_type, "value": val})

    pushed, skipped = mp.bulk_add_iocs(
        case.misp_event_id, iocs,
        comment_prefix=f"ForensiQ {case.case_number}"
    )
    audit.log(db, case_id,
              f"Pushed {pushed} IOCs to MISP event {case.misp_event_id} "
              f"({skipped} skipped)",
              investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.post("/misp/add_tag")
def misp_add_tag(
    case_id: int,
    tag: str      = Form(...),
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    """Add a tag to the linked MISP event."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case and case.misp_event_id and tag.strip():
        ok = mp.add_tag_to_event(case.misp_event_id, tag.strip())
        audit.log(db, case_id,
                  f"Tag '{tag}' {'added to' if ok else 'failed on'} MISP event {case.misp_event_id}",
                  investigator=investigator, app_name="MISP")
    return RedirectResponse(f"/cases/{case_id}#tab-integrations", status_code=303)


@router.get("/misp/search")
def misp_search(case_id: int, q: str = "", db: Session = Depends(get_db)):
    """Search MISP events by value and return JSON."""
    from fastapi.responses import JSONResponse
    if not q.strip():
        return JSONResponse({"results": []})
    results = mp.search_events_by_value(q.strip(), limit=10)
    return JSONResponse({"results": [
        {
            "id":        e.get("id"),
            "info":      e.get("info", ""),
            "date":      e.get("date", ""),
            "orgc":      e.get("Orgc", {}).get("name", "") if isinstance(e.get("Orgc"), dict) else "",
            "attr_count": e.get("attribute_count", "?"),
            "url":       mp.event_url(e.get("id", "")),
        }
        for e in results
    ]})
