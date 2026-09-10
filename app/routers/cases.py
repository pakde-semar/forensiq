from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime
from ..database import get_db
from .. import models
from ..core import audit
from ..core.coc import generate_case_number
from ..routers.agency import get_or_create_agency

router = APIRouter(prefix="/cases", tags=["cases"])
templates = Jinja2Templates(directory="app/templates")

CASE_TYPES = [
    "Cyber Incident", "Digital Forensics", "OSINT Investigation",
    "Mobile Forensics", "Network Forensics", "Financial Investigation",
    "Malware Analysis", "Threat Hunting", "Other",
]


@router.get("/")
def case_list(request: Request, db: Session = Depends(get_db)):
    cases = db.query(models.Case).order_by(models.Case.created_at.desc()).all()
    return templates.TemplateResponse(request, "cases/list.html", {"cases": cases})


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
