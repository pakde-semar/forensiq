"""
Timeline plugin — chronological view of all case events.
"""
import html as _html

TAB_LABEL = "Timeline"
TAB_ICON  = "fa-timeline"


_COLOR = {
    "case":     ("primary",   "fa-folder-open"),
    "evidence": ("warning",   "fa-box-archive"),
    "audit":    ("secondary", "fa-clock-rotate-left"),
    "closed":   ("danger",    "fa-lock"),
    "report":   ("info",      "fa-file-lines"),
}


def render_tab(case) -> str:  # noqa: ANN001
    events: list[dict] = []

    if case.created_at:
        events.append({
            "ts":     case.created_at,
            "kind":   "case",
            "title":  "Case opened",
            "detail": f"{case.case_number} — {case.name}",
        })

    for ev in case.evidence:
        if ev.date_added:
            events.append({
                "ts":     ev.date_added,
                "kind":   "evidence",
                "title":  f"Evidence uploaded: {ev.evidence_number}",
                "detail": ev.file_name,
            })

    for rep in getattr(case, "reports", []):
        if rep.created_at:
            events.append({
                "ts":     rep.created_at,
                "kind":   "report",
                "title":  "Report generated",
                "detail": rep.title or "",
            })

    for log in case.audit_logs:
        if log.timestamp:
            events.append({
                "ts":     log.timestamp,
                "kind":   "audit",
                "title":  log.message[:120],
                "detail": log.investigator or "",
            })

    if case.closed_at:
        events.append({
            "ts":     case.closed_at,
            "kind":   "closed",
            "title":  "Case closed",
            "detail": "",
        })

    events.sort(key=lambda e: e["ts"])

    if not events:
        return "<p class='text-muted mt-3'>No events recorded yet.</p>"

    items_html = ""
    prev_date  = None
    for ev in events:
        date_str = ev["ts"].strftime("%d %b %Y")
        time_str = ev["ts"].strftime("%H:%M")
        color, icon = _COLOR.get(ev["kind"], ("secondary", "fa-circle"))

        if date_str != prev_date:
            items_html += f"""
        <div class="d-flex align-items-center my-3">
          <hr class="flex-grow-1 border-secondary">
          <span class="mx-3 text-muted small fw-semibold">{date_str}</span>
          <hr class="flex-grow-1 border-secondary">
        </div>"""
            prev_date = date_str

        detail_html = ""
        if ev["detail"]:
            detail_html = (
                f"<div class='small text-muted'>{_html.escape(ev['detail'])}</div>"
            )

        items_html += f"""
        <div class="d-flex gap-3 mb-3 align-items-start">
          <div class="text-center" style="min-width:40px;padding-top:2px">
            <span class="badge rounded-pill bg-{color}">
              <i class="fa {icon}"></i>
            </span>
          </div>
          <div class="flex-grow-1">
            <div class="d-flex justify-content-between">
              <span class="fw-semibold small">{_html.escape(ev['title'])}</span>
              <span class="text-muted small ms-3" style="white-space:nowrap">{time_str}</span>
            </div>
            {detail_html}
          </div>
        </div>"""

    return f"""
<div class="mt-3">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h6 class="mb-0"><i class="fa fa-timeline me-1"></i>Case Timeline</h6>
    <span class="badge bg-secondary">{len(events)} event{"s" if len(events) != 1 else ""}</span>
  </div>
  <div style="max-height:620px;overflow-y:auto;padding-right:4px">
    {items_html}
  </div>
</div>"""
