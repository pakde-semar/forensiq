"""
Email Header Analyzer plugin — parse raw email headers for forensic indicators.
"""
TAB_LABEL = "Email Header"
TAB_ICON  = "fa-envelope-open-text"


def render_tab(case) -> str:  # noqa: ANN001
    return """
<div class="row g-3 mt-1">
  <div class="col-md-5">
    <div class="card">
      <div class="card-header"><i class="fa fa-envelope-open-text me-1"></i>Paste Email Headers</div>
      <div class="card-body">
        <textarea id="eh-input" class="form-control font-monospace mb-2" rows="14"
                  placeholder="Paste full email headers here (Received:, From:, Authentication-Results:, …)"></textarea>
        <button class="btn btn-sm btn-outline-secondary w-100" onclick="ehAnalyze()">
          <i class="fa fa-magnifying-glass me-1"></i>Analyze
        </button>
        <div id="eh-spinner" class="mt-2 small text-muted" style="display:none">
          <span class="spinner-border spinner-border-sm me-1"></span>Analyzing…
        </div>
      </div>
    </div>
  </div>
  <div class="col-md-7">
    <div id="eh-result" style="display:none">

      <div class="card mb-3">
        <div class="card-header"><i class="fa fa-circle-info me-1"></i>Summary</div>
        <div class="card-body p-0">
          <table class="table table-sm table-dark mb-0">
            <tbody id="eh-summary-tbody"></tbody>
          </table>
        </div>
      </div>

      <div class="card mb-3" id="eh-auth-card">
        <div class="card-header"><i class="fa fa-shield-halved me-1"></i>Authentication</div>
        <div class="card-body p-0">
          <table class="table table-sm table-dark mb-0">
            <tbody id="eh-auth-tbody"></tbody>
          </table>
        </div>
      </div>

      <div class="card mb-3" id="eh-hops-card">
        <div class="card-header"><i class="fa fa-route me-1"></i>Routing Hops</div>
        <div class="card-body p-0" style="overflow-x:auto">
          <table class="table table-sm table-dark mb-0">
            <thead><tr><th>#</th><th>From</th><th>By</th><th>IP</th><th>Timestamp</th></tr></thead>
            <tbody id="eh-hops-tbody"></tbody>
          </table>
        </div>
      </div>

      <div id="eh-warnings" class="mb-3"></div>

    </div>
  </div>
</div>

<script>
(function() {
  const IP_RE = /\\b(?:(?:25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\.){3}(?:25[0-5]|2[0-4]\\d|[01]?\\d\\d?)\\b/;
  const PRIVATE_RE = /^(10\\.|172\\.(1[6-9]|2\\d|3[01])\\.|192\\.168\\.|127\\.)/;

  window.ehAnalyze = async function() {
    const raw = document.getElementById('eh-input').value.trim();
    if (!raw) return;
    document.getElementById('eh-spinner').style.display = '';
    document.getElementById('eh-result').style.display  = 'none';
    try {
      const r    = await fetch('/api/email-header', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({headers: raw}),
      });
      const data = await r.json();
      renderEmailResult(data);
    } catch(e) {
      alert('Error: ' + e);
    } finally {
      document.getElementById('eh-spinner').style.display = 'none';
    }
  };

  function badge(val, good, bad) {
    if (!val) return '<span class="badge bg-secondary">unknown</span>';
    val = val.toLowerCase();
    if (good && good.some(g => val.includes(g))) return `<span class="badge bg-success">${val}</span>`;
    if (bad  && bad.some(b => val.includes(b)))  return `<span class="badge bg-danger">${val}</span>`;
    return `<span class="badge bg-warning text-dark">${val}</span>`;
  }

  function renderEmailResult(d) {
    // Summary
    const sum = d.summary || {};
    let sumRows = '';
    const sumFields = [
      ['From',       sum.from       || '–'],
      ['To',         sum.to         || '–'],
      ['Subject',    sum.subject    || '–'],
      ['Date',       sum.date       || '–'],
      ['Message-ID', sum.message_id || '–'],
      ['X-Mailer',   sum.x_mailer   || '–'],
      ['Reply-To',   sum.reply_to   || '–'],
    ];
    for (const [k,v] of sumFields)
      sumRows += `<tr><th class="ps-3 text-muted" style="width:30%;font-weight:normal">${k}</th><td class="pe-3 font-monospace small">${v}</td></tr>`;
    document.getElementById('eh-summary-tbody').innerHTML = sumRows;

    // Auth
    const auth = d.auth || {};
    const authRows = `
      <tr><th class="ps-3 text-muted" style="width:30%;font-weight:normal">SPF</th>
          <td class="pe-3">${badge(auth.spf, ['pass'], ['fail','softfail','none'])}</td></tr>
      <tr><th class="ps-3 text-muted" style="font-weight:normal">DKIM</th>
          <td class="pe-3">${badge(auth.dkim, ['pass'], ['fail','none'])}</td></tr>
      <tr><th class="ps-3 text-muted" style="font-weight:normal">DMARC</th>
          <td class="pe-3">${badge(auth.dmarc, ['pass'], ['fail','none'])}</td></tr>
    `;
    document.getElementById('eh-auth-tbody').innerHTML = authRows;

    // Hops
    const hops = d.hops || [];
    let hopRows = '';
    hops.forEach((h, i) => {
      const ipCell = h.ip
        ? (PRIVATE_RE.test(h.ip)
            ? `<span class="text-muted">${h.ip}</span>`
            : `<button class="btn btn-sm py-0 btn-outline-secondary" onclick="window.iocOsint&&iocOsint('ip','${h.ip}')">${h.ip}</button>`)
        : '–';
      hopRows += `<tr><td>${i+1}</td><td class="small">${h.from||'–'}</td><td class="small">${h.by||'–'}</td><td>${ipCell}</td><td class="small">${h.ts||'–'}</td></tr>`;
    });
    document.getElementById('eh-hops-tbody').innerHTML = hopRows || '<tr><td colspan="5" class="text-muted small">No Received: headers found.</td></tr>';

    // Warnings
    const warns = d.warnings || [];
    const wDiv = document.getElementById('eh-warnings');
    if (warns.length) {
      wDiv.innerHTML = warns.map(w =>
        `<div class="alert alert-warning py-2 px-3 mb-2"><i class="fa fa-triangle-exclamation me-1"></i>${w}</div>`
      ).join('');
    } else {
      wDiv.innerHTML = '<div class="alert alert-success py-2 px-3"><i class="fa fa-check me-1"></i>No obvious anomalies detected.</div>';
    }

    document.getElementById('eh-result').style.display = '';
  }
})();
</script>
"""
