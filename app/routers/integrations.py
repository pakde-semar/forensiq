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
