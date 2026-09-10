"""
Evidence Preview & Hex Viewer — embedded split-panel viewer for the case detail tab.
"""

TAB_LABEL = "Preview"
TAB_ICON  = "fa-eye"

_EXT_ICON = {
    # images
    "png":"fa-image","jpg":"fa-image","jpeg":"fa-image","gif":"fa-image",
    "bmp":"fa-image","webp":"fa-image","svg":"fa-image","tiff":"fa-image",
    # video
    "mp4":"fa-film","webm":"fa-film","mov":"fa-film","mkv":"fa-film","avi":"fa-film",
    # audio
    "mp3":"fa-music","wav":"fa-music","flac":"fa-music","ogg":"fa-music","m4a":"fa-music",
    # docs
    "pdf":"fa-file-pdf","txt":"fa-file-lines","log":"fa-file-lines","csv":"fa-table",
    "md":"fa-file-lines","json":"fa-code","xml":"fa-code","yaml":"fa-code","yml":"fa-code",
    # code
    "py":"fa-code","js":"fa-code","ts":"fa-code","sh":"fa-code","ps1":"fa-code",
    "html":"fa-code","css":"fa-code","sql":"fa-database","go":"fa-code","rs":"fa-code",
    # archives
    "zip":"fa-file-zipper","gz":"fa-file-zipper","tar":"fa-file-zipper",
    "rar":"fa-file-zipper","7z":"fa-file-zipper",
    # executable
    "exe":"fa-gear","dll":"fa-gear","elf":"fa-gear",
}

_TEXT_EXT = {
    'txt','log','csv','tsv','md','rst','json','xml','yaml','yml','toml','ini','conf','cfg',
    'py','js','ts','sh','bash','zsh','ps1','bat','cmd','html','htm','css','sql',
    'go','rs','java','c','cpp','h','rb','php','r','lua','pl','swift','kt','tf',
}
_IMG_EXT  = {'png','jpg','jpeg','gif','bmp','webp','svg','tiff','tif','ico'}
_VID_EXT  = {'mp4','webm','mov','ogv','mkv','avi','wmv'}
_AUD_EXT  = {'mp3','wav','ogg','flac','m4a','aac','opus'}
_PDF_EXT  = {'pdf'}

def _kind(ev) -> str:
    ext = ev.file_name.rsplit('.', 1)[-1].lower() if '.' in ev.file_name else ''
    if ext in _IMG_EXT: return 'image'
    if ext in _VID_EXT: return 'video'
    if ext in _AUD_EXT: return 'audio'
    if ext in _PDF_EXT: return 'pdf'
    if ext in _TEXT_EXT: return 'text'
    return 'binary'

def _ev_icon(ev) -> str:
    ext = ev.file_name.rsplit('.', 1)[-1].lower() if '.' in ev.file_name else ''
    return _EXT_ICON.get(ext, 'fa-file')

def _fmt_size(n: int) -> str:
    for unit in ('B','KB','MB','GB'):
        if n < 1024: return f'{n:.0f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


