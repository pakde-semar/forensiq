"""
File Metadata plugin — EXIF/metadata extraction from evidence files via /api/evidence/{id}/meta.
"""
import html as _html

TAB_LABEL = "File Metadata"
TAB_ICON  = "fa-file-circle-info"


def render_tab(case) -> str:  # noqa: ANN001
    if not case.evidence:
        return "<p class='text-muted mt-3'>No evidence files in this case.</p>"

    rows = ""
    for ev in case.evidence:
        rows += f"""
        <tr>
          <td><code class='small'>{ev.evidence_number}</code></td>
          <td class='small'>{_html.escape(ev.file_name)}</td>
          <td class='small text-muted'>{ev.category}</td>
          <td>
            <button class='btn btn-sm py-0 btn-outline-secondary'
                    onclick="metaLoad({ev.id}, '{_html.escape(ev.file_name, quote=True)}')">
              <i class='fa fa-file-circle-info me-1'></i>View
            </button>
          </td>
        </tr>"""

    return f"""
<div class="row g-3 mt-1">
  <div class="col-md-5">
    <div class="card">
      <div class="card-header"><i class="fa fa-file-circle-info me-1"></i>Evidence Files</div>
      <div class="card-body p-0">
        <table class="table table-sm table-dark mb-0">
          <thead><tr><th>Ev#</th><th>File</th><th>Category</th><th></th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>
  </div>
  <div class="col-md-7">
    <div id="meta-panel" style="display:none">
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span id="meta-title">Metadata</span>
          <button class="btn btn-sm py-0 btn-outline-secondary"
                  onclick="document.getElementById('meta-panel').style.display='none'">
            <i class="fa fa-xmark"></i>
          </button>
        </div>
        <div class="card-body p-0" style="max-height:500px;overflow-y:auto">
          <table class="table table-sm table-dark mb-0">
            <tbody id="meta-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>
    <div id="meta-empty" class="text-muted mt-3 small" style="display:none">
      No metadata extracted (file may be unsupported or missing).
    </div>
  </div>
</div>

<script>
(function() {{
  window.metaLoad = async function(evId, fileName) {{
    const panel = document.getElementById('meta-panel');
    const title = document.getElementById('meta-title');
    const tbody = document.getElementById('meta-tbody');
    const empty = document.getElementById('meta-empty');
    panel.style.display = 'none';
    empty.style.display = 'none';
    title.textContent   = fileName;
    tbody.innerHTML     = '<tr><td colspan="2"><span class="spinner-border spinner-border-sm me-1"></span>Extracting…</td></tr>';
    panel.style.display = '';
    try {{
      const r    = await fetch(`/api/evidence/${{evId}}/meta`);
      const data = await r.json();
      if (data.error) {{
        tbody.innerHTML = `<tr><td colspan="2" class="text-danger">${{data.error}}</td></tr>`;
        return;
      }}
      const entries = Object.entries(data).filter(([k]) => k !== '_tool');
      if (!entries.length) {{
        panel.style.display = 'none';
        empty.style.display = '';
        return;
      }}
      // Group by prefix (ExifTool tags are "Group:Tag")
      let rows = '';
      for (const [k, v] of entries) {{
        const interesting = ['GPS', 'Author', 'Creator', 'Software', 'Make', 'Model',
                             'DateTime', 'Date', 'Time', 'Copyright', 'Comment', 'Description',
                             'Title', 'Subject', 'Producer', 'Modify'];
        const highlight   = interesting.some(i => k.includes(i));
        rows += `<tr>
          <th class="ps-3 text-muted" style="width:42%;font-weight:normal;font-size:.8rem">${{k}}</th>
          <td class="pe-3 font-monospace small ${{highlight ? 'text-warning' : ''}}">${{String(v).substring(0, 200)}}</td>
        </tr>`;
      }}
      tbody.innerHTML = rows;
    }} catch(e) {{
      tbody.innerHTML = `<tr><td colspan="2" class="text-danger">${{e}}</td></tr>`;
    }}
  }};
}})();
</script>
"""
