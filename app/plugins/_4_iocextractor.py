"""
IOC Extractor plugin — regex-based extraction of IOCs from case notes and text.
"""
import re
import html as _html

TAB_LABEL = "IOC Extractor"
TAB_ICON  = "fa-crosshairs"

_PATTERNS = {
    "IPv4":    r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b',
    "SHA256":  r'\b[a-fA-F0-9]{64}\b',
    "MD5":     r'\b[a-fA-F0-9]{32}\b',
    "SHA1":    r'\b[a-fA-F0-9]{40}\b',
    "Email":   r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',
    "URL":     r'https?://[^\s<>"\'\]]+',
    "CVE":     r'CVE-\d{4}-\d{4,7}',
    "Domain":  r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,6}\b',
}

_PRIVATE_IP = re.compile(
    r'^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.0\.0\.0|255\.)'
)

_ICON = {
    "IPv4":   "fa-network-wired",
    "SHA256": "fa-hashtag",
    "MD5":    "fa-hashtag",
    "SHA1":   "fa-hashtag",
    "Email":  "fa-envelope",
    "URL":    "fa-link",
    "CVE":    "fa-bug",
    "Domain": "fa-globe",
}

_LOOKUPABLE = {"IPv4", "MD5", "SHA256", "SHA1", "Domain"}


def _extract(text: str) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {k: set() for k in _PATTERNS}
    for kind, pat in _PATTERNS.items():
        for m in re.finditer(pat, text):
            v = m.group()
            if kind == "IPv4" and _PRIVATE_IP.match(v):
                continue
            if kind == "Domain" and ("@" in text[max(0, m.start()-1):m.end()+1]):
                continue  # skip email addresses picked up as domains
            found[kind].add(v)
    # deduplicate: remove domains that are substrings of URLs already captured
    urls_lower = {u.lower() for u in found.get("URL", set())}
    found["Domain"] = {
        d for d in found["Domain"]
        if not any(d.lower() in u for u in urls_lower)
           and "." in d
    }
    return {k: sorted(v) for k, v in found.items() if v}


