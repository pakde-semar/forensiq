import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse, Response, JSONResponse
from ..templates_env import templates as _shared_templates
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..core import audit
from ..routers.agency import get_or_create_agency

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/evidence/{ev_id}/coc",
    tags=["coc"],
)
templates = _shared_templates

REPORTS_ROOT = Path("reports")

COC_ACTIONS = ["received", "transferred", "examined", "returned", "stored", "disposed"]
COC_METHODS = ["in-person", "courier", "digital", "secure-transport"]


@router.post("/add")
def coc_add_entry(
    case_id: int,
    ev_id: int,
    action:      str = Form("received"),
    released_by: str = Form(""),
    received_by: str = Form(""),
    purpose:     str = Form(""),
    location:    str = Form(""),
    method:      str = Form(""),
    notes:       str = Form(""),
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if not ev:
        return RedirectResponse(f"/cases/{case_id}#tab-evidence", status_code=303)

    entry = models.CoCEntry(
        evidence_id = ev_id,
        action      = action,
        released_by = released_by.strip(),
        received_by = received_by.strip(),
        purpose     = purpose.strip(),
        location    = location.strip(),
        method      = method,
        notes       = notes.strip(),
        timestamp   = datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    audit.log(db, case_id,
              f"CoC entry added for {ev.evidence_number}: {action} — {received_by or released_by}",
              investigator=investigator, app_name="CoC")
    return RedirectResponse(f"/cases/{case_id}#tab-evidence", status_code=303)


@router.get("/entries")
def coc_entries(case_id: int, ev_id: int, db: Session = Depends(get_db)):
    """Return CoC entries as JSON for inline display."""
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if not ev:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse({
        "evidence_number": ev.evidence_number,
        "coc_number":      ev.coc_number,
        "file_name":       ev.file_name,
        "entries": [
            {
                "id":          e.id,
                "timestamp":   e.timestamp.strftime("%Y-%m-%d %H:%M"),
                "action":      e.action,
                "released_by": e.released_by,
                "received_by": e.received_by,
                "purpose":     e.purpose,
                "location":    e.location,
                "method":      e.method,
                "notes":       e.notes,
            }
            for e in ev.coc_entries
        ],
    })


@router.get("/pdf")
def coc_pdf(case_id: int, ev_id: int, db: Session = Depends(get_db)):
    """Generate and download Chain of Custody PDF for one evidence item."""
    case   = db.query(models.Case).filter_by(id=case_id).first()
    ev     = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    agency = get_or_create_agency(db)

    if not case or not ev:
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    html = templates.get_template("reports/coc_report.html").render({
        "case":         case,
        "ev":           ev,
        "agency":       agency,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "COC_ACTIONS":  COC_ACTIONS,
    })

    pdf_bytes = None
    try:
        from weasyprint import HTML as WP_HTML
        pdf_bytes = WP_HTML(string=html, base_url=".").write_pdf()
    except Exception as e:
        log.error("CoC PDF generation failed: %s", e)

    if pdf_bytes:
        fname = f"CoC_{ev.coc_number}_{ev.evidence_number}.pdf"
        audit.log(db, case_id, f"CoC PDF downloaded: {ev.evidence_number}",
                  app_name="CoC")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    # Fallback: serve HTML
    fname = f"CoC_{ev.coc_number}_{ev.evidence_number}.html"
    return Response(
        content=html.encode(),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
