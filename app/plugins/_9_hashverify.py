"""
Hash Verification plugin — batch re-verify integrity of all evidence files.
"""
import html as _html
import json as _json

TAB_LABEL = "Hash Verify"
TAB_ICON  = "fa-shield-check"

_STATUS_CFG = {
    "ok":       ("success", "fa-check-circle",    "OK"),
    "tampered": ("danger",  "fa-triangle-exclamation", "TAMPERED"),
    "missing":  ("warning", "fa-question-circle", "MISSING"),
    "no_hash":  ("secondary","fa-minus-circle",   "NO HASH"),
    "error":    ("danger",  "fa-times-circle",    "ERROR"),
}


def render_tab(case) -> str:
    case_id = case.id
    latest  = case.hash_verify_batches[0] if case.hash_verify_batches else None

    if latest:
        ts      = latest.run_at.strftime("%Y-%m-%d %H:%M UTC")
        run_by  = latest.run_by or "unknown"
        results = _json.loads(latest.results_json or "[]")

        ok_c  = latest.ok_count
        tam_c = latest.tampered_count
        mis_c = latest.missing_count
        nh_c  = latest.no_hash_count

        overall_cls = "danger" if tam_c else ("warning" if mis_c else "success")

        summary_html = f"""
        <div class="alert alert-{overall_cls} py-2 d-flex justify-content-between align-items-center mb-3">
          <span>
            <i class="fa fa-clock me-1"></i>{ts} &nbsp;·&nbsp; by <strong>{run_by}</strong>
            &nbsp;·&nbsp; {latest.total} evidence
          </span>
          <span>
            <span class="badge bg-success me-1">{ok_c} OK</span>
            {'<span class="badge bg-danger me-1">'+str(tam_c)+' TAMPERED</span>' if tam_c else ''}
            {'<span class="badge bg-warning text-dark me-1">'+str(mis_c)+' MISSING</span>' if mis_c else ''}
            {'<span class="badge bg-secondary me-1">'+str(nh_c)+' NO HASH</span>' if nh_c else ''}
          </span>
        </div>"""

        rows = ""
        for r in results:
            st  = r.get("status", "error")
            cls, icon, label = _STATUS_CFG.get(st, ("secondary", "fa-circle", st.upper()))
            ev_num  = _html.escape(r.get("evidence_number", ""))
            fname   = _html.escape(r.get("file_name", ""))
            s_md5   = r.get("stored_md5", "")
            c_md5   = r.get("computed_md5", "")
            s_sha   = r.get("stored_sha256", "")
            c_sha   = r.get("computed_sha256", "")

            detail_id = f"hv-detail-{r.get('evidence_id', 0)}"
            md5_cls   = "" if (not s_md5 or s_md5 == c_md5) else "text-danger"
            sha_cls   = "" if (not s_sha or s_sha == c_sha) else "text-danger"

            detail_html = ""
            if st in ("ok", "tampered"):
                detail_html = f"""
                <div id="{detail_id}" style="display:none" class="mt-1 small p-2 rounded" style="background:#111">
                  <div><span class="text-muted">MD5 stored:    </span><code class="{md5_cls}">{s_md5 or '—'}</code></div>
                  <div><span class="text-muted">MD5 computed:  </span><code class="{md5_cls}">{c_md5 or '—'}</code></div>
                  <div><span class="text-muted">SHA256 stored: </span><code class="{sha_cls}" style="word-break:break-all">{s_sha or '—'}</code></div>
                  <div><span class="text-muted">SHA256 computed:</span><code class="{sha_cls}" style="word-break:break-all">{c_sha or '—'}</code></div>
                </div>"""
                toggle_btn = f"""<button class="btn btn-sm py-0 btn-outline-secondary"
                  onclick="var d=document.getElementById('{detail_id}');d.style.display=d.style.display?'':'none'">
                  <i class="fa fa-magnifying-glass"></i></button>"""
            else:
                toggle_btn = ""

            rows += f"""
            <tr>
              <td><span class="badge bg-{cls}"><i class="fa {icon} me-1"></i>{label}</span></td>
              <td class="small text-muted">{ev_num}</td>
              <td class="small">{fname}</td>
              <td class="text-end">{toggle_btn}</td>
            </tr>
            {"<tr><td colspan='4' class='pt-0'>"+detail_html+"</td></tr>" if detail_html else ""}"""

        table_html = f"""
        <div class="card">
          <div class="card-body p-0" style="max-height:420px;overflow-y:auto">
            <table class="table table-sm table-dark mb-0 align-middle">
              <thead class="table-secondary text-muted small">
                <tr><th>Status</th><th>#</th><th>File</th><th></th></tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </div>"""
    else:
        summary_html = """
        <div class="alert alert-secondary py-2 small text-muted">
          No batch verify has been run yet for this case.
        </div>"""
        table_html = ""

    return f"""
<div class="row g-3 mt-1">
  <div class="col-12">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <span class="text-muted small">
        <i class="fa fa-shield-check me-1"></i>Re-hash all evidence files and compare against stored hashes.
      </span>
      <form method="post" action="/cases/{case_id}/evidence/verify_batch">
        <input type="hidden" name="investigator" value="">
        <button class="btn btn-sm btn-outline-primary">
          <i class="fa fa-rotate me-1"></i>Run batch verify
        </button>
      </form>
    </div>

    {summary_html}
    {table_html}

    <div class="mt-2">
      <small class="text-muted">
        <i class="fa fa-info-circle me-1"></i>
        TAMPERED = stored hash does not match current file hash.
        MISSING = file not found on disk.
        NO HASH = no hash was recorded at upload time.
      </small>
    </div>
  </div>
</div>
"""
