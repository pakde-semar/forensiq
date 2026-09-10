"""Evidence metadata extraction endpoints."""
import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from .. import models
from ..core.metadata_extractor import extract
from ..core import audit

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["metadata"])


@router.get("/{ev_id}/metadata")
def get_metadata(case_id: int, ev_id: int, db: Session = Depends(get_db)):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if not ev:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {
        "ev_id":        ev.id,
        "file_name":    ev.file_name,
        "extracted_at": ev.metadata_extracted_at.isoformat() if ev.metadata_extracted_at else None,
        "metadata":     json.loads(ev.metadata_json or "{}"),
    }


@router.post("/{ev_id}/metadata/extract")
def extract_metadata(
    case_id: int,
    ev_id:   int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if not ev:
        return JSONResponse({"error": "Not found"}, status_code=404)
    background.add_task(_extract_bg, ev_id, case_id)
    return {"status": "queued", "ev_id": ev_id}


@router.post("/metadata/extract_all")
def extract_all_metadata(
    case_id:    int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ev_ids = [ev.id for ev in db.query(models.Evidence).filter_by(case_id=case_id).all()]
    for eid in ev_ids:
        background.add_task(_extract_bg, eid, case_id)
    return {"status": "queued", "count": len(ev_ids)}


def _extract_bg(ev_id: int, case_id: int):
    db = SessionLocal()
    try:
        ev = db.query(models.Evidence).filter_by(id=ev_id).first()
        if not ev or not ev.file_path:
            return
        meta = extract(ev.file_path)
        ev.metadata_json         = json.dumps(meta)
        ev.metadata_extracted_at = datetime.utcnow()
        db.commit()
    except Exception:
        pass
    finally:
        db.close()