def render_tab(case) -> str:  # noqa: ANN001
    notes_text = case.notes or ""
    for ev in case.evidence:
        notes_text += f"\n{ev.file_name}"

    preloaded = _extract(notes_text)

    def _rows(kind: str, values: list[str]) -> str:
        icon = _ICON.get(kind, "fa-tag")
        ltype = "ip" if kind == "IPv4" else ("hash" if kind in ("MD5", "SHA256", "SHA1") else "domain")
        rows = ""
        for v in values:
            lookup_btn = ""
            if kind in _LOOKUPABLE:
                rows += (
                    f"<tr>"
                    f"<td><span class='badge bg-secondary'><i class='fa {icon} me-1'></i>{kind}</span></td>"
                    f"<td><code class='small'>{_html.escape(v)}</code></td>"
                    f"<td>"
                    f"<button class='btn btn-sm py-0 btn-outline-secondary' "
                    f"onclick=\"iocOsint('{ltype}','{_html.escape(v, quote=True)}')\">OSINT</button>"
                    f"</td>"
                    f"</tr>"
                )
            else:
                rows += (
                    f"<tr>"
                    f"<td><span class='badge bg-secondary'><i class='fa {icon} me-1'></i>{kind}</span></td>"
                    f"<td colspan='2'><code class='small'>{_html.escape(v)}</code></td>"
                    f"</tr>"
                )
        return rows

    preloaded_rows = ""
    preloaded_count = 0
    for kind, values in preloaded.items():
        preloaded_rows += _rows(kind, values)
        preloaded_count += len(values)

    case_id = case.id
    preloaded_section = f"""
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span><i class="fa fa-note-sticky me-1"></i>From Case Notes &amp; Evidence</span>
        <span class="badge bg-secondary">{preloaded_count} IOC{"s" if preloaded_count != 1 else ""}</span>
      </div>
      <div class="card-body p-0" style="max-height:320px;overflow-y:auto">
        {"<table class='table table-sm table-dark mb-0'><tbody>" + preloaded_rows + "</tbody></table>" if preloaded_rows else "<p class='text-muted small p-3 mb-0'>No IOCs found in case notes.</p>"}
      </div>
      <div class="card-footer d-flex gap-2 py-2">
        <a href="/cases/{case_id}/export/iocs.csv"
           class="btn btn-sm btn-outline-secondary" download>
          <i class="fa fa-file-csv me-1"></i>Export CSV
        </a>
        <a href="/cases/{case_id}/export/iocs.stix.json"
           class="btn btn-sm btn-outline-secondary" download>
          <i class="fa fa-file-code me-1"></i>Export STIX 2.1
        </a>
        <button class="btn btn-sm btn-outline-secondary ms-auto"
                onclick="iocPreview({case_id})">
          <i class="fa fa-list me-1"></i>Preview all
        </button>
      </div>
    </div>"""

    return f"""
<div class="row g-3 mt-1">

  <div class="col-md-6">
    {preloaded_section}

    <div id="ioc-preview-{case_id}" class="mt-2" style="display:none">
      <div class="card">
        <div class="card-header d-flex justify-content-between align-items-center">
          <span>All Extracted IOCs (JSON)</span>
          <button class="btn btn-sm py-0 btn-outline-secondary"
                  onclick="document.getElementById('ioc-preview-{case_id}').style.display='none'">
            <i class="fa fa-xmark"></i>
          </button>
        </div>
        <div class="card-body p-2">
          <pre id="ioc-preview-body-{case_id}" class="small mb-0" style="max-height:260px;overflow-y:auto"></pre>
        </div>
      </div>
    </div>
  </div>

  <div class="col-md-6">
    <div class="card">
      <div class="card-header"><i class="fa fa-crosshairs me-1"></i>Extract from Text</div>
      <div class="card-body">
        <textarea id="ioc-input" class="form-control font-monospace mb-2" rows="6"
                  placeholder="Paste any text, logs, or report…"></textarea>
        <button class="btn btn-sm btn-outline-secondary w-100" onclick="iocExtract()">
          <i class="fa fa-crosshairs me-1"></i>Extract IOCs
        </button>
      </div>
    </div>

    <div id="ioc-custom-result" class="mt-3" style="display:none">
      <div class="card">
        <div class="card-header d-flex justify-content-between">
          <span>Extracted IOCs</span>
          <button class="btn btn-sm py-0 btn-outline-secondary"
                  onclick="document.getElementById('ioc-custom-result').style.display='none'">
            <i class="fa fa-xmark"></i>
          </button>
        </div>
        <div class="card-body p-0" style="max-height:320px;overflow-y:auto">
          <table class="table table-sm table-dark mb-0">
            <tbody id="ioc-custom-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

</div>

<!-- OSINT result panel (shared with OSINT plugin if present) -->
<div id="ioc-osint-panel" class="mt-3" style="display:none">
  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      <span id="ioc-osint-title">OSINT Result</span>
      <button class="btn btn-sm py-0 btn-outline-secondary"
              onclick="document.getElementById('ioc-osint-panel').style.display='none'">
        <i class="fa fa-xmark"></i>
      </button>
    </div>
    <div class="card-body p-0">
      <table class="table table-sm table-dark mb-0"><tbody id="ioc-osint-tbody"></tbody></table>
    </div>
  </div>
</div>

<script>
(function() {{
  const PATTERNS = {{
    IPv4:   /\\b(?:(?:25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\.)({{3}})(?:25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\b/g,
    SHA256: /\\b[a-fA-F0-9]{{64}}\\b/g,
    MD5:    /\\b[a-fA-F0-9]{{32}}\\b/g,
    SHA1:   /\\b[a-fA-F0-9]{{40}}\\b/g,
    Email:  /\\b[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{{2,}}\\b/g,
    URL:    /https?:\\/\\/[^\\s<>"'\\]]+/g,
    CVE:    /CVE-\\d{{4}}-\\d{{4,7}}/g,
    Domain: /\\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\\-]{{0,61}}[a-zA-Z0-9])?\\.)+[a-zA-Z]{{2,6}}\\b/g,
  }};
  const PRIVATE = /^(10\\.|172\\.(1[6-9]|2\\d|3[01])\\.|192\\.168\\.|127\\.|0\\.0\\.0\\.0|255\\.)/;
  const LOOKUPTYPE = {{IPv4:'ip', MD5:'hash', SHA256:'hash', SHA1:'hash', Domain:'domain'}};

  window.iocExtract = function() {{
    const text = document.getElementById('ioc-input').value;
    const found = {{}};
    for (const [kind, pat] of Object.entries(PATTERNS)) {{
      const rx = new RegExp(pat.source, 'g');
      const matches = [...new Set([...text.matchAll(rx)].map(m => m[0]))];
      if (kind === 'IPv4') {{
        const filtered = matches.filter(ip => !PRIVATE.test(ip));
        if (filtered.length) found[kind] = filtered;
      }} else if (matches.length) {{
        found[kind] = matches;
      }}
    }}
    renderIocTable(found, 'ioc-custom-tbody');
    document.getElementById('ioc-custom-result').style.display = '';
  }};

  function renderIocTable(found, tbodyId) {{
    const tbody = document.getElementById(tbodyId);
    let html = '';
    for (const [kind, vals] of Object.entries(found)) {{
      for (const v of vals) {{
        const ltype = LOOKUPTYPE[kind];
        const btn   = ltype
          ? `<button class="btn btn-sm py-0 btn-outline-secondary" onclick="iocOsint('${{ltype}}','${{v.replace(/'/g,"\\\\'")}}')" >OSINT</button>`
          : '';
        html += `<tr><td><span class="badge bg-secondary">${{kind}}</span></td><td><code class="small">${{v}}</code></td><td>${{btn}}</td></tr>`;
      }}
    }}
    tbody.innerHTML = html || '<tr><td colspan="3" class="text-muted small p-3">No IOCs found.</td></tr>';
  }}

  window.iocPreview = async function(caseId) {{
    const div = document.getElementById('ioc-preview-' + caseId);
    const pre = document.getElementById('ioc-preview-body-' + caseId);
    if (div.style.display !== 'none') {{ div.style.display = 'none'; return; }}
    pre.textContent = 'Loading…';
    div.style.display = '';
    try {{
      const r = await fetch(`/cases/${{caseId}}/export/iocs`);
      const d = await r.json();
      pre.textContent = JSON.stringify(d, null, 2);
    }} catch(e) {{
      pre.textContent = 'Error: ' + e;
    }}
  }};

  window.iocOsint = async function(type, q) {{
    const panel = document.getElementById('ioc-osint-panel');
    const title = document.getElementById('ioc-osint-title');
    const tbody = document.getElementById('ioc-osint-tbody');
    title.textContent = type.toUpperCase() + ' — ' + q;
    tbody.innerHTML   = '<tr><td colspan="2"><span class="spinner-border spinner-border-sm me-1"></span>Looking up…</td></tr>';
    panel.style.display = '';
    try {{
      const r    = await fetch(`/api/lookup?type=${{type}}&q=${{encodeURIComponent(q)}}`);
      const data = await r.json();
      if (data.error) {{
        tbody.innerHTML = `<tr><td colspan="2" class="text-danger">${{data.error}}</td></tr>`;
        return;
      }}
      const isMalware = (data.Status || '').includes('MALWARE');
      let rows = '';
      for (const [k, v] of Object.entries(data)) {{
        const cls = (k === 'Status' && isMalware) ? 'text-danger fw-bold' : '';
        rows += `<tr><th class="ps-3 text-muted" style="width:35%;font-weight:normal">${{k}}</th><td class="font-monospace small ${{cls}}">${{v}}</td></tr>`;
      }}
      tbody.innerHTML = rows;
    }} catch(e) {{
      tbody.innerHTML = `<tr><td colspan="2" class="text-danger">${{e}}</td></tr>`;
    }}
  }};
}})();
</script>
"""
