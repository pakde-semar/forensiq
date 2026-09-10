"""
Flowintel Push — create/update Flowintel case and push IOC observables.
"""
import httpx
import sys
import os

MODULE_NAME  = "flowintel_push"
MODULE_LABEL = "Flowintel Push"
MODULE_ICON  = "fa-diagram-project"

# Flowintel config (mirrors integrations/config.py but imports cleanly from subprocess context)
_BASE = os.getenv("FLOWINTEL_URL", "http://127.0.0.1:7006")
_KEY  = os.getenv("FLOWINTEL_API_KEY", "aO4EEcQ50S1ouVaobz6okouwpsBUjNIqXgjyD0hP7IZuEwYkdQ94m55y2fR7")
_HDR  = {"X-API-KEY": _KEY, "Content-Type": "application/json"}


def _get(path: str) -> dict:
    r = httpx.get(f"{_BASE}{path}", headers=_HDR, timeout=10)
    return r.json() if r.status_code == 200 else {}


def _post(path: str, data: dict) -> dict:
    r = httpx.post(f"{_BASE}{path}", headers=_HDR, json=data, timeout=10)
    try:
        return r.json()
    except Exception:
        return {}


def run(context: dict) -> dict:
    case       = context.get("case")
    risk_score = context.get("risk_score")
    iocs       = context.get("iocs", {})

    findings: list[dict] = []
    pushed: list[str]    = []

    # Step 1: ensure Flowintel case exists
    fw_id = case.flowintel_case_id
    if not fw_id:
        res = _post("/api/case/create", {
            "title":       f"[{case.case_number}] {case.name}",
            "description": (case.notes or "")[:500],
        })
        fw_id = res.get("id") or (res.get("case", {}) or {}).get("id")
        if fw_id:
            findings.append({"type": "info", "title": f"Created Flowintel case #{fw_id}", "detail": ""})
        else:
            findings.append({"type": "warning", "title": "Could not create Flowintel case", "detail": str(res)[:200]})
            return {"status": "done", "findings": findings}
    else:
        findings.append({"type": "info", "title": f"Using existing Flowintel case #{fw_id}", "detail": ""})

    # Step 2: push risk score as note
    if risk_score is not None:
        note_text = f"[ForensiQ Pipeline] Risk Score: {risk_score}/100 — {context.get('risk_level', '')}"
        _post(f"/api/case/{fw_id}/note/create", {"note": note_text})
        findings.append({"type": "info", "title": f"Pushed risk score: {risk_score}/100", "detail": ""})

    # Step 3: push IOC observables
    TYPE_MAP = {
        "IPv4":   "ip-src",
        "Domain": "domain",
        "URL":    "url",
        "MD5":    "md5",
        "SHA256": "sha-256",
        "SHA1":   "sha-1",
        "Email":  "email-src",
    }
    obs_count = 0
    for kind, vals in iocs.items():
        obs_type = TYPE_MAP.get(kind)
        if not obs_type:
            continue
        for val in vals[:20]:  # cap at 20 per type to avoid flooding
            _post(f"/api/case/{fw_id}/observable/create", {
                "value": val,
                "type":  obs_type,
            })
            obs_count += 1
            pushed.append(val)

    if obs_count:
        findings.append({
            "type":   "info",
            "title":  f"Pushed {obs_count} observable(s) to Flowintel",
            "detail": ", ".join(pushed[:5]) + ("…" if len(pushed) > 5 else ""),
        })

    notes = (
        f"\n\n### Flowintel Push\n"
        f"Case: #{fw_id} | Observables pushed: {obs_count}"
        + (f" | Risk score: {risk_score}/100" if risk_score else "")
    )

    return {"status": "done", "findings": findings, "notes": notes, "flowintel_case_id": fw_id}
