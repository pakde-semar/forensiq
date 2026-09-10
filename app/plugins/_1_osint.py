"""
OSINT Lookup plugin — IP geo, domain WHOIS, hash lookup via /api/lookup.
"""
TAB_LABEL = "OSINT"
TAB_ICON  = "fa-magnifying-glass-location"


def render_tab(case) -> str:  # noqa: ANN001
    hashes_rows = ""
    for ev in case.evidence:
        for h, htype in [(ev.md5, "MD5"), (ev.sha256, "SHA256")]:
            if not h:
                continue
            short = h[:20] + "…" if len(h) > 20 else h
            hashes_rows += (
                f"<tr>"
                f"<td><code class='small'>{ev.evidence_number}</code></td>"
                f"<td class='small text-truncate' style='max-width:140px'>{ev.file_name}</td>"
                f"<td><code class='small'>{short}</code></td>"
                f"<td class='small'>{htype}</td>"
                f"<td><button class='btn btn-sm py-0 btn-outline-secondary' "
                f"onclick=\"osintQuick('hash','{h}')\">Check</button></td>"
                f"</tr>"
            )

    evidence_section = ""
    if hashes_rows:
        evidence_section = f"""
        <div class="card mt-3">
          <div class="card-header small"><i class="fa fa-box-archive me-1"></i>Evidence Hashes</div>
          <div class="card-body p-0" style="overflow-x:auto">
            <table class="table table-sm table-dark mb-0">
              <thead><tr><th>Ev#</th><th>File</th><th>Hash</th><th>Type</th><th></th></tr></thead>
              <tbody>{hashes_rows}</tbody>
            </table>
          </div>
        </div>"""

    return f"""
<div class="row g-3 mt-1">

  <div class="col-md-5">
    <div class="card">
      <div class="card-header"><i class="fa fa-search me-1"></i>Lookup</div>
      <div class="card-body">
        <select id="osint-type" class="form-select form-select-sm mb-2">
          <option value="ip">IP Address</option>
          <option value="domain">Domain / WHOIS</option>
          <option value="hash">Hash (MD5 / SHA256)</option>
        </select>
        <div class="input-group input-group-sm">
          <input type="text" id="osint-query" class="form-control font-monospace"
                 placeholder="Enter value…" onkeydown="if(event.key==='Enter')osintLookup()">
          <button class="btn btn-outline-secondary" onclick="osintLookup()">
            <i class="fa fa-search"></i>
          </button>
        </div>
        <div id="osint-spinner" class="mt-2 small text-muted" style="display:none">
          <span class="spinner-border spinner-border-sm me-1"></span>Looking up…
        </div>
        <div id="osint-inline-error" class="mt-2 small text-danger"></div>
      </div>
    </div>
    {evidence_section}
  </div>

  <div class="col-md-7">
    <div class="card" id="osint-result-card" style="display:none">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span id="osint-result-title">Results</span>
        <button class="btn btn-sm btn-outline-secondary py-0"
                onclick="document.getElementById('osint-result-card').style.display='none'">
          <i class="fa fa-xmark"></i>
        </button>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm table-dark mb-0" id="osint-result-table">
          <tbody id="osint-result-body"></tbody>
        </table>
      </div>
    </div>
    <div id="osint-history" class="mt-3"></div>
  </div>

</div>

<script>
(function() {{
  function osintQuick(type, q) {{
    document.getElementById('osint-type').value = type;
    document.getElementById('osint-query').value = q;
    osintLookup();
  }}
  window.osintQuick = osintQuick;

  window.osintLookup = async function() {{
    const type = document.getElementById('osint-type').value;
    const q    = document.getElementById('osint-query').value.trim();
    if (!q) return;
    document.getElementById('osint-spinner').style.display = '';
    document.getElementById('osint-inline-error').textContent = '';
    document.getElementById('osint-result-card').style.display = 'none';
    try {{
      const r    = await fetch(`/api/lookup?type=${{type}}&q=${{encodeURIComponent(q)}}`);
      const data = await r.json();
      renderOsintResult(type, q, data);
    }} catch(e) {{
      document.getElementById('osint-inline-error').textContent = 'Request failed: ' + e;
    }} finally {{
      document.getElementById('osint-spinner').style.display = 'none';
    }}
  }};

  function renderOsintResult(type, q, data) {{
    const card  = document.getElementById('osint-result-card');
    const title = document.getElementById('osint-result-title');
    const tbody = document.getElementById('osint-result-body');
    title.textContent = type.toUpperCase() + ' — ' + q;
    card.style.display = '';

    if (data.error) {{
      tbody.innerHTML = `<tr><td colspan="2" class="text-danger">${{data.error}}</td></tr>`;
      return;
    }}
    const isMalware = (data['Status'] || '').includes('MALWARE');
    let rows = '';
    for (const [k, v] of Object.entries(data)) {{
      const vClass = (k === 'Status' && isMalware) ? 'text-danger fw-bold' : '';
      rows += `<tr>
        <th class="ps-3 text-muted" style="width:38%;font-weight:normal">${{k}}</th>
        <td class="pe-3 font-monospace small ${{vClass}}">${{v}}</td>
      </tr>`;
    }}
    tbody.innerHTML = rows;
  }}
}})();
</script>
"""
