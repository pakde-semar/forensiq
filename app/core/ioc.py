"""Shared IOC extraction logic used by pipeline, export, and plugins."""
import re
from typing import NamedTuple


class IOC(NamedTuple):
    type:   str   # IPv4 | SHA256 | MD5 | SHA1 | Email | URL | CVE | Domain
    value:  str
    source: str   # "notes" | "evidence:<evidence_number>"


_P = {
    "IPv4":   re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'),
    "SHA256": re.compile(r'\b[a-fA-F0-9]{64}\b'),
    "MD5":    re.compile(r'\b[a-fA-F0-9]{32}\b'),
    "SHA1":   re.compile(r'\b[a-fA-F0-9]{40}\b'),
    "Email":  re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    "URL":    re.compile(r'https?://[^\s<>"\']+'),
    "CVE":    re.compile(r'CVE-\d{4}-\d{4,7}', re.I),
    "Domain": re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}\b'),
}
_PRIVATE = re.compile(r'^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.0\.0\.0|255\.)')


def extract_from_case(case) -> list[IOC]:
    """Extract all IOCs from a case's notes and evidence."""
    results: list[IOC] = []
    seen: set[tuple[str, str]] = set()

    def _scan(text: str, source: str) -> None:
        url_matches: set[str] = set()
        for m in _P["URL"].finditer(text):
            url_matches.add(m.group().lower())

        for kind, pat in _P.items():
            for m in pat.finditer(text):
                v = m.group()
                if kind == "IPv4" and _PRIVATE.match(v):
                    continue
                if kind == "Domain" and any(v.lower() in u for u in url_matches):
                    continue
                key = (kind, v.lower())
                if key in seen:
                    continue
                seen.add(key)
                results.append(IOC(type=kind, value=v, source=source))

    _scan(case.notes or "", "notes")
    for ev in (case.evidence or []):
        src = f"evidence:{ev.evidence_number}"
        _scan(ev.file_name or "", src)
        _scan(ev.notes or "", src)
        # Also include hashes directly from evidence fields
        for h, kind in [(ev.md5, "MD5"), (ev.sha256, "SHA256")]:
            if h:
                key = (kind, h.lower())
                if key not in seen:
                    seen.add(key)
                    results.append(IOC(type=kind, value=h, source=src))

    return results
