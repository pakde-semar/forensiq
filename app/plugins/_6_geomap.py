"""
Geo IP Map plugin — plot all IPs from case notes and evidence on an interactive map.
"""
import re
import html as _html

TAB_LABEL = "Geo Map"
TAB_ICON  = "fa-map-location-dot"

_IPV4_RE    = re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')
_PRIVATE_RE = re.compile(r'^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|0\.0\.0\.0|255\.)')


def _public_ips(text: str) -> list[str]:
    return sorted({
        m for m in _IPV4_RE.findall(text)
        if not _PRIVATE_RE.match(m)
    })


def render_tab(case) -> str:  # noqa: ANN001
    notes_text = case.notes or ""
    for ev in case.evidence:
        notes_text += f"\n{ev.file_name}"

    found_ips = _public_ips(notes_text)
    ip_list_json = str(found_ips).replace("'", '"')
    ip_badges = "".join(
        f"<span class='badge bg-secondary me-1 mb-1 font-monospace'>{_html.escape(ip)}</span>"
        for ip in found_ips
    ) or "<span class='text-muted small'>No public IPs found in notes.</span>"

    return f"""
<div class="mt-2">
  <div class="d-flex justify-content-between align-items-start mb-2">
    <div>
      <h6 class="mb-1"><i class="fa fa-map-location-dot me-1"></i>IP Geolocation Map</h6>
      <div id="geo-badges">{ip_badges}</div>
    </div>
    <div class="d-flex gap-2">
      <input type="text" id="geo-extra-ip" class="form-control form-control-sm"
             placeholder="Add IP…" style="width:160px"
             onkeydown="if(event.key==='Enter')geoAddIp()">
      <button class="btn btn-sm btn-outline-secondary" onclick="geoAddIp()">Add</button>
      <button class="btn btn-sm btn-outline-secondary" onclick="geoLoadAll()" id="geo-load-btn">
        <i class="fa fa-play me-1"></i>Load Map
      </button>
    </div>
  </div>

  <div id="geo-progress" class="mb-2" style="display:none">
    <div class="progress" style="height:5px">
      <div id="geo-bar" class="progress-bar bg-info" style="width:0%"></div>
    </div>
    <small class="text-muted" id="geo-label">Looking up IPs…</small>
  </div>

  <div id="geo-map" style="height:440px;border-radius:8px;background:#1a1a2e">
    <div class="d-flex align-items-center justify-content-center h-100 text-muted">
      <i class="fa fa-map-location-dot fa-2x me-2"></i>Click "Load Map" to plot IPs
    </div>
  </div>
  <small class="text-muted">Map tiles: OpenStreetMap · Geo data: ipinfo.io</small>
</div>

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>

<script>
(function() {{
  let geoIps    = {ip_list_json};
  let leafletMap = null;

  window.geoAddIp = function() {{
    const inp = document.getElementById('geo-extra-ip');
    const ip  = inp.value.trim();
    if (!ip) return;
    if (!geoIps.includes(ip)) {{
      geoIps.push(ip);
      const badge = document.createElement('span');
      badge.className = 'badge bg-info me-1 mb-1 font-monospace';
      badge.textContent = ip;
      document.getElementById('geo-badges').appendChild(badge);
    }}
    inp.value = '';
  }};

  window.geoLoadAll = async function() {{
    const btn = document.getElementById('geo-load-btn');
    btn.disabled = true;
    const progress = document.getElementById('geo-progress');
    const bar      = document.getElementById('geo-bar');
    const label    = document.getElementById('geo-label');
    progress.style.display = '';

    // Init map
    if (leafletMap) leafletMap.remove();
    document.getElementById('geo-map').innerHTML = '';
    leafletMap = L.map('geo-map').setView([20, 0], 2);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 18,
      attribution: '© OpenStreetMap'
    }}).addTo(leafletMap);

    const results = [];
    for (let i = 0; i < geoIps.length; i++) {{
      const ip = geoIps[i];
      bar.style.width   = Math.round((i + 1) / geoIps.length * 100) + '%';
      label.textContent = `Looking up ${{ip}} (${{i+1}}/${{geoIps.length}})…`;
      try {{
        const r    = await fetch(`/api/lookup?type=ip&q=${{encodeURIComponent(ip)}}`);
        const data = await r.json();
        // ipinfo returns no loc for bogons
        const loc = data.loc || (data.Latitude ? `${{data.Latitude}},${{data.Longitude}}` : null);
        // Our lookup returns City/Country not lat/lon — need raw loc
        // Fetch raw ipinfo directly for lat/lon
        const raw  = await fetch(`https://ipinfo.io/${{ip}}/json`);
        const rdata = await raw.json();
        if (rdata.loc) {{
          const [lat, lon] = rdata.loc.split(',').map(Number);
          const popup = [
            `<b>${{ip}}</b>`,
            rdata.org || '',
            [rdata.city, rdata.region, rdata.country].filter(Boolean).join(', '),
          ].join('<br>');
          L.marker([lat, lon])
           .addTo(leafletMap)
           .bindPopup(popup);
          results.push({{ip, lat, lon}});
        }}
      }} catch(e) {{ /* skip */ }}
    }}

    if (results.length > 1) {{
      const bounds = L.latLngBounds(results.map(r => [r.lat, r.lon]));
      leafletMap.fitBounds(bounds, {{padding: [40, 40]}});
    }} else if (results.length === 1) {{
      leafletMap.setView([results[0].lat, results[0].lon], 6);
    }}

    progress.style.display = 'none';
    label.textContent = `Done — ${{results.length}} IP${{results.length !== 1 ? 's' : ''}} plotted.`;
    progress.style.display = '';
    bar.style.width = '100%';
    btn.disabled = false;
  }};
}})();
</script>
"""
