from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from ..templates_env import templates as _shared_templates
from sqlalchemy import or_
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Optional
from ..database import get_db
from .. import models
from ..core import audit
from ..core.coc import generate_case_number
from ..routers.agency import get_or_create_agency

router = APIRouter(prefix="/cases", tags=["cases"])
templates = _shared_templates

CASE_TYPES = [
    "Cyber Incident", "Digital Forensics", "OSINT Investigation",
    "Mobile Forensics", "Network Forensics", "Financial Investigation",
    "Malware Analysis", "Threat Hunting", "Other",
]

_SORT_FIELDS = {
    "newest":   models.Case.created_at.desc(),
    "oldest":   models.Case.created_at.asc(),
    "updated":  models.Case.updated_at.desc(),
    "priority": models.Case.priority.desc(),
    "name":     models.Case.name.asc(),
}


@router.get("/")
def case_list(
    request:    Request,
    q:          str           = Query(""),
    status:     list[str]     = Query([]),
    priority:   list[str]     = Query([]),
    case_type:  str           = Query(""),
    date_from:  Optional[date] = Query(None),
    date_to:    Optional[date] = Query(None),
    sort:       str           = Query("newest"),
    db:         Session       = Depends(get_db),
):
    query = db.query(models.Case)

    # Full-text search across case_number, name, notes and evidence filenames
    if q.strip():
        term = f"%{q.strip()}%"
        ev_sub = (
            db.query(models.Evidence.case_id)
            .filter(or_(
                models.Evidence.file_name.ilike(term),
                models.Evidence.notes.ilike(term),
                models.Evidence.md5.ilike(term),
                models.Evidence.sha256.ilike(term),
            ))
            .subquery()
        )
        query = query.filter(or_(
            models.Case.case_number.ilike(term),
            models.Case.name.ilike(term),
            models.Case.notes.ilike(term),
            models.Case.id.in_(ev_sub),
        ))

    if status:
        query = query.filter(models.Case.status.in_(status))
    if priority:
        query = query.filter(models.Case.priority.in_(priority))
    if case_type:
        query = query.filter(models.Case.case_type == case_type)
    if date_from:
        query = query.filter(models.Case.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(models.Case.created_at <= datetime.combine(date_to, datetime.max.time()))

    order = _SORT_FIELDS.get(sort, models.Case.created_at.desc())
    cases = query.order_by(order).all()

    filters = {
        "q": q, "status": status, "priority": priority,
        "case_type": case_type,
        "date_from": date_from.isoformat() if date_from else "",
        "date_to":   date_to.isoformat()   if date_to   else "",
        "sort": sort,
    }
    active_filters = any([q.strip(), status, priority, case_type, date_from, date_to])

    return templates.TemplateResponse(request, "cases/list.html", {
        "cases":          cases,
        "filters":        filters,
        "active_filters": active_filters,
        "total_count":    db.query(models.Case).count(),
        "CASE_TYPES":     CASE_TYPES,
        "ALL_STATUSES":   [e.value for e in models.CaseStatus],
        "ALL_PRIORITIES": [e.value for e in models.CasePriority],
    })


@router.get("/search")
def global_search(q: str = Query(""), db: Session = Depends(get_db)):
    """JSON search across cases + evidence — used by the navbar quick-search."""
    if not q.strip() or len(q.strip()) < 2:
        return JSONResponse({"results": []})
    term = f"%{q.strip()}%"

    cases = (
        db.query(models.Case)
        .filter(or_(
            models.Case.case_number.ilike(term),
            models.Case.name.ilike(term),
        ))
        .limit(6).all()
    )
    evidence = (
        db.query(models.Evidence)
        .filter(or_(
            models.Evidence.file_name.ilike(term),
            models.Evidence.md5.ilike(term),
            models.Evidence.sha256.ilike(term),
        ))
        .limit(6).all()
    )

    results = []
    for c in cases:
        results.append({
            "type": "case", "id": c.id,
            "label": f"{c.case_number} — {c.name}",
            "sub":   c.status,
            "url":   f"/cases/{c.id}",
        })
    for ev in evidence:
        results.append({
            "type":  "evidence", "id": ev.id,
            "label": ev.file_name,
            "sub":   f"{ev.evidence_number} · case #{ev.case_id}",
            "url":   f"/cases/{ev.case_id}#tab-evidence",
        })
    return JSONResponse({"results": results})


@router.get("/new")
def case_new(request: Request, db: Session = Depends(get_db)):
    agency = get_or_create_agency(db)
    return templates.TemplateResponse(request, "cases/new.html", {
        "agency"         : agency,
        "case_types"     : CASE_TYPES,
        "priorities"     : [e.value for e in models.CasePriority],
        "classifications": [e.value for e in models.CaseClassification],
    })


@router.post("/new")
def case_create(
    name:             str = Form(...),
    case_type:        str = Form(""),
    priority:         str = Form(models.CasePriority.medium),
    classification:   str = Form(models.CaseClassification.confidential),
    investigator_name: str = Form(""),
    notes:            str = Form(""),
    db: Session = Depends(get_db),
):
    agency = get_or_create_agency(db)
    case_number = generate_case_number(agency.case_prefix or "CASE", db)

    case = models.Case(
        case_number    = case_number,
        name           = name,
        case_type      = case_type,
        priority       = priority,
        classification = classification,
        notes          = notes,
        status         = models.CaseStatus.open,
    )
    db.add(case)
    db.flush()

    if investigator_name.strip():
        inv = models.Investigator(case_id=case.id, name=investigator_name.strip(), is_lead=1)
        db.add(inv)

    db.commit()
    audit.log(db, case.id, f"Case created: {case_number} — {name}",
              investigator=investigator_name)
    return RedirectResponse(f"/cases/{case.id}", status_code=303)


@router.get("/{case_id}")
def case_detail(case_id: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return RedirectResponse("/cases/")
    agency  = get_or_create_agency(db)
    from ..core.pipeline import PIPELINES
    plugins  = _load_plugins()
    # Pipeline run history — latest 30, grouped for display
    pl_runs  = case.pipeline_runs[:30]
    return templates.TemplateResponse(request, "cases/detail.html", {
        "case"      : case,
        "agency"    : agency,
        "plugins"   : plugins,
        "categories": [e.value for e in models.EvidenceCategory],
        "audit_logs": case.audit_logs[-50:][::-1],
        "PIPELINES" : PIPELINES,
        "pl_runs"   : pl_runs,
    })


@router.post("/{case_id}/status")
def case_update_status(
    case_id: int,
    status: str = Form(...),
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case:
        old = case.status
        case.status = status
        if status == models.CaseStatus.closed:
            case.closed_at = datetime.utcnow()
        db.commit()
        audit.log(db, case_id, f"Status changed: {old} → {status}", investigator=investigator)
    return RedirectResponse(f"/cases/{case_id}", status_code=303)


@router.post("/{case_id}/notes")
def case_update_notes(
    case_id: int,
    notes: str = Form(""),
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if case:
        case.notes = notes
        case.updated_at = datetime.utcnow()
        db.commit()
        audit.log(db, case_id, "Case notes updated", investigator=investigator)
    return RedirectResponse(f"/cases/{case_id}", status_code=303)


@router.post("/{case_id}/investigator")
def case_add_investigator(
    case_id: int,
    name: str = Form(...),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    inv = models.Investigator(case_id=case_id, name=name.strip(), email=email.strip())
    db.add(inv)
    db.commit()
    audit.log(db, case_id, f"Investigator added: {name}", investigator=name)
    return RedirectResponse(f"/cases/{case_id}", status_code=303)


def _load_plugins() -> list[dict]:
    """Discover plugin modules from app/plugins/_N_*.py."""
    import importlib.util, sys
    from pathlib import Path

    plugins = []
    plugin_dir = Path("app/plugins")
    if not plugin_dir.exists():
        return plugins

    for f in sorted(plugin_dir.glob("_[0-9]*_*.py"),
                    key=lambda x: int(x.stem.split("_")[1]) if x.stem.split("_")[1].isdigit() else 999):
        parts = f.stem.split("_", 2)
        if len(parts) < 3:
            continue
        label       = parts[2].replace("_", " ").title()
        module_name = f"app.plugins.{f.stem}"
        spec        = importlib.util.spec_from_file_location(module_name, str(f))
        if not spec:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            plugins.append({
                "label"   : getattr(mod, "TAB_LABEL", label),
                "icon"    : getattr(mod, "TAB_ICON", "fa-puzzle-piece"),
                "route"   : getattr(mod, "TAB_ROUTE", f"/plugins/{f.stem}"),
                "module"  : mod,
            })
        except Exception as e:
            print(f"Plugin load error {f}: {e}")
    return plugins
