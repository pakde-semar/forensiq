"""
Generic lookup API — used by OSINT, Hash Check, Email Header, and File Metadata plugins.
"""
import re
import asyncio
import shutil
import socket
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter(prefix="/api", tags=["lookup"])

TIMEOUT = httpx.Timeout(15.0)


@router.get("/lookup")
async def lookup(type: str, q: str):
    q = q.strip()
    if not q:
        return JSONResponse({"error": "Empty query"}, status_code=400)
    if type == "ip":
        return await _lookup_ip(q)
    if type == "domain":
        return await _lookup_domain(q)
    if type == "hash":
        return await _lookup_hash(q)
    return JSONResponse({"error": f"Unknown lookup type: {type}"}, status_code=400)


async def _lookup_ip(ip: str) -> JSONResponse:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f"https://ipinfo.io/{ip}/json")
            d = r.json()
        if "bogon" in d:
            return JSONResponse({
                "IP": d.get("ip", ip),
                "Type": "Bogon / Private / Reserved",
            })
        return JSONResponse({
            "IP":           d.get("ip", ip),
            "Hostname":     d.get("hostname", "–"),
            "City":         d.get("city", "–"),
            "Region":       d.get("region", "–"),
            "Country":      d.get("country", "–"),
            "Organization": d.get("org", "–"),
            "Postal":       d.get("postal", "–"),
            "Timezone":     d.get("timezone", "–"),
            "Source":       "ipinfo.io",
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


async def _lookup_domain(domain: str) -> JSONResponse:
    result: dict[str, str] = {}

    # DNS resolution
    try:
        ips = socket.getaddrinfo(domain, None)
        addrs = list({ai[4][0] for ai in ips})
        result["DNS"] = ", ".join(addrs[:6])
    except Exception:
        result["DNS"] = "resolution failed"

    # WHOIS via system binary (preferred — no rate limit)
    if shutil.which("whois"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "whois", domain,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
            text = stdout.decode(errors="replace")
            _WHOIS_FIELDS = {
                "Domain Name", "Registrar", "Registrar URL", "Registrar WHOIS Server",
                "Updated Date", "Creation Date", "Registry Expiry Date",
                "Name Server", "DNSSEC", "Registry Domain ID",
                "Registrant Country", "Admin Country", "Tech Country",
            }
            seen: dict[str, str] = {}
            for line in text.splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    k, v = k.strip(), v.strip()
                    if k in _WHOIS_FIELDS and k not in seen and v:
                        seen[k] = v
            result.update(seen)
            result["Source"] = "whois (system)"
        except Exception as e:
            result["WHOIS error"] = str(e)
    else:
        result["Source"] = "DNS only (whois not available)"

    return JSONResponse(result if result else {"error": "No data found"})


async def _lookup_hash(h: str) -> JSONResponse:
    h = h.strip().lower()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.post(
                "https://mb-api.abuse.ch/api/v1/",
                data={"query": "get_info", "hash": h},
            )
            data = r.json()
        status = data.get("query_status", "")
        if status == "hash_not_found":
            return JSONResponse({"Status": "Clean / Not found", "Hash": h, "Source": "MalwareBazaar"})
        if status == "ok":
            d = data.get("data", [{}])[0]
            return JSONResponse({
                "Status":     "MALWARE DETECTED",
                "Hash":       h,
                "File Name":  d.get("file_name", "–"),
                "File Type":  d.get("file_type", "–"),
                "File Size":  f"{d.get('file_size', '–')} bytes",
                "Signature":  d.get("signature", "–"),
                "Tags":       ", ".join(d.get("tags") or []) or "–",
                "First Seen": d.get("first_seen", "–"),
                "Reporter":   d.get("reporter", "–"),
                "Source":     "MalwareBazaar",
            })
        return JSONResponse({"Status": status or "unknown", "Hash": h})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ─── Email Header Analysis ────────────────────────────────────────────────────

class _EmailHeaderBody(BaseModel):
    headers: str


_IP_RE  = re.compile(r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b')
_TS_RE  = re.compile(r';\s*(.+)$')


def _parse_email_headers(raw: str) -> dict[str, Any]:
    import email as _email
    msg = _email.message_from_string(raw)

    summary = {
        "from":       msg.get("From", ""),
        "to":         msg.get("To", ""),
        "subject":    msg.get("Subject", ""),
        "date":       msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "x_mailer":   msg.get("X-Mailer") or msg.get("User-Agent") or "",
        "reply_to":   msg.get("Reply-To", ""),
    }

    # Auth results
    auth_raw = msg.get("Authentication-Results", "") or msg.get("ARC-Authentication-Results", "")
    auth: dict[str, str] = {}
    for proto in ("spf", "dkim", "dmarc"):
        m = re.search(rf'{proto}=(\S+)', auth_raw, re.IGNORECASE)
        auth[proto] = m.group(1).rstrip(";") if m else ""

    # Routing hops from Received: headers
    received = msg.get_all("Received") or []
    hops: list[dict] = []
    for r in received:
        hop: dict[str, str] = {}
        fm = re.search(r'from\s+(\S+)', r, re.IGNORECASE)
        by = re.search(r'by\s+(\S+)', r, re.IGNORECASE)
        ts = _TS_RE.search(r)
        ip = _IP_RE.search(r)
        if fm:  hop["from"] = fm.group(1)
        if by:  hop["by"]   = by.group(1)
        if ts:  hop["ts"]   = ts.group(1).strip()[:40]
        if ip:  hop["ip"]   = ip.group(0)
        hops.append(hop)
    hops.reverse()  # chronological order (oldest first)

    # Heuristic warnings
    warnings: list[str] = []
    frm = summary["from"]
    rto = summary["reply_to"]
    if rto and frm and rto.lower() != frm.lower():
        warnings.append(f"Reply-To differs from From: <b>{rto}</b>")
    if auth.get("spf") and auth["spf"].lower() not in ("pass",):
        warnings.append(f"SPF not passing: <b>{auth['spf']}</b>")
    if auth.get("dkim") and auth["dkim"].lower() not in ("pass",):
        warnings.append(f"DKIM not passing: <b>{auth['dkim']}</b>")
    if auth.get("dmarc") and auth["dmarc"].lower() not in ("pass",):
        warnings.append(f"DMARC not passing: <b>{auth['dmarc']}</b>")
    if len(hops) > 6:
        warnings.append(f"Unusually long routing chain: {len(hops)} hops")

    # From display name vs email mismatch
    dn_match = re.match(r'^"?([^<"]+)"?\s*<([^>]+)>', frm)
    if dn_match:
        display_domain = dn_match.group(1).strip().lower()
        email_domain   = dn_match.group(2).split("@")[-1].lower() if "@" in dn_match.group(2) else ""
        if display_domain and email_domain and display_domain not in email_domain and email_domain not in display_domain:
            warnings.append(f"Display name domain mismatch: <b>{display_domain}</b> vs <b>{email_domain}</b>")

    return {"summary": summary, "auth": auth, "hops": hops, "warnings": warnings}


@router.post("/email-header")
async def email_header(body: _EmailHeaderBody):
    try:
        result = _parse_email_headers(body.headers)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ─── File Metadata ────────────────────────────────────────────────────────────

@router.get("/evidence/{ev_id}/meta")
async def evidence_meta(ev_id: int, db: Session = Depends(get_db)):
    ev = db.query(models.Evidence).filter_by(id=ev_id).first()
    if not ev:
        return JSONResponse({"error": "Evidence not found"}, status_code=404)

    fpath = Path(ev.file_path) if ev.file_path else None
    if not fpath or not fpath.exists():
        return JSONResponse({"error": "File not found on disk"}, status_code=404)

    # Try exiftool first (most comprehensive)
    if shutil.which("exiftool"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "exiftool", "-json", "-long", str(fpath),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
            import json as _json
            data = _json.loads(stdout.decode(errors="replace"))
            if data:
                # Flatten: drop SourceFile, ExifToolVersion
                result = {
                    k: v for k, v in data[0].items()
                    if k not in ("SourceFile", "ExifToolVersion", "Directory", "FileName",
                                 "FilePermissions", "FileInodeChangeDate")
                }
                result["_tool"] = "exiftool"
                return JSONResponse(result)
        except Exception:
            pass

    # Fallback: Pillow for images
    suffix = fpath.suffix.lower()
    if suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif", ".webp"):
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
            img  = Image.open(fpath)
            meta = {"Format": img.format, "Mode": img.mode, "Size": f"{img.width}x{img.height}"}
            exif = img._getexif() if hasattr(img, "_getexif") else None
            if exif:
                for tag_id, val in exif.items():
                    tag = TAGS.get(tag_id, str(tag_id))
                    meta[tag] = str(val)[:200]
            meta["_tool"] = "Pillow"
            return JSONResponse(meta)
        except Exception as e:
            return JSONResponse({"error": f"Pillow: {e}"})

    # Fallback: basic file info
    stat = fpath.stat()
    return JSONResponse({
        "File Name": fpath.name,
        "File Size": f"{stat.st_size:,} bytes",
        "Suffix":    suffix,
        "Note":      "No metadata tool available for this file type",
    })
