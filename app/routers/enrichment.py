"""Threat intelligence enrichment — VirusTotal, AbuseIPDB, Shodan."""
import json
import httpx
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from .. import models
from ..templates_env import templates
from ..core import audit

router = APIRouter(tags=["enrichment"])

# ── Supported providers per IOC type ─────────────────────────────────────────

SUPPORTED = {
    "IPv4":   ["virustotal", "abuseipdb", "shodan"],
    "Domain": ["virustotal", "shodan"],
    "MD5":    ["virustotal"],
    "SHA256": ["virustotal"],
    "SHA1":   ["virustotal"],
    "URL":    ["virustotal"],
}


# ── Settings helpers ──────────────────────────────────────────────────────────

def _get_setting(db: Session, key: str) -> str:
    row = db.query(models.AppSetting).filter_by(key=key).first()
    return row.value if row else ""


def _set_setting(db: Session, key: str, value: str):
    row = db.query(models.AppSetting).filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.add(models.AppSetting(key=key, value=value))
    db.commit()


# ── Settings page ─────────────────────────────────────────────────────────────

@router.get("/settings/enrichment")
def settings_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "enrichment/settings.html", {
        "vt_key":       _get_setting(db, "vt_api_key"),
        "abuseipdb_key": _get_setting(db, "abuseipdb_api_key"),
        "shodan_key":   _get_setting(db, "shodan_api_key"),
        "saved":        request.query_params.get("saved"),
    })


@router.post("/settings/enrichment")
def settings_save(
    vt_key:        str = Form(""),
    abuseipdb_key: str = Form(""),
    shodan_key:    str = Form(""),
    db: Session = Depends(get_db),
):
    _set_setting(db, "vt_api_key",        vt_key.strip())
    _set_setting(db, "abuseipdb_api_key", abuseipdb_key.strip())
    _set_setting(db, "shodan_api_key",    shodan_key.strip())
    return RedirectResponse("/settings/enrichment?saved=1", status_code=303)


# ── JSON list of enrichment results for a case ───────────────────────────────

@router.get("/cases/{case_id}/ioc/enrichments")
def enrichment_list(case_id: int, db: Session = Depends(get_db)):
    results = (
        db.query(models.EnrichmentResult)
        .filter_by(case_id=case_id)
        .order_by(models.EnrichmentResult.queried_at.desc())
        .all()
    )
    return [
        {
            "id":         r.id,
            "ioc_type":   r.ioc_type,
            "ioc_value":  r.ioc_value,
            "provider":   r.provider,
            "queried_at": r.queried_at.strftime("%Y-%m-%d %H:%M") if r.queried_at else "—",
            "queried_by": r.queried_by,
            "verdict":    r.verdict,
            "summary":    r.summary,
            "result_json": json.loads(r.result_json or "{}"),
        }
        for r in results
    ]


# ── Enrich an IOC ─────────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/ioc/enrich")
def enrich_ioc(
    case_id:      int,
    background:   BackgroundTasks,
    ioc_type:     str = Form(...),
    ioc_value:    str = Form(...),
    provider:     str = Form(...),
    investigator: str = Form(""),
    db: Session = Depends(get_db),
):
    background.add_task(_enrich_bg, case_id, ioc_type, ioc_value, provider, investigator)
    return {"status": "queued"}


@router.post("/cases/{case_id}/ioc/enrichments/{result_id}/delete")
def enrichment_delete(case_id: int, result_id: int, db: Session = Depends(get_db)):
    r = db.query(models.EnrichmentResult).filter_by(id=result_id, case_id=case_id).first()
    if r:
        db.delete(r)
        db.commit()
    return {"status": "deleted"}


# ── Background enrichment task ────────────────────────────────────────────────

