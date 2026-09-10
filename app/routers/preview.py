"""
Evidence file preview — serves inline preview for images, PDF, text, video, audio, and binary.
"""
import html as _html
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter(prefix="/cases/{case_id}/evidence/{ev_id}", tags=["preview"])

# ── File type sets ────────────────────────────────────────────────────────────

_IMAGE = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif'}
_VIDEO = {'.mp4', '.webm', '.mov', '.ogv', '.mkv', '.avi', '.wmv'}
_AUDIO = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.opus'}
_PDF   = {'.pdf'}
_TEXT  = {
    '.txt', '.log', '.csv', '.tsv', '.md', '.rst',
    '.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.conf', '.cfg',
    '.py', '.js', '.ts', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    '.html', '.htm', '.css', '.sql', '.go', '.rs', '.java', '.c', '.cpp', '.h',
    '.rb', '.php', '.r', '.lua', '.pl', '.swift', '.kt', '.scala', '.tf',
}
_LANG_MAP = {
    '.py': 'python',      '.js': 'javascript', '.ts': 'typescript',
    '.sh': 'bash',        '.bash': 'bash',      '.zsh': 'bash',
    '.ps1': 'powershell', '.bat': 'dos',        '.cmd': 'dos',
    '.json': 'json',      '.xml': 'xml',        '.html': 'html', '.htm': 'html',
    '.yaml': 'yaml',      '.yml': 'yaml',       '.toml': 'toml',
    '.css': 'css',        '.sql': 'sql',        '.md': 'markdown',
    '.c': 'c',            '.cpp': 'cpp',        '.h': 'c',
    '.go': 'go',          '.rs': 'rust',        '.java': 'java',
    '.rb': 'ruby',        '.php': 'php',        '.r': 'r',
    '.lua': 'lua',        '.pl': 'perl',        '.kt': 'kotlin',
    '.tf': 'hcl',
}

# ── Hex dump ──────────────────────────────────────────────────────────────────

def _hex_dump(data: bytes, width: int = 16) -> str:
    lines = []
    for i in range(0, len(data), width):
        chunk    = data[i:i + width]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        asc_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{i:08x}  {hex_part:<{width * 3}}  |{asc_part}|')
    return '\n'.join(lines)


# ── Page skeleton ─────────────────────────────────────────────────────────────

_PAGE_HEAD = """<!doctype html>
<html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet"
  href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #1e1e2e; color: #cdd6f4; font-family: system-ui, sans-serif;
       font-size: .87rem; line-height: 1.6; }
pre  { margin: 0; padding: 16px; overflow-x: auto; font-family: monospace;
       font-size: .82rem; line-height: 1.5; white-space: pre; }
code { font-family: monospace; }
.center { display: flex; align-items: center; justify-content: center;
          min-height: 100vh; padding: 20px; }
img  { max-width: 100%; max-height: 90vh; display: block; border-radius: 4px; }
video, audio { width: 100%; max-width: 900px; }
.meta { font-size: .72rem; color: #6c7086; padding: 8px 16px;
        border-bottom: 1px solid #313244; background: #181825; }
.err  { color: #f38ba8; padding: 40px; text-align: center; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-thumb { background: #45475a; border-radius: 3px; }
</style>
</head><body>"""

_PAGE_FOOT = "</body></html>"


def _page(body: str) -> HTMLResponse:
    return HTMLResponse(_PAGE_HEAD + body + _PAGE_FOOT)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/preview", response_class=HTMLResponse)
def evidence_preview(case_id: int, ev_id: int, db: Session = Depends(get_db)):
    ev = db.query(models.Evidence).filter_by(id=ev_id, case_id=case_id).first()
    if not ev:
        return _page('<div class="err">Evidence not found.</div>')

    fp = Path(ev.file_path) if ev.file_path else None
    if not fp or not fp.exists():
        return _page(
            f'<div class="err">'
            f'<p><b>File not on disk.</b></p>'
            f'<p style="margin-top:8px;font-size:.8rem;color:#a6adc8">'
            f'{_html.escape(str(fp or "—"))}</p>'
            f'</div>'
        )

    ext  = fp.suffix.lower()
    size = fp.stat().st_size
    meta = (f'<div class="meta">'
            f'{_html.escape(ev.file_name)} &nbsp;·&nbsp; '
            f'{size / 1024:.1f} KB &nbsp;·&nbsp; '
            f'{ev.evidence_number}'
            f'</div>')

    # ── Image ──────────────────────────────────────────────────────
    if ext in _IMAGE:
        url = '/' + str(fp).replace('\\', '/')
        return _page(
            meta +
            f'<div class="center"><img src="{url}" alt="{_html.escape(ev.file_name)}"></div>'
        )

    # ── Video ──────────────────────────────────────────────────────
    if ext in _VIDEO:
        url  = '/' + str(fp).replace('\\', '/')
        mime = {'mp4': 'video/mp4', 'webm': 'video/webm',
                'ogv': 'video/ogg', 'mov': 'video/quicktime'}.get(ext.lstrip('.'), 'video/mp4')
        return _page(
            meta +
            f'<div class="center"><video controls>'
            f'<source src="{url}" type="{mime}">Your browser does not support video.</video></div>'
        )

    # ── Audio ──────────────────────────────────────────────────────
    if ext in _AUDIO:
        url  = '/' + str(fp).replace('\\', '/')
        mime = {'mp3': 'audio/mpeg', 'wav': 'audio/wav', 'ogg': 'audio/ogg',
                'flac': 'audio/flac', 'm4a': 'audio/mp4', 'aac': 'audio/aac',
                'opus': 'audio/ogg'}.get(ext.lstrip('.'), 'audio/mpeg')
        return _page(
            meta +
            f'<div class="center"><audio controls style="width:90%;max-width:600px">'
            f'<source src="{url}" type="{mime}">Your browser does not support audio.</audio></div>'
        )

    # ── PDF ────────────────────────────────────────────────────────
    if ext in _PDF:
        url = '/' + str(fp).replace('\\', '/')
        return _page(
            meta +
            f'<embed src="{url}" type="application/pdf"'
            f'  style="width:100%;height:calc(100vh - 36px);border:none">'
        )

    # ── Text / code ────────────────────────────────────────────────
    if ext in _TEXT:
        try:
            raw = fp.read_bytes()
            text = raw[:512_000].decode('utf-8', errors='replace')
            if len(raw) > 512_000:
                text += f'\n\n… [truncated — showing 500 KB of {size / 1024:.0f} KB]'
        except Exception as e:
            return _page(f'<div class="err">Cannot read file: {_html.escape(str(e))}</div>')

        lang = _LANG_MAP.get(ext, '')
        cls  = f'language-{lang}' if lang else ''
        escaped = _html.escape(text)
        return _page(
            meta +
            f'<pre><code class="{cls}">{escaped}</code></pre>'
            '<script>document.addEventListener("DOMContentLoaded",()=>hljs.highlightAll());'
            'hljs.highlightAll();</script>'
        )

    # ── Binary hex dump ────────────────────────────────────────────
    try:
        raw   = fp.read_bytes()[:4096]
        dump  = _hex_dump(raw)
        note  = '' if len(raw) < 4096 else f'\n… [showing first 4096 of {size} bytes]'
        return _page(
            meta +
            f'<pre><code class="language-plaintext">{_html.escape(dump + note)}</code></pre>'
            '<script>hljs.highlightAll();</script>'
        )
    except Exception as e:
        return _page(f'<div class="err">Cannot read file: {_html.escape(str(e))}</div>')
