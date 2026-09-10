"""
Flowintel API client for ForensiQ.
Flowintel runs at 127.0.0.1:7006 (localhost on flowintel VM).
ForensiQ accesses it via SSH tunnel or direct if on same host.
"""
import httpx
import logging
from .config import FLOWINTEL_BASE_URL, FLOWINTEL_API_KEY

log = logging.getLogger(__name__)

TIMEOUT = 10.0


def _headers() -> dict:
    return {"X-API-KEY": FLOWINTEL_API_KEY, "Content-Type": "application/json"}


def _get(path: str) -> dict | list | None:
    url = f"{FLOWINTEL_BASE_URL}{path}"
    try:
        r = httpx.get(url, headers=_headers(), timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("Flowintel GET %s failed: %s", path, e)
        return None


def _post(path: str, data: dict) -> dict | None:
    url = f"{FLOWINTEL_BASE_URL}{path}"
    try:
        r = httpx.post(url, headers=_headers(), json=data, timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("Flowintel POST %s failed: %s", path, e)
        return None


# ─── Case operations ────────────────────────────────────────────────────────

def get_case(flowintel_case_id: int) -> dict | None:
    """Return full Flowintel case dict or None."""
    return _get(f"/api/case/{flowintel_case_id}")


def list_cases() -> list[dict]:
    """Return list of all Flowintel cases."""
    result = _get("/api/case/all")
    if isinstance(result, dict):
        return result.get("cases", [])
    return []


def get_case_notes(flowintel_case_id: int) -> str:
    """Return case notes as plain text."""
    case = get_case(flowintel_case_id)
    return case.get("notes", "") if case else ""


def create_case(title: str, description: str = "") -> dict | None:
    """Create a new case in Flowintel and return the response."""
    return _post("/api/case/create", {
        "title"      : title,
        "description": description,
    })


def get_modules_result(flowintel_case_id: int) -> dict | None:
    """Return last module run result for a case."""
    return _get(f"/api/case/{flowintel_case_id}/module")


def get_fir_suggestion(notes: str) -> dict | None:
    """
    Parse FIR_SUGGESTION marker from Flowintel case notes.
    Returns {"decision": str, "score": int, "ts": str} or None.
    """
    import re
    m = re.search(r'<!-- FIR_SUGGESTION:([^:]+):(\d+):([^ ]+) -->', notes or "")
    if not m:
        return None
    return {"decision": m.group(1), "score": int(m.group(2)), "ts": m.group(3)}


def sync_notes_to_forensiq(flowintel_case_id: int) -> tuple[str, dict | None]:
    """
    Pull notes from Flowintel case and return (notes_text, fir_suggestion).
    """
    notes      = get_case_notes(flowintel_case_id)
    suggestion = get_fir_suggestion(notes)
    return notes, suggestion


def get_observables(flowintel_case_id: int) -> list[dict]:
    """Return list of observables (IOCs) attached to a Flowintel case."""
    result = _get(f"/api/case/{flowintel_case_id}/observable/all")
    if isinstance(result, dict):
        return result.get("observables", [])
    return []
