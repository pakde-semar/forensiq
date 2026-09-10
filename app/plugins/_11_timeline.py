"""
Timeline plugin — chronological visual of all case events.
"""

TAB_LABEL = "Timeline"
TAB_ICON  = "fa-timeline"


def render_tab(case) -> str:
    case_id = case.id

    return f"""
<div class="row g-2 mt-1" id="tl-root-{case_id}">

  <!-- Filter bar -->
  <div class="col-12">
    <div class="d-flex flex-wrap gap-2 align-items-center mb-2">
      <span class="text-muted small me-1"><i class="fa fa-filter me-1"></i>Filter:</span>

      <div id="tl-cats" class="d-flex flex-wrap gap-1">
        <!-- populated by JS -->
      </div>

      <div class="ms-auto d-flex gap-2 align-items-center">
        <input type="date" id="tl-from-{case_id}" class="form-control form-control-sm"
               style="width:140px" title="From date">
        <span class="text-muted small">—</span>
        <input type="date" id="tl-to-{case_id}" class="form-control form-control-sm"
               style="width:140px" title="To date">
        <button class="btn btn-sm btn-outline-secondary py-0"
                onclick="tlClearFilters_{case_id}()">
          <i class="fa fa-xmark"></i>
        </button>
      </div>
    </div>

    <div id="tl-count-{case_id}" class="text-muted small mb-3"></div>
  </div>

  <!-- Timeline -->
  <div class="col-12">
    <div id="tl-feed-{case_id}" style="position:relative;padding-left:32px;">
      <!-- vertical line -->
      <div style="position:absolute;left:10px;top:0;bottom:0;width:2px;background:#313244;"></div>
      <div class="text-muted small p-3"><i class="fa fa-spinner fa-spin me-2"></i>Loading…</div>
    </div>
  </div>
</div>

<style>
.tl-event {{
  position: relative;
  margin-bottom: 14px;
  display: flex;
  gap: 12px;
  align-items: flex-start;
}}
.tl-dot {{
  position: absolute;
  left: -27px;
  top: 4px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #313244;
  border: 2px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 7px;
}}
.tl-body {{
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 6px;
  padding: 8px 12px;
  flex: 1;
  min-width: 0;
}}
.tl-body:hover {{ border-color: #45475a; }}
.tl-head {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.tl-title {{
  font-size: .83rem;
  font-weight: 600;
  color: #cdd6f4;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.tl-detail {{
  font-size: .75rem;
  color: #6c7086;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.tl-ts {{
  font-size: .7rem;
  color: #6c7086;
  white-space: nowrap;
  flex-shrink: 0;
}}
.cat-pill {{
  font-size: .72rem;
  padding: 2px 8px;
  border-radius: 12px;
  border: 1px solid;
  cursor: pointer;
  background: transparent;
  transition: background .1s;
  display: flex;
  align-items: center;
  gap: 4px;
}}
.cat-pill.active {{ color: #1e1e2e !important; }}
.tl-date-sep {{
  font-size: .7rem;
  color: #6c7086;
  padding: 6px 0 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}}
.tl-date-sep::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: #313244;
}}
</style>

<script>
(function() {{
  const CASE_ID = {case_id};

  const CATS = {{
    case:       {{ label: 'Case',        icon: 'fa-folder-plus',           color: '#cba6f7' }},
    evidence:   {{ label: 'Evidence',    icon: 'fa-box-archive',           color: '#89b4fa' }},
    audit:      {{ label: 'Audit',       icon: 'fa-clipboard-list',        color: '#a6adc8' }},
    pipeline:   {{ label: 'Pipeline',    icon: 'fa-diagram-project',       color: '#b4befe' }},
    coc:        {{ label: 'CoC',         icon: 'fa-arrow-right-arrow-left',color: '#fab387' }},
    time:       {{ label: 'Time',        icon: 'fa-clock',                 color: '#a6e3a1' }},
    yara:       {{ label: 'Yara',        icon: 'fa-shield-halved',         color: '#f38ba8' }},
    hashverify: {{ label: 'Hash',        icon: 'fa-shield-check',          color: '#94e2d5' }},
    notes:      {{ label: 'Notes',       icon: 'fa-file-alt',              color: '#f9e2af' }},
  }};

  let allEvents  = [];
  let activeCategories = new Set(Object.keys(CATS));

  // Build filter pills
  const pillsDiv = document.getElementById('tl-cats');
  Object.entries(CATS).forEach(([key, cfg]) => {{
    const btn = document.createElement('button');
    btn.className = 'cat-pill active';
    btn.dataset.cat = key;
    btn.style.borderColor = cfg.color;
    btn.style.color       = cfg.color;
    btn.style.background  = cfg.color + '22';
    btn.innerHTML = `<i class="fa ${{cfg.icon}}" style="font-size:.65rem"></i>${{cfg.label}}`;
    btn.onclick = () => toggleCat(key, btn, cfg.color);
    pillsDiv.appendChild(btn);
  }});

  function toggleCat(key, btn, color) {{
    if (activeCategories.has(key)) {{
      activeCategories.delete(key);
      btn.classList.remove('active');
      btn.style.background = 'transparent';
    }} else {{
      activeCategories.add(key);
      btn.classList.add('active');
      btn.style.background = color + '22';
    }}
    render();
  }}

  window[`tlClearFilters_${{CASE_ID}}`] = function() {{
    activeCategories = new Set(Object.keys(CATS));
    pillsDiv.querySelectorAll('.cat-pill').forEach(b => {{
      const cat = CATS[b.dataset.cat];
      b.classList.add('active');
      b.style.background = cat.color + '22';
    }});
    document.getElementById(`tl-from-${{CASE_ID}}`).value = '';
    document.getElementById(`tl-to-${{CASE_ID}}`).value   = '';
    render();
  }};

  document.getElementById(`tl-from-${{CASE_ID}}`).addEventListener('change', render);
  document.getElementById(`tl-to-${{CASE_ID}}`).addEventListener('change', render);

  function filtered() {{
    const from = document.getElementById(`tl-from-${{CASE_ID}}`).value;
    const to   = document.getElementById(`tl-to-${{CASE_ID}}`).value;
    return allEvents.filter(e => {{
      if (!activeCategories.has(e.category)) return false;
      if (from && e.ts && e.ts < from) return false;
      if (to   && e.ts && e.ts > to + 'T23:59:59') return false;
      return true;
    }});
  }}

  function render() {{
    const events = filtered();
    const feed   = document.getElementById(`tl-feed-${{CASE_ID}}`);
    const count  = document.getElementById(`tl-count-${{CASE_ID}}`);

    count.textContent = `${{events.length}} event${{events.length !== 1 ? 's' : ''}}`;

    if (!events.length) {{
      feed.innerHTML = '<div style="position:absolute;left:10px;top:0;bottom:0;width:2px;background:#313244;"></div>' +
        '<div class="text-muted small p-3">No events match the current filter.</div>';
      return;
    }}

    let html = '<div style="position:absolute;left:10px;top:0;bottom:0;width:2px;background:#313244;"></div>';
    let lastDate = '';

    events.forEach(ev => {{
      const cfg      = CATS[ev.category] || {{ color: '#a6adc8', icon: 'fa-circle' }};
      const evDate   = ev.ts ? ev.ts.substring(0, 10) : '';
      const evTime   = ev.dt ? ev.dt.substring(11)   : '';

      if (evDate !== lastDate) {{
        html += `<div class="tl-date-sep">${{evDate || 'Unknown date'}}</div>`;
        lastDate = evDate;
      }}

      const titleHtml = ev.link
        ? `<a href="${{ev.link}}" class="tl-title" style="color:${{cfg.color}};text-decoration:none">${{ev.title}}</a>`
        : `<span class="tl-title">${{ev.title}}</span>`;

      html += `
      <div class="tl-event">
        <div class="tl-dot" style="border-color:${{ev.color || cfg.color}}">
          <i class="fa ${{ev.icon || cfg.icon}}" style="color:${{ev.color || cfg.color}};font-size:7px"></i>
        </div>
        <div class="tl-body">
          <div class="tl-head">
            ${{titleHtml}}
            <span class="tl-ts">${{evTime}}</span>
            <span class="badge" style="background:${{cfg.color}}22;color:${{cfg.color}};border:1px solid ${{cfg.color}}44;font-size:.6rem">
              ${{cfg.label}}
            </span>
          </div>
          ${{ev.detail ? `<div class="tl-detail">${{ev.detail}}</div>` : ''}}
        </div>
      </div>`;
    }});

    feed.innerHTML = html;
  }}

  // Load events
  fetch(`/cases/${{CASE_ID}}/timeline/events`)
    .then(r => r.json())
    .then(data => {{
      allEvents = data;
      render();
    }})
    .catch(() => {{
      document.getElementById(`tl-feed-${{CASE_ID}}`).innerHTML =
        '<div class="text-danger small p-3">Failed to load timeline.</div>';
    }});
}})();
</script>
"""
