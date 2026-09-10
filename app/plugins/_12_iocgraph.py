"""
IOC Relationship Graph — D3.js force-directed visualization of IOC connections.
"""

TAB_LABEL = "IOC Graph"
TAB_ICON  = "fa-circle-nodes"


# Node color palette by IOC type (Catppuccin Mocha)
_TYPE_COLOR = {
    "IPv4":   "#89b4fa",   # blue
    "Domain": "#cba6f7",   # mauve
    "MD5":    "#fab387",   # peach
    "SHA256": "#f9e2af",   # yellow
    "SHA1":   "#94e2d5",   # teal
    "Email":  "#a6e3a1",   # green
    "URL":    "#74c7ec",   # sapphire
    "CVE":    "#f38ba8",   # red
}
_DEFAULT_COLOR = "#a6adc8"


def render_tab(case) -> str:
    case_id = case.id

    type_colors_js = str(_TYPE_COLOR).replace("'", '"')

    return f"""
<div id="iocg-root-{case_id}" style="display:flex;flex-direction:column;height:calc(100vh - 200px);min-height:420px">

  <!-- toolbar -->
  <div class="d-flex flex-wrap gap-2 align-items-center mb-2 flex-shrink-0">
    <span class="text-muted small"><i class="fa fa-circle-nodes me-1"></i>IOC Graph</span>
    <div id="iocg-pills-{case_id}" class="d-flex flex-wrap gap-1 ms-2"></div>
    <div class="ms-auto d-flex gap-2">
      <button class="btn btn-sm btn-outline-secondary py-0" onclick="iocgReload_{case_id}()" title="Reload">
        <i class="fa fa-rotate-right"></i>
      </button>
      <button class="btn btn-sm btn-outline-secondary py-0" onclick="iocgReset_{case_id}()" title="Reset zoom">
        <i class="fa fa-compress"></i>
      </button>
    </div>
  </div>

  <!-- stats bar -->
  <div id="iocg-stats-{case_id}" class="text-muted small mb-2 flex-shrink-0"></div>

  <!-- main area -->
  <div style="display:flex;flex:1;gap:12px;min-height:0">

    <!-- graph canvas -->
    <div style="flex:1;background:#181825;border:1px solid #313244;border-radius:6px;position:relative;overflow:hidden">
      <svg id="iocg-svg-{case_id}" width="100%" height="100%"></svg>
      <div id="iocg-empty-{case_id}" class="text-muted small"
           style="display:none;position:absolute;inset:0;display:flex;align-items:center;justify-content:center">
        No IOCs found in this case.
      </div>
      <div id="iocg-loading-{case_id}"
           style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:#181825">
        <span class="text-muted small"><i class="fa fa-spinner fa-spin me-2"></i>Loading graph…</span>
      </div>
    </div>

    <!-- detail panel -->
    <div id="iocg-detail-{case_id}"
         style="width:240px;flex-shrink:0;background:#1e1e2e;border:1px solid #313244;border-radius:6px;
                padding:14px;overflow-y:auto;display:none">
      <div style="font-size:.75rem;font-weight:600;color:#cdd6f4;margin-bottom:10px">
        <i class="fa fa-circle-info me-1"></i>Node Detail
      </div>
      <div id="iocg-detail-body-{case_id}" style="font-size:.78rem"></div>
    </div>
  </div>

  <!-- legend -->
  <div id="iocg-legend-{case_id}" class="d-flex flex-wrap gap-3 mt-2 flex-shrink-0" style="font-size:.72rem;color:#6c7086"></div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
(function() {{
  const CASE_ID    = {case_id};
  const TYPE_COLOR = {type_colors_js};
  const DEF_COLOR  = "{_DEFAULT_COLOR}";

  function color(type) {{ return TYPE_COLOR[type] || DEF_COLOR; }}

  // -- State ----------------------------------------------------------------
  let simulation, allNodes = [], allEdges = [], hiddenTypes = new Set();

  // -- Elements -------------------------------------------------------------
  const svg     = d3.select(`#iocg-svg-${{CASE_ID}}`);
  const loading = document.getElementById(`iocg-loading-${{CASE_ID}}`);
  const empty   = document.getElementById(`iocg-empty-${{CASE_ID}}`);
  const stats   = document.getElementById(`iocg-stats-${{CASE_ID}}`);
  const detail  = document.getElementById(`iocg-detail-${{CASE_ID}}`);
  const detBody = document.getElementById(`iocg-detail-body-${{CASE_ID}}`);
  const legend  = document.getElementById(`iocg-legend-${{CASE_ID}}`);
  const pills   = document.getElementById(`iocg-pills-${{CASE_ID}}`);

  // Zoom layer
  let gMain;
  const zoom = d3.zoom()
    .scaleExtent([0.1, 8])
    .on("zoom", e => gMain && gMain.attr("transform", e.transform));

  function initSvg() {{
    svg.selectAll("*").remove();
    svg.call(zoom);
    gMain = svg.append("g");

    // arrow marker
    svg.append("defs").append("marker")
      .attr("id", `arrow-${{CASE_ID}}`)
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 18).attr("refY", 0)
      .attr("markerWidth", 5).attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "#45475a");
  }}

  // -- Render graph ---------------------------------------------------------
  function render() {{
    const visNodes = allNodes.filter(n => !hiddenTypes.has(n.type));
    const visIds   = new Set(visNodes.map(n => n.id));
    const visEdges = allEdges.filter(e => visIds.has(e.source.id || e.source) && visIds.has(e.target.id || e.target));

    initSvg();
    if (!visNodes.length) {{ empty.style.display = 'flex'; return; }}
    empty.style.display = 'none';

    // Get SVG dimensions
    const w = svg.node().clientWidth  || 800;
    const h = svg.node().clientHeight || 500;

    // Edge layer
    const link = gMain.append("g").selectAll("line")
      .data(visEdges)
      .join("line")
        .attr("stroke", "#45475a")
        .attr("stroke-opacity", 0.7)
        .attr("stroke-width", d => Math.min(4, 1 + d.weight * 0.8));

    // Node layer
    const node = gMain.append("g").selectAll("g")
      .data(visNodes)
      .join("g")
        .attr("cursor", "pointer")
        .call(d3.drag()
          .on("start", dragStart)
          .on("drag",  dragging)
          .on("end",   dragEnd))
        .on("click", (evt, d) => {{ evt.stopPropagation(); showDetail(d); }});

    // radius: 6–18 based on count
    const rScale = d3.scaleSqrt().domain([1, d3.max(visNodes, n => n.count) || 1]).range([6, 18]);

    node.append("circle")
      .attr("r",           d => rScale(d.count))
      .attr("fill",        d => color(d.type) + "33")
      .attr("stroke",      d => color(d.type))
      .attr("stroke-width", 1.5);

    node.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", d => rScale(d.count) + 10)
      .attr("fill", "#a6adc8")
      .attr("font-size", "9px")
      .attr("pointer-events", "none")
      .text(d => d.label);

    // Click background to deselect
    svg.on("click", () => {{ detail.style.display = 'none'; }});

    // Simulation
    if (simulation) simulation.stop();
    simulation = d3.forceSimulation(visNodes)
      .force("link",   d3.forceLink(visEdges).id(d => d.id).distance(80).strength(0.5))
      .force("charge", d3.forceManyBody().strength(-150))
      .force("center", d3.forceCenter(w / 2, h / 2))
      .force("collide",d3.forceCollide().radius(d => rScale(d.count) + 8))
      .on("tick", () => {{
        link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
        node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
      }});
  }}

  function dragStart(evt, d) {{
    if (!evt.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x; d.fy = d.y;
  }}
  function dragging(evt, d) {{ d.fx = evt.x; d.fy = evt.y; }}
  function dragEnd(evt, d) {{
    if (!evt.active) simulation.alphaTarget(0);
    d.fx = null; d.fy = null;
  }}

  // -- Detail panel ---------------------------------------------------------
  function showDetail(d) {{
    const c = color(d.type);
    detBody.innerHTML = `
      <div style="background:${{c}}22;border:1px solid ${{c}}55;border-radius:4px;padding:6px 8px;margin-bottom:10px">
        <span style="font-size:.65rem;color:${{c}};font-weight:600;text-transform:uppercase">${{d.type}}</span>
        <div style="color:#cdd6f4;word-break:break-all;margin-top:3px;font-size:.8rem">${{d.full}}</div>
      </div>
      <div style="color:#6c7086;font-size:.72rem">Occurrences: <span style="color:#cdd6f4">${{d.count}}</span></div>
      <button onclick="navigator.clipboard.writeText('${{d.full.replace(/'/g, "\\'")}}')"
              class="btn btn-sm btn-outline-secondary py-0 mt-2 w-100" style="font-size:.7rem">
        <i class="fa fa-copy me-1"></i>Copy value
      </button>
    `;
    detail.style.display = 'block';
  }}

  // -- Filter pills ---------------------------------------------------------
  function buildPills(types) {{
    pills.innerHTML = '';
    [...types].sort().forEach(type => {{
      const c   = color(type);
      const btn = document.createElement('button');
      btn.className = 'btn btn-sm py-0';
      btn.style.cssText = `font-size:.68rem;border:1px solid ${{c}};color:${{c}};background:${{c}}22;border-radius:12px;padding:1px 8px`;
      btn.innerHTML = type;
      btn.dataset.type = type;
      btn.onclick = () => {{
        if (hiddenTypes.has(type)) {{
          hiddenTypes.delete(type);
          btn.style.background = c + '22';
          btn.style.opacity    = '1';
        }} else {{
          hiddenTypes.add(type);
          btn.style.background = 'transparent';
          btn.style.opacity    = '0.4';
        }}
        render();
      }};
      pills.appendChild(btn);
    }});
  }}

  // -- Legend ---------------------------------------------------------------
  function buildLegend(types) {{
    legend.innerHTML = '';
    [...types].sort().forEach(type => {{
      const c  = color(type);
      const el = document.createElement('span');
      el.innerHTML = `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{c}};margin-right:4px;border:1px solid ${{c}}"></span>${{type}}`;
      legend.appendChild(el);
    }});
  }}

  // -- Load data ------------------------------------------------------------
  function iocgReload_{case_id}() {{
    loading.style.display = 'flex';
    detail.style.display  = 'none';
    hiddenTypes.clear();
    fetch(`/cases/${{CASE_ID}}/ioc/graph`)
      .then(r => r.json())
      .then(data => {{
        allNodes = data.nodes;
        allEdges = data.edges;
        const s  = data.stats;
        stats.textContent = `${{s.node_count}} nodes · ${{s.edge_count}} edges · ${{s.ioc_count}} IOCs extracted`;

        const types = new Set(allNodes.map(n => n.type));
        buildPills(types);
        buildLegend(types);

        loading.style.display = 'none';
        render();
      }})
      .catch(() => {{
        loading.innerHTML = '<span class="text-danger small">Failed to load graph data.</span>';
      }});
  }}

  window[`iocgReset_${{CASE_ID}}`] = function() {{
    svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
  }};
  window[`iocgReload_${{CASE_ID}}`] = iocgReload_{case_id};

  // Resize observer → re-render when tab becomes visible or container resizes
  const ro = new ResizeObserver(() => {{ if (allNodes.length) render(); }});
  ro.observe(document.getElementById(`iocg-svg-${{CASE_ID}}`));

  iocgReload_{case_id}();
}})();
</script>
"""