def render_tab(case) -> str:
    case_id  = case.id
    evidence = sorted(case.evidence or [], key=lambda e: e.evidence_number)

    if not evidence:
        return '<div class="text-muted small p-4 text-center">No evidence files in this case.</div>'

    ev_rows = ""
    for ev in evidence:
        icon = _ev_icon(ev)
        kind = _kind(ev)
        sz   = _fmt_size(ev.file_size) if ev.file_size else "?"
        ev_rows += f"""
        <div class="evrow d-flex align-items-center gap-2 px-2 py-2"
             style="border-bottom:1px solid #31324430;cursor:pointer;border-radius:4px"
             onclick="pvLoad_{case_id}({ev.id},'{ev.file_name.replace("'","\\'")}','{kind}')"
             onmouseover="this.style.background='#31324455'"
             onmouseout="this.style.background=''">
          <i class="fa {icon}" style="color:#89b4fa;width:14px;text-align:center;font-size:.8rem"></i>
          <div style="flex:1;min-width:0">
            <div style="font-size:.78rem;color:#cdd6f4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                 title="{ev.file_name}">{ev.file_name}</div>
            <div style="font-size:.65rem;color:#6c7086">{ev.evidence_number} · {sz}</div>
          </div>
        </div>"""

    return f"""
<div id="pvroot-{case_id}" style="display:flex;gap:0;min-height:520px;overflow:hidden;border:1px solid #31324488;border-radius:8px">

  <!-- Left: evidence list -->
  <div style="width:240px;min-width:200px;border-right:1px solid #31324488;
              overflow-y:auto;padding:6px 4px;background:#1e1e2e30;flex-shrink:0">
    <div style="font-size:.68rem;color:#6c7086;padding:4px 8px 6px;text-transform:uppercase;letter-spacing:.06em">
      {len(evidence)} file(s)
    </div>
    {ev_rows}
  </div>

  <!-- Right: preview -->
  <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">

    <!-- toolbar -->
    <div id="pvbar-{case_id}"
         style="display:flex;align-items:center;gap:8px;padding:6px 12px;
                background:#181825;border-bottom:1px solid #31324488;flex-shrink:0">
      <span id="pvtitle-{case_id}" style="font-size:.78rem;color:#6c7086;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
        Select a file to preview
      </span>
      <div id="pvactions-{case_id}" style="display:none;align-items:center;gap-6px">
        <button id="pvhexbtn-{case_id}" onclick="pvToggleHex_{case_id}()"
                style="display:none;font-size:.7rem;background:#31324488;border:1px solid #45475a55;
                       color:#cdd6f4;border-radius:4px;padding:2px 8px;cursor:pointer">
          <i class="fa fa-table-cells me-1"></i>Hex
        </button>
        <button onclick="pvSearch_{case_id}()"
                style="font-size:.7rem;background:#31324488;border:1px solid #45475a55;
                       color:#cdd6f4;border-radius:4px;padding:2px 8px;cursor:pointer;margin-left:4px">
          <i class="fa fa-magnifying-glass me-1"></i>Search
        </button>
        <a id="pvdllink-{case_id}" href="#" target="_blank"
           style="font-size:.7rem;background:#31324488;border:1px solid #45475a55;
                  color:#89b4fa;border-radius:4px;padding:2px 8px;text-decoration:none;margin-left:4px">
          <i class="fa fa-up-right-from-square me-1"></i>Open
        </a>
      </div>
    </div>

    <!-- search bar (hidden by default) -->
    <div id="pvsearchbar-{case_id}"
         style="display:none;align-items:center;gap:6px;padding:5px 12px;
                background:#181825;border-bottom:1px solid #31324488;flex-shrink:0">
      <input id="pvsq-{case_id}" type="text" placeholder="Search string or hex (prefix 0x)…"
             style="flex:1;background:#313244;border:1px solid #45475a;color:#cdd6f4;
                    border-radius:4px;padding:3px 8px;font-size:.78rem;font-family:monospace"
             onkeydown="if(event.key==='Enter')pvDoSearch_{case_id}()">
      <button onclick="pvDoSearch_{case_id}()"
              style="font-size:.72rem;background:#89b4fa22;border:1px solid #89b4fa44;
                     color:#89b4fa;border-radius:4px;padding:3px 10px;cursor:pointer">Find</button>
      <button onclick="document.getElementById('pvsearchbar-{case_id}').style.display='none';
                       document.getElementById('pvsresults-{case_id}').style.display='none'"
              style="background:none;border:none;color:#6c7086;cursor:pointer;font-size:.8rem">✕</button>
    </div>

    <!-- search results -->
    <div id="pvsresults-{case_id}"
         style="display:none;max-height:130px;overflow-y:auto;font-size:.72rem;
                font-family:monospace;padding:4px 12px;background:#181825;
                border-bottom:1px solid #31324488;flex-shrink:0"></div>

    <!-- preview frame -->
    <div id="pvwrap-{case_id}" style="flex:1;overflow:hidden;background:#1e1e2e">
      <div id="pvempty-{case_id}" class="d-flex align-items-center justify-content-center h-100"
           style="color:#45475a;font-size:.85rem">
        <span><i class="fa fa-eye me-2"></i>Select a file to preview</span>
      </div>
      <iframe id="pvframe-{case_id}" style="display:none;width:100%;height:100%;border:none"
              sandbox="allow-same-origin allow-scripts allow-forms"></iframe>
    </div>
  </div>
</div>

<script>
(function(){{
  const CID     = {case_id};
  let curEvId   = null;
  let curKind   = null;
  let hexMode   = false;

  window[`pvLoad_${{CID}}`] = function(evId, name, kind) {{
    curEvId = evId;
    curKind = kind;
    hexMode = false;

    document.getElementById(`pvtitle-${{CID}}`).textContent = name;
    document.getElementById(`pvactions-${{CID}}`).style.display = 'flex';
    document.getElementById(`pvdllink-${{CID}}`).href =
      `/cases/${{CID}}/evidence/${{evId}}/preview`;

    const hexBtn = document.getElementById(`pvhexbtn-${{CID}}`);
    hexBtn.style.display = (kind === 'binary' || kind === 'text') ? '' : 'none';
    hexBtn.textContent   = kind === 'binary' ? '⬡ Hex' : '⬡ Hex View';

    _loadFrame(`/cases/${{CID}}/evidence/${{evId}}/preview`);
    document.getElementById(`pvsearchbar-${{CID}}`).style.display='none';
    document.getElementById(`pvsresults-${{CID}}`).style.display='none';
  }};

  window[`pvToggleHex_${{CID}}`] = function() {{
    if (!curEvId) return;
    hexMode = !hexMode;
    const hexBtn = document.getElementById(`pvhexbtn-${{CID}}`);
    hexBtn.style.background = hexMode ? '#89b4fa33' : '#31324488';
    const url = hexMode
      ? `/cases/${{CID}}/evidence/${{curEvId}}/preview/hex`
      : `/cases/${{CID}}/evidence/${{curEvId}}/preview`;
    _loadFrame(url);
  }};

  window[`pvSearch_${{CID}}`] = function() {{
    const bar = document.getElementById(`pvsearchbar-${{CID}}`);
    bar.style.display = bar.style.display === 'none' ? 'flex' : 'none';
    if (bar.style.display === 'flex') document.getElementById(`pvsq-${{CID}}`).focus();
  }};

  window[`pvDoSearch_${{CID}}`] = async function() {{
    if (!curEvId) return;
    const q = document.getElementById(`pvsq-${{CID}}`).value.trim();
    if (!q) return;
    const mode = q.startsWith('0x') ? 'hex' : 'ascii';
    const qStr = mode === 'hex' ? q.slice(2) : q;
    const res  = document.getElementById(`pvsresults-${{CID}}`);
    res.style.display = 'block';
    res.innerHTML = '<span style="color:#6c7086">Searching…</span>';
    try {{
      const r = await fetch(`/cases/${{CID}}/evidence/${{curEvId}}/preview/search?q=${{encodeURIComponent(qStr)}}&mode=${{mode}}`);
      const d = await r.json();
      if (d.error) {{ res.innerHTML = `<span style="color:#f38ba8">${{d.error}}</span>`; return; }}
      if (!d.count) {{ res.innerHTML = '<span style="color:#6c7086">No matches found.</span>'; return; }}
      res.innerHTML = `<span style="color:#a6e3a1;margin-right:12px">${{d.count}} hit(s)</span>` +
        d.hits.map(h => `
          <span onclick="pvGoOffset_${{CID}}(${{h.page}})"
                style="cursor:pointer;color:#89b4fa;margin-right:16px"
                title="Click to jump to this page in hex view">
            <code style="color:#cba6f7">${{h.offset_hex}}</code>
            <code style="color:#6c7086">&nbsp;${{h.context}}</code>
          </span>`).join('');
    }} catch(e) {{ res.innerHTML = '<span style="color:#f38ba8">Search failed.</span>'; }}
  }};

  window[`pvGoOffset_${{CID}}`] = function(page) {{
    if (!curEvId) return;
    hexMode = true;
    document.getElementById(`pvhexbtn-${{CID}}`).style.background = '#89b4fa33';
    _loadFrame(`/cases/${{CID}}/evidence/${{curEvId}}/preview/hex?offset=${{page}}`);
  }};

  function _loadFrame(url) {{
    const empty = document.getElementById(`pvempty-${{CID}}`);
    const frame = document.getElementById(`pvframe-${{CID}}`);
    empty.style.display = 'none';
    frame.style.display = 'block';
    frame.src           = url;
  }}
}})();
</script>
"""
