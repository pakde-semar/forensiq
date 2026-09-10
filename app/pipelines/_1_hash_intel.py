"""
Hash Intel — check evidence file hashes against MalwareBazaar.
Runs automatically after evidence upload; also usable for all case evidence in assessment.
"""
import httpx

MODULE_NAME  = "hash_intel"
MODULE_LABEL = "Hash Intel"
MODULE_ICON  = "fa-hashtag"


def run(context: dict) -> dict:
    evidence = context.get("evidence")
    case     = context.get("case")

    # Collect (hash, label) pairs
    targets: list[tuple[str, str]] = []
    if evidence:
        # Single evidence mode (from auto-run on upload)
        for h in [evidence.sha256, evidence.md5]:
            if h:
                targets.append((h, evidence.file_name))
                break
    else:
        # Full case mode — all evidence
        for ev in (case.evidence or []):
            h = ev.sha256 or ev.md5
            if h:
                targets.append((h, ev.file_name))

    if not targets:
        return {"status": "skipped", "findings": [{"type": "info", "title": "No hashes to check", "detail": ""}]}

    findings: list[dict] = []
    with httpx.Client(timeout=20) as c:
        for h, label in targets:
            try:
                r    = c.post("https://mb-api.abuse.ch/api/v1/", data={"query": "get_info", "hash": h})
                data = r.json()
                qs   = data.get("query_status", "")
                if qs == "ok":
                    d = data.get("data", [{}])[0]
                    findings.append({
                        "type":   "critical",
                        "title":  f"MALWARE: {label}",
                        "detail": f"Signature: {d.get('signature','–')} | Tags: {', '.join(d.get('tags') or [])} | First seen: {d.get('first_seen','–')}",
                    })
                elif qs == "hash_not_found":
                    findings.append({
                        "type":   "info",
                        "title":  f"Clean: {label}",
                        "detail": f"Hash {h[:16]}… not found in MalwareBazaar",
                    })
                else:
                    findings.append({
                        "type":   "warning",
                        "title":  f"Unknown status for {label}",
                        "detail": qs,
                    })
            except Exception as e:
                findings.append({
                    "type":   "warning",
                    "title":  f"Lookup failed: {label}",
                    "detail": str(e),
                })

    critical = sum(1 for f in findings if f["type"] == "critical")
    notes = None
    if critical:
        lines = [f"### Hash Intel — {critical} malware detection(s)"]
        for f in findings:
            if f["type"] == "critical":
                lines.append(f"- **{f['title']}** — {f['detail']}")
        notes = "\n".join(lines)

    return {"status": "done", "findings": findings, "notes": notes}
