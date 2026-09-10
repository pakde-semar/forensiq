import json
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import engine, get_db
from . import models
from .templates_env import templates
from .routers import agency, cases, evidence, reports, integrations, lookup, pipeline, coc, export, yara, hashverify, timeclock, notes, timeline, preview, iocgraph, invheatmap, enrichment, bulkimport, tagsearch, metadata, alerts

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="ForensiQ", version="0.1.0")


@app.on_event("startup")
def _startup():
    from .database import SessionLocal as _SL
    from .routers.alerts import ensure_default_rules
    db = _SL()
    try:
        ensure_default_rules(db)
    finally:
        db.close()
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


app.include_router(agency.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(reports.router)
app.include_router(integrations.router)
app.include_router(lookup.router)
app.include_router(pipeline.router)
app.include_router(coc.router)
app.include_router(export.router)
app.include_router(yara.router)
app.include_router(hashverify.router)
app.include_router(timeclock.router)
app.include_router(notes.router)
app.include_router(timeline.router)
app.include_router(preview.router)
app.include_router(iocgraph.router)
app.include_router(invheatmap.router)
app.include_router(enrichment.router)
app.include_router(bulkimport.router)
app.include_router(tagsearch.router)
app.include_router(metadata.router)
app.include_router(alerts.router)


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    now = datetime.utcnow()

    # ── Stat cards ────────────────────────────────────────────────
    total    = db.query(models.Case).count()
    active   = db.query(models.Case).filter_by(status=models.CaseStatus.active).count()
    review   = db.query(models.Case).filter_by(status=models.CaseStatus.review).count()
    ev_total = db.query(models.Evidence).count()

    # ── Case status distribution ──────────────────────────────────
    status_rows = db.query(models.Case.status, func.count(models.Case.id))\
                    .group_by(models.Case.status).all()
    status_data = {r[0]: r[1] for r in status_rows}

    # ── Case priority distribution ────────────────────────────────
    priority_rows = db.query(models.Case.priority, func.count(models.Case.id))\
                      .group_by(models.Case.priority).all()
    priority_data = {r[0]: r[1] for r in priority_rows}

    # ── Cases per month (last 12 months) ─────────────────────────
    months_labels, months_counts = [], []
    for i in range(11, -1, -1):
        dt    = (now.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
        label = dt.strftime("%b %Y")
        ym    = dt.strftime("%Y-%m")
        cnt   = db.query(models.Case)\
                  .filter(func.strftime("%Y-%m", models.Case.created_at) == ym).count()
        months_labels.append(label)
        months_counts.append(cnt)

    # ── Evidence category distribution ───────────────────────────
    cat_rows = db.query(models.Evidence.category, func.count(models.Evidence.id))\
                 .group_by(models.Evidence.category).all()
    cat_data  = {r[0].split("/")[-1] if r[0] else "Other": r[1] for r in cat_rows}

    # ── Top 7 investigators by total hours ────────────────────────
    inv_rows = db.query(models.Investigator.name,
                        func.sum(models.Investigator.timeclock_minutes))\
                 .group_by(models.Investigator.name)\
                 .order_by(func.sum(models.Investigator.timeclock_minutes).desc())\
                 .limit(7).all()
    inv_labels  = [r[0] for r in inv_rows]
    inv_minutes = [int(r[1] or 0) for r in inv_rows]
    inv_hours   = [round(m / 60, 1) for m in inv_minutes]

    # ── Pipeline runs per day (last 14 days) ─────────────────────
    pipe_labels, pipe_done, pipe_error = [], [], []
    for i in range(13, -1, -1):
        day   = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        label = (now - timedelta(days=i)).strftime("%d %b")
        done  = db.query(models.PipelineRun)\
                  .filter(func.strftime("%Y-%m-%d", models.PipelineRun.started_at) == day,
                          models.PipelineRun.status == "done").count()
        err   = db.query(models.PipelineRun)\
                  .filter(func.strftime("%Y-%m-%d", models.PipelineRun.started_at) == day,
                          models.PipelineRun.status == "error").count()
        pipe_labels.append(label)
        pipe_done.append(done)
        pipe_error.append(err)

    # ── Activity heatmap (last 91 days) ──────────────────────────
    heat_counts: dict[str, int] = defaultdict(int)
    cutoff = now - timedelta(days=91)
    heat_rows = db.query(func.strftime("%Y-%m-%d", models.AuditLog.timestamp),
                         func.count(models.AuditLog.id))\
                  .filter(models.AuditLog.timestamp >= cutoff)\
                  .group_by(func.strftime("%Y-%m-%d", models.AuditLog.timestamp))\
                  .all()
    for date_str, cnt in heat_rows:
        if date_str:
            heat_counts[date_str] = cnt
    heat_max = max(heat_counts.values(), default=1)

    # Build 91-day grid (Sun→Sat columns)
    heat_days = []
    for i in range(90, -1, -1):
        d   = (now - timedelta(days=i))
        key = d.strftime("%Y-%m-%d")
        heat_days.append({
            "date":  key,
            "label": d.strftime("%b %d"),
            "count": heat_counts.get(key, 0),
            "level": min(4, int(heat_counts.get(key, 0) / max(heat_max, 1) * 4 + 0.5)),
        })

    recent_cases = (
        db.query(models.Case)
        .order_by(models.Case.updated_at.desc())
        .limit(10).all()
    )
    recent_logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(20).all()
    )

    return templates.TemplateResponse(request, "dashboard.html", {
        "stats":          {"total": total, "active": active, "review": review, "evidence": ev_total},
        "recent_cases":   recent_cases,
        "recent_logs":    recent_logs,
        # chart data (JSON-safe)
        "status_data":    json.dumps(status_data),
        "priority_data":  json.dumps(priority_data),
        "months_labels":  json.dumps(months_labels),
        "months_counts":  json.dumps(months_counts),
        "cat_labels":     json.dumps(list(cat_data.keys())),
        "cat_counts":     json.dumps(list(cat_data.values())),
        "inv_labels":     json.dumps(inv_labels),
        "inv_hours":      json.dumps(inv_hours),
        "pipe_labels":    json.dumps(pipe_labels),
        "pipe_done":      json.dumps(pipe_done),
        "pipe_error":     json.dumps(pipe_error),
        "heat_days":      heat_days,
        "heat_max":       heat_max,
    })
