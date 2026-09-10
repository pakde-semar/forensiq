"""
Evidence Metadata — EXIF, PE headers, file type, strings extraction.
"""

TAB_LABEL = "Metadata"
TAB_ICON  = "fa-microscope"


def render_tab(case) -> str:
    case_id   = case.id
    evidence  = case.evidence or []

    if not evidence:
        return '<div class="text-muted small p-4 text-center">No evidence files in this case.</div>'

    rows = ""
    for ev in sorted(evidence, key=lambda e: e.evidence_number):
        extracted = "✓" if ev.metadata_extracted_at else "—"
        ts        = ev.metadata_extracted_at.strftime("%Y-%m-%d %H:%M") if ev.metadata_extracted_at else "Not extracted"
        rows += f"""
        <tr>
          <td><code style="font-size:.75rem">{ev.evidence_number}</code></td>
          <td style="font-size:.8rem;word-break:break-all;max-width:200px">{ev.file_name}</td>
          <td class="text-muted" style="font-size:.72rem;white-space:nowrap">{ts}</td>
          <td>
            <div class="d-flex gap-1">
              <button class="btn btn-sm py-0" style="font-size:.7rem;border:1px solid #cba6f755;color:#cba6f7"
                      onclick="metaExtract_{case_id}({ev.id}, this)">
                <i class="fa fa-bolt me-1"></i>Extract
              </button>
              <button class="btn btn-sm py-0 btn-outline-secondary"
                      style="font-size:.7rem"
                      onclick="metaView_{case_id}({ev.id}, '{ev.file_name.replace("'", "\\'")}')">
                <i class="fa fa-eye me-1"></i>View
              </button>
            </div>
          </td>
        </tr>"""

    return f"""
<div id="meta-root-{case_id}">

  <!-- Header -->
  <div class="d-flex align-items-center justify-content-between mb-3 mt-1">
    <span class="text-muted small"><i class="fa fa-microscope me-1"></i>Evidence Metadata</span>
    <div class="d-flex gap-2">
      <button class="btn btn-sm btn-outline-secondary py-0" style="font-size:.75rem"
              onclick="metaExtractAll_{case_id}()">
        <i class="fa fa-bolt me-1"></i>Extract All
      </button>
    </div>
  </div>

  <!-- Evidence list -->
  <div class="card mb-3">
    <div class="table-responsive">
      <table class="table table-sm table-hover mb-0">
        <thead class="small text-muted">
          <tr><th>Ev #</th><th>File</th><th>Last Extracted</th><th>Actions</th></tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Detail panel -->
  <div id="meta-panel-{case_id}" class="card p-3" style="display:none">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <span id="meta-panel-title-{case_id}" style="font-weight:600;color:#cdd6f4;font-size:.9rem"></span>
      <button class="btn btn-sm btn-outline-secondary py-0"
              onclick="document.getElementById('meta-panel-{case_id}').style.display='none'">
        <i class="fa fa-xmark"></i>
      </button>
    </div>
    <div id="meta-panel-body-{case_id}"></div>
  </div>
</div>

<script>
(function() {{
  const CASE_ID = {case_id};

  // ── Extract single ────────────────────────────────────────────
  window[`metaExtract_${{CASE_ID}}`] = function(evId, btn) {{
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i>Extracting…';
    btn.disabled  = true;
    fetch(`/cases/${{CASE_ID}}/evidence/${{evId}}/metadata/extract`, {{method:'POST'}})
      .then(r => r.json())
      .then(() => {{
        setTimeout(() => {{
          btn.innerHTML = orig;
          btn.disabled  = false;
          window[`metaView_${{CASE_ID}}`](evId, '');
        }}, 2500);
      }})
      .catch(() => {{ btn.innerHTML = orig; btn.disabled = false; }});
  }};

  // ── Extract all ───────────────────────────────────────────────
  window[`metaExtractAll_${{CASE_ID}}`] = function() {{
    fetch(`/cases/${{CASE_ID}}/evidence/metadata/extract_all`, {{method:'POST'}})
      .then(r => r.json())
      .then(d => alert(`Queued ${{d.count}} extraction${{d.count !== 1 ? 's' : ''}}. Refresh in a few seconds.`))
      .catch(() => alert('Failed to queue extractions.'));
  }};

  // ── View metadata ─────────────────────────────────────────────
  window[`metaView_${{CASE_ID}}`] = function(evId, fileName) {{
    const panel = document.getElementById(`meta-panel-${{CASE_ID}}`);
    const title = document.getElementById(`meta-panel-title-${{CASE_ID}}`);
    const body  = document.getElementById(`meta-panel-body-${{CASE_ID}}`);

    panel.style.display = 'block';
    title.textContent   = fileName || 'Loading…';
    body.innerHTML      = '<span class="text-muted small"><i class="fa fa-spinner fa-spin me-1"></i>Loading…</span>';
    panel.scrollIntoView({{behavior:'smooth', block:'nearest'}});

    fetch(`/cases/${{CASE_ID}}/evidence/${{evId}}/metadata`)
      .then(r => r.json())
      .then(data => {{
        title.textContent = data.file_name;
        const m = data.metadata;
        if (!m || Object.keys(m).length === 0) {{
          body.innerHTML = '<span class="text-muted small">No metadata extracted yet. Click Extract first.</span>';
          return;
        }}
        if (m.error) {{
          body.innerHTML = `<span class="text-danger small">${{m.error}}</span>`;
          return;
        }}
        body.innerHTML = renderMeta(m);
      }})
      .catch(() => {{ body.innerHTML = '<span class="text-danger small">Failed to load metadata.</span>'; }});
  }};

  // ── Render helpers ────────────────────────────────────────────
  function renderMeta(m) {{
    let html = '';

    // File info
    if (m.file_info) html += section('File Info', 'fa-file', '#89b4fa', tableKV(m.file_info, ['size_bytes','magic_hex']));

    // EXIF
    if (m.exif) {{
      const gps = m.exif.GPS_coords
        ? `<div class="mt-1"><a href="https://maps.google.com/?q=${{m.exif.GPS_coords}}" target="_blank"
              style="font-size:.72rem;color:#89b4fa"><i class="fa fa-location-dot me-1"></i>View on map</a></div>`
        : '';
      html += section('EXIF Data', 'fa-camera', '#f9e2af', tableKV(m.exif, ['GPSInfo']) + gps);
    }}

    // PE
    if (m.pe) {{
      const imports = (m.pe.imports || []).map(i =>
        `<div class="mb-1"><span style="color:#fab387;font-size:.75rem">${{i.dll}}</span>
         <div style="font-size:.7rem;color:#6c7086;padding-left:12px">${{(i.functions||[]).slice(0,8).join(', ')}}${{i.functions?.length > 8 ? ' …' : ''}}</div></div>`
      ).join('');
      const sections = (m.pe.section_list || []).map(s =>
        `<span class="badge me-1 mb-1" style="background:#31324488;color:#a6adc8;font-size:.65rem">
           ${{s.name}} <span style="color:${{s.entropy > 7 ? '#f38ba8' : '#6c7086'}}">(e:${{s.entropy}})</span>
         </span>`
      ).join('');
      const peBasic = tableKV(m.pe, ['imports','exports','section_list']);
      html += section('PE Header', 'fa-gears', '#cba6f7',
        peBasic + (sections ? `<div class="mt-2"><div class="text-muted" style="font-size:.72rem">Sections:</div>${{sections}}</div>` : '') +
        (imports ? `<div class="mt-2"><div class="text-muted" style="font-size:.72rem">Imports:</div>${{imports}}</div>` : ''));
    }}

    // Media
    if (m.media) html += section('Media Info', 'fa-film', '#94e2d5', tableKV(m.media, ['streams']) +
      (m.media.streams?.length ? `<div class="mt-2">${{m.media.streams.map(s =>
        `<span class="badge me-1" style="background:#31324488;color:#a6adc8;font-size:.65rem">
           ${{s.type}} · ${{s.codec}}${{s.resolution ? ' · ' + s.resolution : ''}}
         </span>`).join('')}}</div>` : ''));

    // Strings
    if (m.strings?.interesting?.length) {{
      const list = m.strings.interesting.map(s =>
        `<div style="font-size:.72rem;font-family:monospace;color:#a6adc8;padding:1px 0;
                     word-break:break-all;border-bottom:1px solid #31324455">${{esc(s)}}</div>`
      ).join('');
      html += section(`Interesting Strings (${{m.strings.interesting.length}} of ${{m.strings.total_ascii}} total)`,
        'fa-align-left', '#a6e3a1', list +
        (m.strings.truncated ? '<div class="text-muted" style="font-size:.68rem;margin-top:4px">Scanning first 2 MB only.</div>' : ''));
    }}

    return html || '<span class="text-muted small">No structured data extracted.</span>';
  }}

  function section(title, icon, color, body) {{
    const id = 'sec-' + Math.random().toString(36).slice(2,8);
    return `
    <div class="mb-3 rounded" style="border:1px solid ${{color}}33;overflow:hidden">
      <div class="d-flex align-items-center gap-2 px-3 py-2" style="background:${{color}}11;cursor:pointer"
           onclick="document.getElementById('${{id}}').classList.toggle('d-none')">
        <i class="fa ${{icon}}" style="color:${{color}};font-size:.8rem"></i>
        <span style="font-size:.8rem;font-weight:600;color:${{color}}">${{title}}</span>
        <i class="fa fa-chevron-down ms-auto text-muted" style="font-size:.65rem"></i>
      </div>
      <div id="${{id}}" class="px-3 py-2">${{body}}</div>
    </div>`;
  }}

  function tableKV(obj, skip=[]) {{
    const rows = Object.entries(obj)
      .filter(([k]) => !skip.includes(k))
      .map(([k, v]) => {{
        const display = typeof v === 'object' ? JSON.stringify(v).slice(0,120) + (JSON.stringify(v).length > 120 ? '…' : '') : String(v).slice(0,200);
        return `<tr>
          <td style="color:#6c7086;font-size:.72rem;white-space:nowrap;padding:2px 8px 2px 0;vertical-align:top">${{k}}</td>
          <td style="font-size:.75rem;color:#cdd6f4;word-break:break-all;padding:2px 0">${{esc(display)}}</td>
        </tr>`;
      }}).join('');
    return rows ? `<table style="width:100%;border-collapse:collapse">${{rows}}</table>` : '';
  }}

  function esc(s) {{
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }}
}})();
</script>
"""
