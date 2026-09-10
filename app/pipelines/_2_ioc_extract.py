"""
IOC Extract — regex-extract IOCs from case notes and evidence filenames.
Populates context["iocs"] for downstream modules.
"""
import re

MODULE_NAME  = "ioc_extract"
MODULE_LABEL = "IOC Extract"
MODULE_ICON  = "fa-crosshairs"

_P = {
    "IPv4":   re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'),
    "SHA256": re.compile(r'\b[a-fA-F0-9]{64}\b'),
    "MD5":    re.compile(r'\b[a-fA-F0-9]{32}\b'),
    "SHA1":   re.compile(r'\b[a-fA-F0-9]{40}\b'),
    "Email":  re.compile(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b'),
    "URL":    re.compile(r'https?://[^\s<>"\']+'),
    "CVE":    re.compile(r'CVE-\d{4}-\d{4,7}'),
    "Domain": re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}\b'),
}
_PRIVATE = re.compile(r'^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.0\.0\.0|255\.)')


def run(context: dict) -> dict:
    case = context.get("case")

    corpus = (case.notes or "") + "\n"
    for ev in (case.evidence or []):
        corpus += ev.file_name + "\n"
        corpus += (ev.notes or "") + "\n"

    found: dict[str, set] = {k: set() for k in _P}
    for kind, pat in _P.items():
        for m in pat.finditer(corpus):
            v = m.group()
            if kind == "IPv4" and _PRIVATE.match(v):
                continue
            found[kind].add(v)

    # Remove domains that are substrings of captured URLs
    url_lower = {u.lower() for u in found.get("URL", set())}
    found["Domain"] = {d for d in found["Domain"] if not any(d.lower() in u for u in url_lower) and "." in d}

    # Populate context for downstream modules
    context["iocs"] = {k: sorted(v) for k, v in found.items() if v}

    total = sum(len(v) for v in context["iocs"].values())
    if total == 0:
        return {"status": "skipped", "findings": [{"type": "info", "title": "No IOCs found", "detail": ""}]}

    findings: list[dict] = []
    for kind, vals in context["iocs"].items():
        for v in vals:
            ftype = "warning" if kind in ("IPv4", "SHA256", "MD5", "SHA1", "CVE") else "info"
            findings.append({"type": ftype, "title": f"{kind}: {v}", "detail": ""})

    # Append IOC summary to case notes
    lines = [f"\n\n### IOC Extract — {total} IOC(s) found"]
    for kind, vals in context["iocs"].items():
        lines.append(f"**{kind}** ({len(vals)}): " + ", ".join(f"`{v}`" for v in vals[:10])
                     + ("…" if len(vals) > 10 else ""))
    notes = "\n".join(lines)

    return {"status": "done", "findings": findings, "notes": notes}
