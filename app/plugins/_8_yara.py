"""
Yara Scan plugin — trigger yara scans and show results per case.
"""

TAB_LABEL = "Yara Scan"
TAB_ICON  = "fa-shield-halved"

_SEVERITY_COLOR = {
    "critical": "danger",
    "high":     "danger",
    "medium":   "warning",
    "low":      "success",
}


def render_tab(case) -> str:
    case_id = case.id

    last_result = None
    if case.yara_scan_results:
        last_result = case.yara_scan_results[0]

    # Summarize last scan
    if last_result:
        import json as _json
        results = _json.loads(last_result.results_json or "[]")
        ts       = last_result.scanned_at.strftime("%Y-%m-%d %H:%M UTC")
        by       = last_result.scanned_by or "unknown"
        fc       = last_result.file_count
        mc       = last_result.match_count

        badge_cls = "danger" if mc else "success"
        badge_txt = f"{mc} match{'es' if mc!=1 else ''}"

        summary_html = f"""
        <div class="alert alert-secondary py-2 d-flex justify-content-between align-items-center mb-3">
          <span>
            <i class="fa fa-clock me-1"></i>{ts} &nbsp;·&nbsp;
            {fc} file{'s' if fc!=1 else ''} scanned &nbsp;·&nbsp;
            by <strong>{by}</strong>
          </span>
          <span class="badge bg-{badge_cls}">{badge_txt}</span>
        </div>"""

        if results:
            rows = ""
            for r in results:
                for m in r.get("matches", []):
                    rule_name = m["rule"]
                    strings_html = ""
                    for s in m.get("strings", [])[:5]:
                        strings_html += (
                            f"<div class='text-muted small'>"
                            f"<code>{s['id']}</code> @ 0x{s['offset']:x}: "
                            f"<code>{s['data'][:60]}</code></div>"
                        )
                    rows += f"""
                    <tr>
                      <td><code class='small text-warning'>{rule_name}</code></td>
                      <td class='small'>{r['evidence_number']} — {r['file_name']}</td>
                      <td>
                        {' '.join(f"<span class='badge bg-secondary' style='font-size:0.6rem'>{t}</span>" for t in m.get('tags',[]))}
                      </td>
                      <td>
                        <button class='btn btn-sm py-0 btn-outline-secondary'
                                onclick="yaraToggleStrings(this)">
                          <i class='fa fa-list-ul'></i>
                        </button>
                        <div class='yara-strings mt-1' style='display:none'>
                          {strings_html or '<span class="text-muted small">no string details</span>'}
                        </div>
                      </td>
                    </tr>"""
            result_table = f"""
            <div class="card">
              <div class="card-header small"><i class="fa fa-exclamation-triangle me-1 text-warning"></i>Matches</div>
              <div class="card-body p-0" style="max-height:400px;overflow-y:auto">
                <table class="table table-sm table-dark mb-0 align-top">
                  <thead class="table-secondary text-muted small">
                    <tr>
                      <th>Rule</th><th>Evidence</th><th>Tags</th><th>Strings</th>
                    </tr>
                  </thead>
                  <tbody>{rows}</tbody>
                </table>
              </div>
            </div>"""
        else:
            result_table = """
            <div class="card">
              <div class="card-body text-center text-muted py-4 small">
                <i class="fa fa-check-circle fa-2x text-success mb-2 d-block"></i>
                No matches found — all files clean.
              </div>
            </div>"""
    else:
        summary_html = """
        <div class="alert alert-secondary py-2 small text-muted">
          No scan has been run yet for this case.
        </div>"""
        result_table = ""

    return f"""
<div class="row g-3 mt-1">
  <div class="col-12">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <span class="text-muted small">
        <i class="fa fa-shield-halved me-1"></i>Scan all evidence files against enabled Yara rules.
      </span>
      <form method="post" action="/cases/{case_id}/yara/scan" class="d-inline">
        <input type="hidden" name="investigator" value="">
        <button class="btn btn-sm btn-outline-warning">
          <i class="fa fa-play me-1"></i>Run scan now
        </button>
      </form>
    </div>

    {summary_html}
    {result_table}

    <div class="mt-2 text-end">
      <a href="/yara" class="btn btn-sm btn-outline-secondary">
        <i class="fa fa-cog me-1"></i>Manage Yara rules
      </a>
    </div>
  </div>
</div>

<script>
function yaraToggleStrings(btn) {{
  const div = btn.parentElement.querySelector('.yara-strings');
  if (div) div.style.display = div.style.display === 'none' ? '' : 'none';
}}
</script>
"""
