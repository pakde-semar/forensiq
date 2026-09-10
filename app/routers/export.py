"""
IOC export — CSV and STIX 2.1 bundle download.
"""
import csv
import io
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..core.ioc import extract_from_case
from ..routers.agency import get_or_create_agency

router = APIRouter(prefix="/cases/{case_id}/export", tags=["export"])

# ── STIX 2.1 type mapping ────────────────────────────────────────────────────

_STIX_PATTERN = {
    "IPv4":   lambda v: f"[ipv4-addr:value = '{v}']",
    "Domain": lambda v: f"[domain-name:value = '{v}']",
    "URL":    lambda v: f"[url:value = '{v}']",
    "MD5":    lambda v: f"[file:hashes.MD5 = '{v}']",
    "SHA256": lambda v: f"[file:hashes.'SHA-256' = '{v}']",
    "SHA1":   lambda v: f"[file:hashes.'SHA-1' = '{v}']",
    "Email":  lambda v: f"[email-addr:value = '{v}']",
    "CVE":    lambda v: f"[vulnerability:name = '{v}']",
}

_INDICATOR_TYPES = {
    "IPv4":   ["malicious-activity"],
    "Domain": ["malicious-activity"],
    "URL":    ["malicious-activity"],
    "MD5":    ["malicious-activity"],
    "SHA256": ["malicious-activity"],
    "SHA1":   ["malicious-activity"],
    "Email":  ["malicious-activity"],
    "CVE":    ["compromised"],
}


def _now_stix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/iocs")
def export_iocs_json(case_id: int, db: Session = Depends(get_db)):
    """Return extracted IOCs as JSON — useful for previewing."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return JSONResponse({"error": "not found"}, status_code=404)
    iocs = extract_from_case(case)
    by_type: dict[str, list] = {}
    for ioc in iocs:
        by_type.setdefault(ioc.type, []).append({"value": ioc.value, "source": ioc.source})
    return JSONResponse({
        "case_number": case.case_number,
        "total":       len(iocs),
        "by_type":     by_type,
    })


@router.get("/iocs.csv")
def export_iocs_csv(
    case_id: int,
    types:   list[str] = Query([]),
    db: Session = Depends(get_db),
):
    """Download IOCs as CSV."""
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return Response("Not found", status_code=404)

    iocs = extract_from_case(case)
    if types:
        iocs = [i for i in iocs if i.type in types]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["type", "value", "source", "case_number", "case_name", "extracted_at"])
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    for ioc in iocs:
        writer.writerow([ioc.type, ioc.value, ioc.source, case.case_number, case.name, ts])

    fname = f"iocs_{case.case_number}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/iocs.stix.json")
def export_iocs_stix(
    case_id: int,
    types:   list[str] = Query([]),
    db: Session = Depends(get_db),
):
    """Download IOCs as STIX 2.1 bundle JSON."""
    case   = db.query(models.Case).filter_by(id=case_id).first()
    agency = get_or_create_agency(db)
    if not case:
        return Response("Not found", status_code=404)

    iocs = extract_from_case(case)
    if types:
        iocs = [i for i in iocs if i.type in types]

    now = _now_stix()

    # Identity object (agency)
    identity_id = f"identity--{uuid.uuid5(uuid.NAMESPACE_DNS, agency.name or 'forensiq')}"
    identity = {
        "type":           "identity",
        "spec_version":   "2.1",
        "id":             identity_id,
        "created":        now,
        "modified":       now,
        "name":           agency.name or "ForensiQ",
        "identity_class": "organization",
        **({"contact_information": agency.email} if agency.email else {}),
    }

    # Indicator objects
    indicators = []
    for ioc in iocs:
        pattern_fn = _STIX_PATTERN.get(ioc.type)
        if not pattern_fn:
            continue
        ind_id = f"indicator--{uuid.uuid4()}"
        indicators.append({
            "type":             "indicator",
            "spec_version":     "2.1",
            "id":               ind_id,
            "created":          now,
            "modified":         now,
            "created_by_ref":   identity_id,
            "name":             f"{ioc.type}: {ioc.value}",
            "description":      f"Extracted from {ioc.source} in case {case.case_number}",
            "indicator_types":  _INDICATOR_TYPES.get(ioc.type, ["unknown"]),
            "pattern":          pattern_fn(ioc.value),
            "pattern_type":     "stix",
            "valid_from":       now,
            "labels":           ["forensiq", ioc.type.lower()],
        })

    # Report object
    indicator_ids = [i["id"] for i in indicators]
    report = {
        "type":           "report",
        "spec_version":   "2.1",
        "id":             f"report--{uuid.uuid4()}",
        "created":        now,
        "modified":       now,
        "created_by_ref": identity_id,
        "name":           f"ForensiQ IOC Report — {case.case_number}",
        "description":    case.name,
        "published":      now,
        "report_types":   ["threat-report"],
        "object_refs":    [identity_id] + indicator_ids,
    }

    bundle = {
        "type":         "bundle",
        "id":           f"bundle--{uuid.uuid4()}",
        "spec_version": "2.1",
        "objects":      [identity] + indicators + [report],
    }

    fname = f"iocs_{case.case_number}_{datetime.utcnow().strftime('%Y%m%d')}.stix.json"
    return Response(
        content=json.dumps(bundle, indent=2, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
