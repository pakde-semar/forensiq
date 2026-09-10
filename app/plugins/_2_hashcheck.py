"""
Hash Check plugin — batch check all evidence hashes against MalwareBazaar.
"""
TAB_LABEL = "Hash Check"
TAB_ICON  = "fa-shield-halved"


def render_tab(case) -> str:  # noqa: ANN001
    rows = ""
    for ev in case.evidence:
        hashes = []
        if ev.md5:
            hashes.append(f"<span class='badge bg-secondary me-1 font-monospace'>MD5:{ev.md5[:12]}…</span>")
        if ev.sha256:
            hashes.append(f"<span class='badge bg-secondary me-1 font-monospace'>SHA256:{ev.sha256[:12]}…</span>")

        check_hash = ev.sha256 or ev.md5 or ""
        check_btn  = (
            f"<button class='btn btn-sm btn-outline-secondary py-0' "
            f"onclick=\"hashCheck('{check_hash}',this)\" data-hash='{check_hash}'>"
            f"<i class='fa fa-shield-halved me-1'></i>Check</button>"
            if check_hash else "<span class='text-muted small'>no hash</span>"
        )

        rows += f"""
        <tr id="hcrow-{ev.id}">
          <td><code class='small'>{ev.evidence_number}</code></td>
          <td class='small'>{ev.file_name}</td>
          <td>{"".join(hashes)}</td>
          <td id="hcstatus-{ev.id}">–</td>
          <td>{check_btn}</td>
        </tr>"""

    if not rows:
        return "<p class='text-muted mt-3'>No evidence with hashes found in this case.</p>"

    ev_ids  = [str(ev.id) for ev in case.evidence if ev.sha256 or ev.md5]
    ev_hmap = {str(ev.id): ev.sha256 or ev.md5 for ev in case.evidence if ev.sha256 or ev.md5}
    ev_hmap_json = str(ev_hmap).replace("'", '"')

    return f"""
<div class="mt-3">
  <div class="d-flex justify-content-between align-items-center mb-2">
    <h6 class="mb-0"><i class="fa fa-shield-halved me-1"></i>Evidence Hash Reputation</h6>
    <button class="btn btn-sm btn-outline-warning" onclick="hashCheckAll()">
      <i class="fa fa-play me-1"></i>Check All
    </button>
  </div>

  <div id="hc-progress" class="mb-2" style="display:none">
    <div class="progress" style="height:6px">
      <div id="hc-bar" class="progress-bar bg-warning" style="width:0%"></div>
    </div>
    <small class="text-muted" id="hc-progress-label">Checking…</small>
  </div>

  <div class="card">
    <div class="card-body p-0" style="overflow-x:auto">
      <table class="table table-sm table-dark mb-0">
        <thead>
          <tr>
            <th>Ev#</th><th>File</th><th>Hashes</th><th>Reputation</th><th></th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>

  <small class="text-muted">Source: MalwareBazaar (abuse.ch) — checks MD5/SHA256 only</small>
</div>

<script>
(function() {{
  const hmap = {ev_hmap_json};
  const evIds = {ev_ids};

  async function hashCheck(hash, btn) {{
    if (!hash) return;
    const row = btn ? btn.closest('tr') : null;
    const evId = row ? row.id.replace('hcrow-', '') : null;
    const statusCell = evId ? document.getElementById('hcstatus-' + evId) : null;
    if (btn) btn.disabled = true;
    if (statusCell) statusCell.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    try {{
      const r    = await fetch(`/api/lookup?type=hash&q=${{encodeURIComponent(hash)}}`);
      const data = await r.json();
      if (!statusCell) return;
      if (data.error) {{
        statusCell.innerHTML = `<span class="text-warning small">${{data.error}}</span>`;
      }} else if ((data['Status'] || '').includes('MALWARE')) {{
        const sig = data['Signature'] || '';
        statusCell.innerHTML = `<span class="badge bg-danger">MALWARE</span>${{sig ? ' <small>' + sig + '</small>' : ''}}`;
      }} else {{
        statusCell.innerHTML = '<span class="badge bg-success">Clean</span>';
      }}
    }} catch(e) {{
      if (statusCell) statusCell.innerHTML = `<span class="text-danger small">error</span>`;
    }} finally {{
      if (btn) btn.disabled = false;
    }}
  }}
  window.hashCheck = hashCheck;

  window.hashCheckAll = async function() {{
    const progress = document.getElementById('hc-progress');
    const bar      = document.getElementById('hc-bar');
    const label    = document.getElementById('hc-progress-label');
    progress.style.display = '';
    let done = 0;
    for (const evId of evIds) {{
      const hash = hmap[evId];
      if (!hash) {{ done++; continue; }}
      const fakeBtn = {{ disabled: false, closest: () => document.getElementById('hcrow-' + evId) }};
      await hashCheck(hash, null);
      const statusCell = document.getElementById('hcstatus-' + evId);
      done++;
      const pct = Math.round(done / evIds.length * 100);
      bar.style.width   = pct + '%';
      label.textContent = `Checking… ${{done}}/${{evIds.length}}`;
    }}
    label.textContent = 'Done.';
    setTimeout(() => {{ progress.style.display = 'none'; }}, 2000);
  }};
}})();
</script>
"""
