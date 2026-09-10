from fastapi import APIRouter, BackgroundTasks, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
import shutil
from ..database import get_db
from .. import models
from ..core import audit
from ..core.hashing import hash_file, verify_file
from ..core.coc import next_coc_number, next_evidence_number
from ..core.pipeline import trigger_auto

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["evidence"])
templates = Jinja2Templates(directory="app/templates")

UPLOAD_ROOT = Path("uploads")


def _evidence_dir(case_id: int, category: str) -> Path:
    safe_cat = category.replace("/", "_").replace(" ", "_")
    p = UPLOAD_ROOT / str(case_id) / safe_cat
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/upload")
async def evidence_upload(
    case_id:    int,
    category:   str        = Form(models.EvidenceCategory.other),
    submitter:  str        = Form(""),
    notes:      str        = Form(""),
    orig_loc:   str        = Form(""),
    file:       UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return JSONResponse({"error": "case not found"}, status_code=404)

    dest_dir  = _evidence_dir(case_id, category)
    dest_path = dest_dir / file.filename

    # Write file
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    size          = dest_path.stat().st_size
    md5, sha256   = hash_file(dest_path)
    ev_num        = next_evidence_number(case_id, db)
    coc_num       = next_coc_number(case_id, db)

    ev = models.Evidence(
        case_id           = case_id,
        evidence_number   = ev_num,
        coc_number        = coc_num,
        file_name         = file.filename,
        file_path         = str(dest_path),
        file_size         = size,
        category          = category,
        original_location = orig_loc,
        submitter         = submitter,
        md5               = md5,
        sha256            = sha256,
        notes             = notes,
    )
    db.add(ev)
    db.commit()
    audit.log(db, case_id,
              f"EVIDENCE ADDED: {file.filename} → {ev_num} ({coc_num})",
              investigator=submitter, app_name="Evidence")

    # Trigger auto-run pipelines in background
    trigger_auto("evidence_upload", case_id, ev.id, background_tasks)

    return RedirectResponse(f"/cases/{case_id}#evidence", status_code=303)


@router.post("/{ev_id}/verify")
def evidence_verify(
    case_id: int, ev_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if ev and Path(ev.file_path).exists():
        ok = verify_file(ev.file_path, ev.md5, ev.sha256)
        ev.verified_at = datetime.utcnow()
        db.commit()
        status = "INTEGRITY OK" if ok else "INTEGRITY FAIL — file may be tampered"
        audit.log(db, case_id,
                  f"EVIDENCE VERIFY: {ev.file_name} — {status}",
                  investigator=investigator, app_name="Evidence")
    return RedirectResponse(f"/cases/{case_id}#evidence", status_code=303)


@router.post("/{ev_id}/notes")
def evidence_update_notes(
    case_id: int, ev_id: int,
    notes: str = Form(""),
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if ev:
        ev.notes = notes
        db.commit()
        audit.log(db, case_id, f"EVIDENCE NOTES: {ev.file_name} updated",
                  investigator=investigator, app_name="Evidence")
    return RedirectResponse(f"/cases/{case_id}#evidence", status_code=303)


@router.post("/{ev_id}/delete")
def evidence_delete(
    case_id: int, ev_id: int,
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if ev:
        fname = ev.file_name
        # Remove physical file
        p = Path(ev.file_path)
        if p.exists():
            p.unlink()
        db.delete(ev)
        db.commit()
        audit.log(db, case_id, f"EVIDENCE REMOVED: {fname}",
                  investigator=investigator, app_name="Evidence")
    return RedirectResponse(f"/cases/{case_id}#evidence", status_code=303)