def _enrich_bg(case_id: int, ioc_type: str, ioc_value: str, provider: str, queried_by: str):
    db = SessionLocal()
    try:
        vt_key  = _get_setting(db, "vt_api_key")
        ai_key  = _get_setting(db, "abuseipdb_api_key")
        sh_key  = _get_setting(db, "shodan_api_key")

        try:
            if provider == "virustotal":
                result, verdict, summary = _vt_lookup(ioc_type, ioc_value, vt_key)
            elif provider == "abuseipdb":
                result, verdict, summary = _abuseipdb_lookup(ioc_value, ai_key)
            elif provider == "shodan":
                result, verdict, summary = _shodan_lookup(ioc_type, ioc_value, sh_key)
            else:
                result, verdict, summary = {}, "unknown", "Unknown provider"
        except Exception as e:
            result, verdict, summary = {"error": str(e)}, "error", str(e)[:200]

        er = models.EnrichmentResult(
            case_id=case_id,
            ioc_type=ioc_type,
            ioc_value=ioc_value,
            provider=provider,
            queried_by=queried_by,
            verdict=verdict,
            summary=summary,
            result_json=json.dumps(result),
        )
        db.add(er)
        db.commit()
        audit.log(db, case_id,
                  f"Enriched {ioc_type} {ioc_value} via {provider}: {verdict}",
                  investigator=queried_by, app_name="Enrichment")
        if verdict == "malicious":
            from .alerts import maybe_notify
            maybe_notify(
                db,
                rule_type="enrichment_malicious",
                title=f"Malicious IOC: {ioc_value}",
                body=f"{provider} flagged {ioc_type} as malicious — {summary}",
                severity="critical",
                link=f"/cases/{case_id}",
                case_id=case_id,
            )
    finally:
        db.close()


# ── VirusTotal ────────────────────────────────────────────────────────────────

def _vt_lookup(ioc_type: str, ioc_value: str, api_key: str):
    if not api_key:
        return {}, "unknown", "No VirusTotal API key configured"

    ep_map = {
        "IPv4":   f"ip_addresses/{ioc_value}",
        "Domain": f"domains/{ioc_value}",
        "MD5":    f"files/{ioc_value}",
        "SHA256": f"files/{ioc_value}",
        "SHA1":   f"files/{ioc_value}",
        "URL":    f"urls/{_vt_url_id(ioc_value)}",
    }
    endpoint = ep_map.get(ioc_type)
    if not endpoint:
        return {}, "unknown", f"IOC type {ioc_type} not supported by VirusTotal"

    resp = httpx.get(
        f"https://www.virustotal.com/api/v3/{endpoint}",
        headers={"x-apikey": api_key},
        timeout=20,
    )
    if resp.status_code == 404:
        return {}, "unknown", "Not found in VirusTotal"
    if resp.status_code != 200:
        return {"status_code": resp.status_code}, "error", f"VT API error {resp.status_code}"

    data = resp.json().get("data", {})
    attrs = data.get("attributes", {})
    stats = attrs.get("last_analysis_stats", {})
    mal   = stats.get("malicious", 0)
    sus   = stats.get("suspicious", 0)
    total = sum(stats.values()) or 1

    if mal >= 5:
        verdict = "malicious"
    elif mal > 0 or sus > 0:
        verdict = "suspicious"
    else:
        verdict = "clean"

    summary = f"{mal}/{total} engines detected as malicious"
    if ioc_type in ("MD5", "SHA256", "SHA1"):
        name = attrs.get("meaningful_name") or attrs.get("name") or ""
        if name:
            summary += f" — {name}"

    result = {
        "last_analysis_stats": stats,
        "reputation":          attrs.get("reputation"),
        "country":             attrs.get("country"),
        "as_owner":            attrs.get("as_owner"),
        "tags":                attrs.get("tags", []),
        "meaningful_name":     attrs.get("meaningful_name"),
        "type_description":    attrs.get("type_description"),
        "last_analysis_date":  attrs.get("last_analysis_date"),
        "link": f"https://www.virustotal.com/gui/{'ip-address' if ioc_type=='IPv4' else ioc_type.lower()}/{ioc_value}",
    }
    return result, verdict, summary


