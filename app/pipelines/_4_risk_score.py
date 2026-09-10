"""
Risk Score — aggregate all prior pipeline findings into a 0-100 risk score.
Must run after hash_intel and ioc_extract.
"""
MODULE_NAME  = "risk_score"
MODULE_LABEL = "Risk Score"
MODULE_ICON  = "fa-chart-bar"

_PRIORITY_SCORE = {
    "Critical":      30,
    "High":          20,
    "Medium":        10,
    "Low":            5,
    "Informational":  0,
}
_STATUS_SCORE = {
    "Active": 5,
    "Review": 5,
    "Open":   2,
}


def run(context: dict) -> dict:
    case     = context.get("case")
    prior    = context.get("prior_findings", [])
    iocs     = context.get("iocs", {})

    score = 0.0

    # Priority base
    score += _PRIORITY_SCORE.get(str(case.priority), 0)
    score += _STATUS_SCORE.get(str(case.status), 0)

    # Evidence count
    ev_count = len(case.evidence or [])
    score += min(ev_count * 2, 10)

    # From prior findings
    for f in prior:
        if f.get("type") == "critical":
            score += 25
        elif f.get("type") == "warning":
            score += 5

    # IOC counts
    score += min(len(iocs.get("IPv4", [])) * 3, 15)
    score += min(len(iocs.get("CVE", [])) * 5, 15)
    score += min(len(iocs.get("SHA256", [])) * 2, 10)
    score += min(len(iocs.get("MD5", [])) * 2, 10)
    score += min(len(iocs.get("URL", [])), 5)
    score += min(len(iocs.get("Domain", [])), 5)

    score = min(round(score, 1), 100.0)

    if score >= 80:
        level, ftype = "CRITICAL", "critical"
    elif score >= 55:
        level, ftype = "HIGH", "warning"
    elif score >= 30:
        level, ftype = "MEDIUM", "info"
    else:
        level, ftype = "LOW", "info"

    # Store on context for flowintel_push
    context["risk_score"]  = score
    context["risk_level"]  = level

    findings = [{
        "type":   ftype,
        "title":  f"Risk Score: {score}/100 — {level}",
        "detail": (
            f"Priority={case.priority}, Evidence={ev_count}, "
            f"Critical findings={sum(1 for f in prior if f.get('type')=='critical')}, "
            f"IOC types={len(iocs)}"
        ),
    }]

    notes = (
        f"\n\n### Risk Assessment\n"
        f"**Score:** {score}/100 — **{level}**  \n"
        f"Basis: priority={case.priority}, {ev_count} evidence item(s), "
        f"{sum(1 for f in prior if f.get('type')=='critical')} critical finding(s), "
        f"{sum(len(v) for v in iocs.values())} IOC(s)"
    )

    return {"status": "done", "findings": findings, "notes": notes, "risk_score": score}
