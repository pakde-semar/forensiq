"""
Pipeline router — manual trigger and run history.
"""
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from ..templates_env import templates as _shared_templates
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..core import pipeline as engine

log = logging.getLogger(__name__)

router     = APIRouter(prefix="/cases/{case_id}/pipeline", tags=["pipeline"])
templates  = _shared_templates


@router.post("/run")
def run_pipeline(
    case_id:       int,
    pipeline_name: str = Form(...),
    investigator:  str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case or pipeline_name not in engine.PIPELINES:
        return RedirectResponse(f"/cases/{case_id}#tab-pipeline", status_code=303)

    background_tasks.add_task(
        engine.run_pipeline_background,
        pipeline_name, case_id, None,
        investigator or "manual",
    )
    return RedirectResponse(f"/cases/{case_id}#tab-pipeline", status_code=303)


@router.get("/status")
def pipeline_status(case_id: int, db: Session = Depends(get_db)):
    """JSON — latest run status per pipeline for this case."""
    runs = (
        db.query(models.PipelineRun)
        .filter_by(case_id=case_id)
        .order_by(models.PipelineRun.started_at.desc())
        .limit(50)
        .all()
    )
    seen: dict[str, dict] = {}
    for r in runs:
        if r.pipeline_name not in seen:
            seen[r.pipeline_name] = {
                "id":        r.id,
                "status":    r.status,
                "started":   r.started_at.isoformat() if r.started_at else "",
                "completed": r.completed_at.isoformat() if r.completed_at else None,
                "risk":      r.risk_score,
            }
    return JSONResponse(seen)


@router.get("/runs/{run_id}/steps")
def run_steps(case_id: int, run_id: int, db: Session = Depends(get_db)):
    """JSON — steps detail for one run."""
    run = db.query(models.PipelineRun).filter_by(id=run_id, case_id=case_id).first()
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    steps = json.loads(run.steps_json or "[]")
    return JSONResponse({
        "pipeline": run.pipeline_label,
        "status":   run.status,
        "risk":     run.risk_score,
        "steps":    steps,
    })