def _vt_url_id(url: str) -> str:
    import base64
    return base64.urlsafe_b64encode(url.encode()).rstrip(b"=").decode()


# ── AbuseIPDB ─────────────────────────────────────────────────────────────────

def _abuseipdb_lookup(ioc_value: str, api_key: str):
    if not api_key:
        return {}, "unknown", "No AbuseIPDB API key configured"

    resp = httpx.get(
        "https://api.abuseipdb.com/api/v2/check",
        params={"ipAddress": ioc_value, "maxAgeInDays": 90, "verbose": ""},
        headers={"Key": api_key, "Accept": "application/json"},
        timeout=20,
    )
    if resp.status_code != 200:
        return {"status_code": resp.status_code}, "error", f"AbuseIPDB API error {resp.status_code}"

    data = resp.json().get("data", {})
    score   = data.get("abuseConfidenceScore", 0)
    reports = data.get("totalReports", 0)
    country = data.get("countryCode", "")
    isp     = data.get("isp", "")

    if score >= 75:
        verdict = "malicious"
    elif score >= 25:
        verdict = "suspicious"
    else:
        verdict = "clean"

    summary = f"Abuse confidence: {score}% — {reports} reports"
    if country:
        summary += f" — {country}"
    if isp:
        summary += f" / {isp}"

    result = {
        "abuseConfidenceScore": score,
        "totalReports":         reports,
        "countryCode":          country,
        "usageType":            data.get("usageType"),
        "isp":                  isp,
        "domain":               data.get("domain"),
        "isPublic":             data.get("isPublic"),
        "isWhitelisted":        data.get("isWhitelisted"),
        "link": f"https://www.abuseipdb.com/check/{ioc_value}",
    }
    return result, verdict, summary


# ── Shodan ────────────────────────────────────────────────────────────────────

def _shodan_lookup(ioc_type: str, ioc_value: str, api_key: str):
    if not api_key:
        return {}, "unknown", "No Shodan API key configured"

    if ioc_type == "IPv4":
        url = f"https://api.shodan.io/shodan/host/{ioc_value}"
    elif ioc_type == "Domain":
        url = f"https://api.shodan.io/dns/domain/{ioc_value}"
    else:
        return {}, "unknown", f"IOC type {ioc_type} not supported by Shodan"

    resp = httpx.get(url, params={"key": api_key}, timeout=20)
    if resp.status_code == 404:
        return {}, "unknown", "Not found in Shodan"
    if resp.status_code != 200:
        return {"status_code": resp.status_code}, "error", f"Shodan API error {resp.status_code}"

    data = resp.json()

    if ioc_type == "IPv4":
        ports   = data.get("ports", [])
        vulns   = list(data.get("vulns", {}).keys())
        org     = data.get("org", "")
        country = data.get("country_name", "")
        verdict = "malicious" if vulns else "suspicious" if ports else "unknown"
        summary = f"{len(ports)} open port(s)"
        if vulns:
            summary += f" — {len(vulns)} CVE(s): {', '.join(vulns[:3])}"
        if org:
            summary += f" — {org}"
        result = {
            "ports":        ports,
            "vulns":        vulns,
            "org":          org,
            "country_name": country,
            "os":           data.get("os"),
            "tags":         data.get("tags", []),
            "hostnames":    data.get("hostnames", []),
            "link": f"https://www.shodan.io/host/{ioc_value}",
        }
    else:
        subdomains = data.get("subdomains", [])
        verdict    = "unknown"
        summary    = f"{len(subdomains)} subdomain(s) found"
        result = {
            "subdomains": subdomains[:30],
            "tags":       data.get("tags", []),
            "link": f"https://www.shodan.io/search?query={ioc_value}",
        }

    return result, verdict, summary
