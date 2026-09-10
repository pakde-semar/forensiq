"""
Threat Intel Enrichment — IOC lookup via VirusTotal, AbuseIPDB, Shodan.
"""

TAB_LABEL = "Threat Intel"
TAB_ICON  = "fa-biohazard"

_VERDICT_STYLE = {
    "malicious":  ("f38ba8", "fa-skull-crossbones", "MALICIOUS"),
    "suspicious": ("f9e2af", "fa-triangle-exclamation", "SUSPICIOUS"),
    "clean":      ("a6e3a1", "fa-check-circle", "CLEAN"),
    "unknown":    ("a6adc8", "fa-circle-question", "UNKNOWN"),
    "error":      ("fab387", "fa-circle-exclamation", "ERROR"),
}

_PROVIDER_STYLE = {
    "virustotal": ("f9e2af", "fa-virus", "VirusTotal"),
    "abuseipdb":  ("f38ba8", "fa-ban",   "AbuseIPDB"),
    "shodan":     ("89b4fa", "fa-satellite-dish", "Shodan"),
}

_SUPPORTED = {
    "IPv4":   ["virustotal", "abuseipdb", "shodan"],
    "Domain": ["virustotal", "shodan"],
    "MD5":    ["virustotal"],
    "SHA256": ["virustotal"],
    "SHA1":   ["virustotal"],
    "URL":    ["virustotal"],
}


