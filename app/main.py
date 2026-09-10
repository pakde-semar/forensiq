from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import engine, get_db
from . import models
from .routers import agency, cases, evidence, reports, integrations, lookup, pipeline

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="ForensiQ", version="0.1.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

templates = Jinja2Templates(directory="app/templates")

app.include_router(agency.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(reports.router)
app.include_router(integrations.router)
app.include_router(lookup.router)
app.include_router(pipeline.router)


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    total    = db.query(models.Case).count()
    active   = db.query(models.Case).filter_by(status=models.CaseStatus.active).count()
    review   = db.query(models.Case).filter_by(status=models.CaseStatus.review).count()
    evidence = db.query(models.Evidence).count()

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
        "stats"       : {"total": total, "active": active, "review": review, "evidence": evidence},
        "recent_cases": recent_cases,
        "recent_logs" : recent_logs,
    })
