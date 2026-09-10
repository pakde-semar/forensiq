"""
MISP client for ForensiQ via PyMISP.
"""
import logging
from .config import MISP_BASE_URL, MISP_API_KEY, MISP_VERIFY_SSL

log = logging.getLogger(__name__)

_misp_instance = None


def _misp():
    global _misp_instance
    if _misp_instance is not None:
        return _misp_instance
    try:
        from pymisp import PyMISP
        import warnings
        warnings.filterwarnings("ignore", message=".*InsecureRequestWarning.*")
        _misp_instance = PyMISP(MISP_BASE_URL, MISP_API_KEY, ssl=MISP_VERIFY_SSL)
        return _misp_instance
    except Exception as e:
        log.warning("MISP connection failed: %s", e)
        return None


# ─── Event operations ────────────────────────────────────────────────────────

def get_event(event_id: str | int) -> dict | None:
    """Return MISP event as dict or None."""
    m = _misp()
    if not m:
        return None
    try:
        ev = m.get_event(event_id, pythonify=False)
        if isinstance(ev, dict) and "Event" in ev:
            return ev["Event"]
        return ev if isinstance(ev, dict) else None
    except Exception as e:
        log.warning("MISP get_event %s failed: %s", event_id, e)
        return None


def list_recent_events(limit: int = 20) -> list[dict]:
    """Return the most recent MISP events."""
    m = _misp()
    if not m:
        return []
    try:
        result = m.search(controller="events", limit=limit, pythonify=False)
        if isinstance(result, list):
            return [e.get("Event", e) for e in result]
        return []
    except Exception as e:
        log.warning("MISP list_events failed: %s", e)
        return []


def search_events(value: str, limit: int = 10) -> list[dict]:
    """Search MISP events by value."""
    m = _misp()
    if not m:
        return []
    try:
        result = m.search(value=value, limit=limit, pythonify=False)
        if isinstance(result, list):
            return [e.get("Event", e) for e in result]
        return []
    except Exception as e:
        log.warning("MISP search failed: %s", e)
        return []


def get_iocs_from_event(event_id: str | int) -> list[dict]:
    """
    Return list of IOCs from a MISP event.
    Each item: {"type": str, "value": str, "category": str, "comment": str}
    """
    event = get_event(event_id)
    if not event:
        return []
    iocs = []
    for attr in event.get("Attribute", []):
        iocs.append({
            "type"    : attr.get("type", ""),
            "value"   : attr.get("value", ""),
            "category": attr.get("category", ""),
            "comment" : attr.get("comment", ""),
            "to_ids"  : attr.get("to_ids", False),
        })
    return iocs


def create_event(title: str, tags: list[str] | None = None,
                 distribution: int = 0) -> dict | None:
    """Create a new MISP draft event."""
    m = _misp()
    if not m:
        return None
    try:
        from pymisp import MISPEvent
        ev         = MISPEvent()
        ev.info    = title
        ev.distribution = distribution  # 0=org only, 1=community
        result = m.add_event(ev, pythonify=False)
        if isinstance(result, dict) and "Event" in result:
            return result["Event"]
        return None
    except Exception as e:
        log.warning("MISP create_event failed: %s", e)
        return None


def add_ioc_to_event(event_id: str | int, ioc_type: str,
                     ioc_value: str, comment: str = "") -> bool:
    """Add a single IOC attribute to a MISP event."""
    m = _misp()
    if not m:
        return False
    try:
        from pymisp import MISPAttribute
        attr         = MISPAttribute()
        attr.type    = ioc_type
        attr.value   = ioc_value
        attr.comment = comment
        attr.to_ids  = True
        result = m.add_attribute(event_id, attr, pythonify=False)
        return "Attribute" in result if isinstance(result, dict) else False
    except Exception as e:
        log.warning("MISP add_attribute failed: %s", e)
        return False


def publish_event(event_id: str | int) -> bool:
    """Publish a MISP event."""
    m = _misp()
    if not m:
        return False
    try:
        result = m.publish(event_id)
        return True
    except Exception as e:
        log.warning("MISP publish failed: %s", e)
        return False


def event_url(event_id: str | int) -> str:
    return f"{MISP_BASE_URL}/events/view/{event_id}"


def get_tags() -> list[str]:
    """Return list of available MISP tag names."""
    m = _misp()
    if not m:
        return []
    try:
        result = m.tags(pythonify=False)
        if isinstance(result, list):
            return [t.get("name", "") for t in result if t.get("name")]
        return []
    except Exception as e:
        log.warning("MISP get_tags failed: %s", e)
        return []


def add_tag_to_event(event_id: str | int, tag: str) -> bool:
    """Add a tag to a MISP event."""
    m = _misp()
    if not m:
        return False
    try:
        result = m.tag(event_id, tag)
        return True
    except Exception as e:
        log.warning("MISP add_tag failed: %s", e)
        return False


# IOC type map: ForensiQ label → MISP attribute type
_IOC_TYPE_MAP = {
    "IPv4":    "ip-src",
    "Domain":  "domain",
    "URL":     "url",
    "MD5":     "md5",
    "SHA256":  "sha-256",
    "SHA1":    "sha-1",
    "Email":   "email-src",
    "CVE":     "vulnerability",
}


def bulk_add_iocs(event_id: str | int, iocs: list[dict],
                  comment_prefix: str = "ForensiQ") -> tuple[int, int]:
    """
    Push a list of IOC dicts to a MISP event.
    Each dict: {"type": ForensiQ label, "value": str}
    Returns (pushed, skipped).
    """
    m = _misp()
    if not m:
        return 0, len(iocs)
    pushed = skipped = 0
    for ioc in iocs:
        misp_type = _IOC_TYPE_MAP.get(ioc.get("type", ""))
        value     = (ioc.get("value") or "").strip()
        if not misp_type or not value:
            skipped += 1
            continue
        try:
            from pymisp import MISPAttribute
            attr         = MISPAttribute()
            attr.type    = misp_type
            attr.value   = value
            attr.comment = comment_prefix
            attr.to_ids  = misp_type in ("ip-src", "ip-dst", "domain", "url",
                                          "md5", "sha-256", "sha-1")
            result = m.add_attribute(event_id, attr, pythonify=False)
            if isinstance(result, dict) and "Attribute" in result:
                pushed += 1
            else:
                skipped += 1
        except Exception as e:
            log.warning("MISP bulk_add_ioc %s failed: %s", value, e)
            skipped += 1
    return pushed, skipped


def search_events_by_value(value: str, limit: int = 10) -> list[dict]:
    """Search MISP events that contain a specific value."""
    m = _misp()
    if not m:
        return []
    try:
        result = m.search(value=value, limit=limit, pythonify=False)
        if isinstance(result, list):
            return [e.get("Event", e) for e in result]
        return []
    except Exception as e:
        log.warning("MISP search failed: %s", e)
        return []
