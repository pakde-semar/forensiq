from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from ..templates_env import templates as _shared_templates
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models

router = APIRouter(prefix="/agency", tags=["agency"])
templates = _shared_templates


def get_or_create_agency(db: Session) -> models.Agency:
    agency = db.query(models.Agency).first()
    if not agency:
        agency = models.Agency(name="My Agency")
        db.add(agency)
        db.commit()
        db.refresh(agency)
    return agency


@router.get("/")
def agency_form(request: Request, db: Session = Depends(get_db)):
    agency = get_or_create_agency(db)
    return templates.TemplateResponse(request, "agency/edit.html", {"agency": agency})


@router.post("/")
def agency_save(
    request: Request,
    name:                    str = Form(""),
    unit:                    str = Form(""),
    address:                 str = Form(""),
    city:                    str = Form(""),
    country:                 str = Form(""),
    phone:                   str = Form(""),
    email:                   str = Form(""),
    website:                 str = Form(""),
    case_prefix:             str = Form("CASE"),
    supervisor_name:         str = Form(""),
    supervisor_title:        str = Form(""),
    evidence_intake_email:   str = Form(""),
    legal_records_custodian: str = Form(""),
    db: Session = Depends(get_db),
):
    agency = get_or_create_agency(db)
    agency.name                    = name
    agency.unit                    = unit
    agency.address                 = address
    agency.city                    = city
    agency.country                 = country
    agency.phone                   = phone
    agency.email                   = email
    agency.website                 = website
    agency.case_prefix             = case_prefix
    agency.supervisor_name         = supervisor_name
    agency.supervisor_title        = supervisor_title
    agency.evidence_intake_email   = evidence_intake_email
    agency.legal_records_custodian = legal_records_custodian
    db.commit()
    return RedirectResponse("/agency/", status_code=303)