def render_tab(case) -> str:
    case_id = case.id

    return f"""
<div id="enrich-root-{case_id}">

  <!-- Header row -->
  <div class="d-flex align-items-center justify-content-between mb-3 mt-1">
    <span class="text-muted small"><i class="fa fa-biohazard me-1"></i>Threat Intel Enrichment</span>
    <a href="/settings/enrichment" target="_blank" class="btn btn-sm btn-outline-secondary py-0" style="font-size:.72rem">
      <i class="fa fa-key me-1"></i>Configure API keys
    </a>
  </div>

  <!-- IOC lookup panel -->
  <div class="card mb-3 p-3">
    <div class="small fw-semibold mb-2" style="color:#cdd6f4">
      <i class="fa fa-magnifying-glass me-1"></i>Enrich an IOC
    </div>
    <div class="row g-2 align-items-end">
      <div class="col-md-4">
        <label class="text-muted" style="font-size:.72rem">IOC Value</label>
        <input id="enrich-val-{case_id}" type="text" class="form-control form-control-sm"
               placeholder="1.2.3.4 / evil.com / sha256hash…">
      </div>
      <div class="col-md-2">
        <label class="text-muted" style="font-size:.72rem">Type</label>
        <select id="enrich-type-{case_id}" class="form-select form-select-sm">
          <option value="IPv4">IPv4</option>
          <option value="Domain">Domain</option>
          <option value="SHA256">SHA256</option>
          <option value="MD5">MD5</option>
          <option value="SHA1">SHA1</option>
          <option value="URL">URL</option>
        </select>
      </div>
      <div class="col-md-2">
        <label class="text-muted" style="font-size:.72rem">Provider</label>
        <select id="enrich-provider-{case_id}" class="form-select form-select-sm">
          <option value="virustotal">VirusTotal</option>
          <option value="abuseipdb">AbuseIPDB</option>
          <option value="shodan">Shodan</option>
        </select>
      </div>
      <div class="col-md-2">
        <label class="text-muted" style="font-size:.72rem">Queried by</label>
        <input id="enrich-by-{case_id}" type="text" class="form-control form-control-sm" placeholder="Name">
      </div>
      <div class="col-md-2">
        <button class="btn btn-sm w-100 py-1" style="background:#cba6f7;color:#1e1e2e;font-weight:600"
                onclick="enrichSubmit_{case_id}()">
          <i class="fa fa-bolt me-1"></i>Enrich
        </button>
      </div>
    </div>
    <div id="enrich-msg-{case_id}" class="mt-2" style="font-size:.78rem;display:none"></div>
  </div>

  <!-- IOC list from case (quick-enrich buttons) -->
  <div class="card mb-3">
    <div class="card-header small d-flex justify-content-between align-items-center">
      <span><i class="fa fa-list me-1"></i>Case IOCs</span>
      <button class="btn btn-sm btn-outline-secondary py-0" style="font-size:.7rem"
              onclick="enrichLoadIocs_{case_id}()">
        <i class="fa fa-rotate-right me-1"></i>Reload
      </button>
    </div>
    <div id="enrich-iocs-{case_id}" class="p-3">
      <span class="text-muted small"><i class="fa fa-spinner fa-spin me-1"></i>Loading IOCs…</span>
    </div>
  </div>

  <!-- Results -->
  <div class="card">
    <div class="card-header small d-flex justify-content-between align-items-center">
      <span><i class="fa fa-shield-halved me-1"></i>Enrichment Results</span>
      <button class="btn btn-sm btn-outline-secondary py-0" style="font-size:.7rem"
              onclick="enrichLoadResults_{case_id}()">
        <i class="fa fa-rotate-right me-1"></i>Refresh
      </button>
    </div>
    <div id="enrich-results-{case_id}" class="p-3">
      <span class="text-muted small"><i class="fa fa-spinner fa-spin me-1"></i>Loading…</span>
    </div>
  </div>
</div>

<script>
(function() {{
  const CASE_ID = {case_id};

  const SUPPORTED = {_SUPPORTED!r};
  const PROV_STYLE = {{
    virustotal: {{color:'#f9e2af', icon:'fa-virus',           label:'VirusTotal'}},
    abuseipdb:  {{color:'#f38ba8', icon:'fa-ban',             label:'AbuseIPDB'}},
    shodan:     {{color:'#89b4fa', icon:'fa-satellite-dish',  label:'Shodan'}},
  }};
  const VERDICT_STYLE = {{
    malicious:  {{color:'#f38ba8', icon:'fa-skull-crossbones',    label:'MALICIOUS'}},
    suspicious: {{color:'#f9e2af', icon:'fa-triangle-exclamation', label:'SUSPICIOUS'}},
    clean:      {{color:'#a6e3a1', icon:'fa-check-circle',         label:'CLEAN'}},
    unknown:    {{color:'#a6adc8', icon:'fa-circle-question',       label:'UNKNOWN'}},
    error:      {{color:'#fab387', icon:'fa-circle-exclamation',    label:'ERROR'}},
  }};

  // ── Update provider options when type changes ─────────────────
  document.getElementById(`enrich-type-${{CASE_ID}}`).addEventListener('change', function() {{
    const type  = this.value;
    const sel   = document.getElementById(`enrich-provider-${{CASE_ID}}`);
    const avail = SUPPORTED[type] || [];
    [...sel.options].forEach(o => {{
      o.disabled = !avail.includes(o.value);
    }});
    if (sel.options[sel.selectedIndex].disabled) {{
      const first = [...sel.options].find(o => !o.disabled);
      if (first) sel.value = first.value;
    }}
  }});

  // ── Submit enrichment ─────────────────────────────────────────
  window[`enrichSubmit_${{CASE_ID}}`] = function() {{
    const val      = document.getElementById(`enrich-val-${{CASE_ID}}`).value.trim();
    const iocType  = document.getElementById(`enrich-type-${{CASE_ID}}`).value;
    const provider = document.getElementById(`enrich-provider-${{CASE_ID}}`).value;
    const byWho    = document.getElementById(`enrich-by-${{CASE_ID}}`).value.trim();
    const msg      = document.getElementById(`enrich-msg-${{CASE_ID}}`);

    if (!val) {{ msg.style.display='block'; msg.style.color='#f38ba8'; msg.textContent='Please enter an IOC value.'; return; }}

    msg.style.display='block'; msg.style.color='#a6adc8';
    msg.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i>Querying ' + provider + '…';

    const fd = new FormData();
    fd.append('ioc_type',     iocType);
    fd.append('ioc_value',    val);
    fd.append('provider',     provider);
    fd.append('investigator', byWho);

    fetch(`/cases/${{CASE_ID}}/ioc/enrich`, {{method:'POST', body: fd}})
      .then(r => r.json())
      .then(() => {{
        msg.style.color='#a6e3a1';
        msg.innerHTML = '<i class="fa fa-check me-1"></i>Queued. Results will appear below shortly.';
        setTimeout(() => enrichLoadResults_{case_id}(), 3500);
      }})
      .catch(() => {{
        msg.style.color='#f38ba8';
        msg.textContent = 'Request failed.';
      }});
  }};

  // ── Quick-enrich from IOC list ────────────────────────────────
  window[`enrichQuick_${{CASE_ID}}`] = function(iocType, iocValue, provider) {{
    document.getElementById(`enrich-val-${{CASE_ID}}`).value      = iocValue;
    document.getElementById(`enrich-type-${{CASE_ID}}`).value     = iocType;
    document.getElementById(`enrich-provider-${{CASE_ID}}`).value = provider;
    window[`enrichSubmit_${{CASE_ID}}`]();
    document.getElementById(`enrich-msg-${{CASE_ID}}`).scrollIntoView({{behavior:'smooth', block:'center'}});
  }};

  // ── Load IOC list ─────────────────────────────────────────────
  window[`enrichLoadIocs_${{CASE_ID}}`] = function() {{
    const div = document.getElementById(`enrich-iocs-${{CASE_ID}}`);
    div.innerHTML = '<span class="text-muted small"><i class="fa fa-spinner fa-spin me-1"></i>Loading…</span>';
    fetch(`/cases/${{CASE_ID}}/ioc/graph`)
      .then(r => r.json())
      .then(data => {{
        const nodes = data.nodes || [];
        if (!nodes.length) {{
          div.innerHTML = '<span class="text-muted small">No IOCs found in this case.</span>';
          return;
        }}
        const rows = nodes.map(n => {{
          const avail = SUPPORTED[n.type] || [];
          const btns  = avail.map(p => {{
            const ps = PROV_STYLE[p];
            return `<button class="btn btn-sm py-0" style="font-size:.65rem;border:1px solid ${{ps.color}}55;color:${{ps.color}};background:${{ps.color}}11"
                      onclick="enrichQuick_${{CASE_ID}}('${{n.type}}','${{n.full.replace(/'/g,"\\'")}}',$'${{p}}')">
                      <i class="fa ${{ps.icon}} me-1"></i>${{ps.label}}
                    </button>`;
          }}).join('');
          return `<tr>
            <td style="font-size:.78rem"><span class="badge" style="background:#31324488;color:#a6adc8;font-size:.65rem">${{n.type}}</span></td>
            <td style="font-size:.78rem;font-family:monospace;word-break:break-all">${{n.full}}</td>
            <td style="font-size:.72rem">${{n.count}}×</td>
            <td><div class="d-flex gap-1 flex-wrap">${{btns}}</div></td>
          </tr>`;
        }}).join('');
        div.innerHTML = `
          <div class="table-responsive">
            <table class="table table-sm table-hover mb-0">
              <thead class="small text-muted"><tr><th>Type</th><th>Value</th><th>Seen</th><th>Quick Enrich</th></tr></thead>
              <tbody>${{rows}}</tbody>
            </table>
          </div>`;
      }})
      .catch(() => {{ div.innerHTML = '<span class="text-danger small">Failed to load IOCs.</span>'; }});
  }};

  // ── Load results ──────────────────────────────────────────────
  window[`enrichLoadResults_${{CASE_ID}}`] = function() {{
    const div = document.getElementById(`enrich-results-${{CASE_ID}}`);
    fetch(`/cases/${{CASE_ID}}/ioc/enrichments`)
      .then(r => r.json())
      .then(results => {{
        if (!results.length) {{
          div.innerHTML = '<span class="text-muted small">No enrichment results yet. Use the panel above to enrich IOCs.</span>';
          return;
        }}
        const cards = results.map(r => {{
          const vs = VERDICT_STYLE[r.verdict] || VERDICT_STYLE.unknown;
          const ps = PROV_STYLE[r.provider]   || {{color:'#a6adc8', icon:'fa-question', label:r.provider}};
          const detail = JSON.stringify(r.result_json, null, 2);
          const link   = r.result_json?.link;
          return `
          <div class="mb-2 p-3 rounded" style="background:#181825;border:1px solid #313244">
            <div class="d-flex align-items-start gap-2 flex-wrap">
              <div>
                <span class="badge me-1" style="background:${{vs.color}}22;color:${{vs.color}};border:1px solid ${{vs.color}}55;font-size:.65rem">
                  <i class="fa ${{vs.icon}} me-1"></i>${{vs.label}}
                </span>
                <span class="badge" style="background:${{ps.color}}22;color:${{ps.color}};border:1px solid ${{ps.color}}55;font-size:.65rem">
                  <i class="fa ${{ps.icon}} me-1"></i>${{ps.label}}
                </span>
              </div>
              <div style="flex:1;min-width:0">
                <span class="badge me-1" style="background:#31324488;color:#a6adc8;font-size:.6rem">${{r.ioc_type}}</span>
                <code style="font-size:.8rem;word-break:break-all;color:#cdd6f4">${{r.ioc_value}}</code>
              </div>
              <div class="ms-auto d-flex gap-1 align-items-center flex-shrink-0">
                ${{link ? `<a href="${{link}}" target="_blank" class="btn btn-sm py-0 btn-outline-secondary" style="font-size:.65rem">View ↗</a>` : ''}}
                <button class="btn btn-sm py-0 btn-outline-secondary" style="font-size:.65rem"
                        onclick="this.closest('.mb-2').querySelector('.detail-json').classList.toggle('d-none')">
                  JSON
                </button>
                <button class="btn btn-sm py-0" style="font-size:.65rem;border:1px solid #f38ba855;color:#f38ba8"
                        onclick="enrichDelete_${{CASE_ID}}(${{r.id}}, this)">
                  <i class="fa fa-trash"></i>
                </button>
              </div>
            </div>
            <div class="mt-1" style="font-size:.75rem;color:#a6adc8">${{r.summary}}</div>
            <div class="text-muted" style="font-size:.68rem;margin-top:2px">
              ${{r.queried_at}}${{r.queried_by ? ' · ' + r.queried_by : ''}}
            </div>
            <pre class="detail-json d-none mt-2" style="font-size:.72rem;background:#1e1e2e;padding:8px;border-radius:4px;
                  overflow-x:auto;border:1px solid #313244;max-height:200px;color:#cdd6f4">${{detail}}</pre>
          </div>`;
        }}).join('');
        div.innerHTML = cards;
      }})
      .catch(() => {{ div.innerHTML = '<span class="text-danger small">Failed to load results.</span>'; }});
  }};

  window[`enrichDelete_${{CASE_ID}}`] = function(resultId, btn) {{
    if (!confirm('Delete this enrichment result?')) return;
    fetch(`/cases/${{CASE_ID}}/ioc/enrichments/${{resultId}}/delete`, {{method:'POST'}})
      .then(() => enrichLoadResults_{case_id}())
      .catch(() => alert('Delete failed.'));
  }};

  // Initial load
  enrichLoadIocs_{case_id}();
  enrichLoadResults_{case_id}();
}})();
</script>
"""
