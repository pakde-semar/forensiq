"""Evidence metadata extraction: file type, EXIF, PE headers, strings."""
import json
import re
import struct
import subprocess
from datetime import datetime
from pathlib import Path


def extract(path: str | Path) -> dict:
    """Return a metadata dict for the given file."""
    fp = Path(path)
    if not fp.exists():
        return {"error": "File not found"}

    result: dict = {
        "extracted_at": datetime.utcnow().isoformat(),
        "file_info":    _file_info(fp),
    }

    ext = fp.suffix.lower()

    # EXIF (images)
    if ext in {'.jpg', '.jpeg', '.tiff', '.tif', '.webp', '.png', '.heic', '.heif'}:
        exif = _exif(fp)
        if exif:
            result["exif"] = exif

    # PE (Windows executables)
    if ext in {'.exe', '.dll', '.sys', '.drv', '.ocx', '.scr', '.cpl'}:
        pe = _pe_info(fp)
        if pe:
            result["pe"] = pe

    # Strings
    strings = _extract_strings(fp)
    if strings:
        result["strings"] = strings

    # Video/audio via ffprobe (optional)
    if ext in {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.mp3', '.wav', '.flac', '.m4a'}:
        ff = _ffprobe(fp)
        if ff:
            result["media"] = ff

    return result


# ── File info ──────────────────────────────────────────────────────────────────

def _file_info(fp: Path) -> dict:
    stat = fp.stat()
    info: dict = {
        "size_bytes": stat.st_size,
        "size_human": _human(stat.st_size),
        "extension":  fp.suffix.lower(),
        "name":       fp.name,
    }

    # filetype detection (magic bytes)
    try:
        import filetype as ft
        kind = ft.guess(fp)
        if kind:
            info["mime_type"]   = kind.mime
            info["file_type"]   = kind.extension.upper()
        else:
            info["mime_type"]   = "application/octet-stream"
            info["file_type"]   = fp.suffix.lstrip('.').upper() or "Unknown"
    except Exception:
        info["file_type"] = fp.suffix.lstrip('.').upper() or "Unknown"

    # Magic bytes (first 16 as hex)
    try:
        with fp.open("rb") as f:
            header = f.read(16)
        info["magic_hex"] = header.hex()
        info["magic_str"] = _magic_label(header)
    except Exception:
        pass

    return info


_MAGIC = [
    (b'\x4d\x5a',                   "PE/Windows Executable (MZ)"),
    (b'\x7fELF',                     "ELF Executable (Linux)"),
    (b'\xff\xd8\xff',               "JPEG Image"),
    (b'\x89PNG\r\n\x1a\n',         "PNG Image"),
    (b'GIF87a',                     "GIF Image"),
    (b'GIF89a',                     "GIF Image"),
    (b'%PDF',                        "PDF Document"),
    (b'PK\x03\x04',                 "ZIP Archive"),
    (b'PK\x05\x06',                 "ZIP Archive (empty)"),
    (b'\x1f\x8b',                   "GZIP Archive"),
    (b'BZh',                         "BZIP2 Archive"),
    (b'\xfd7zXZ\x00',               "XZ Archive"),
    (b'Rar!',                        "RAR Archive"),
    (b'\x00\x00\x00\x08mdat',       "MP4/MOV Video"),
    (b'\x00\x00\x00\x18ftypmp42',   "MP4 Video"),
    (b'\x1aE\xdf\xa3',              "WebM/MKV Video"),
    (b'OggS',                        "OGG Audio/Video"),
    (b'ID3',                         "MP3 Audio"),
    (b'RIFF',                        "RIFF (WAV/AVI)"),
    (b'\x00\x01\x00\x00',           "TrueType Font"),
    (b'OTTO',                        "OpenType Font"),
    (b'{',                           "JSON (likely)"),
    (b'<',                           "XML/HTML (likely)"),
    (b'#!',                          "Shell Script"),
    (b'\xce\xfa\xed\xfe',           "Mach-O 32-bit"),
    (b'\xcf\xfa\xed\xfe',           "Mach-O 64-bit"),
    (b'MZ',                          "DOS/PE Executable"),
]

def _magic_label(header: bytes) -> str:
    for sig, label in _MAGIC:
        if header[:len(sig)] == sig:
            return label
    # Try printable ASCII
    printable = bytes(b if 32 <= b < 127 else ord('.') for b in header[:8])
    return f"Unknown (header: {printable.decode()})"


# ── EXIF ───────────────────────────────────────────────────────────────────────

_SKIP_EXIF = {"MakerNote", "UserComment", "PrintImageMatching", "JPEGThumbnail"}

def _exif(fp: Path) -> dict | None:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img  = Image.open(fp)
        info = {"width": img.width, "height": img.height, "mode": img.mode, "format": img.format}

        raw = img._getexif() if hasattr(img, '_getexif') else None
        if not raw:
            return info

        gps_data: dict = {}
        for tag_id, val in raw.items():
            tag = TAGS.get(tag_id, str(tag_id))
            if tag in _SKIP_EXIF:
                continue
            if tag == "GPSInfo" and isinstance(val, dict):
                for gk, gv in val.items():
                    gps_data[GPSTAGS.get(gk, str(gk))] = str(gv)
            else:
                info[tag] = _safe_val(val)

        if gps_data:
            info["GPSInfo"] = gps_data
            coords = _gps_coords(gps_data)
            if coords:
                info["GPS_coords"] = coords

        return info
    except Exception as e:
        return {"error": str(e)[:100]}


def _safe_val(v) -> str:
    if isinstance(v, (bytes, bytearray)):
        try:
            return v.decode('utf-8', errors='replace')[:200]
        except Exception:
            return v.hex()[:80]
    if isinstance(v, tuple):
        return str(v)
    return str(v)[:300]


def _gps_coords(gps: dict) -> str | None:
    try:
        def to_deg(val: str) -> float:
            parts = [float(x) for x in re.findall(r'[\d./]+', val)]
            return parts[0] + parts[1] / 60 + parts[2] / 3600
        lat  = to_deg(str(gps.get("GPSLatitude", "")))
        lon  = to_deg(str(gps.get("GPSLongitude", "")))
        lref = str(gps.get("GPSLatitudeRef", "N"))
        lnrf = str(gps.get("GPSLongitudeRef", "E"))
        if lref == "S": lat = -lat
        if lnrf == "W": lon = -lon
        return f"{lat:.6f}, {lon:.6f}"
    except Exception:
        return None


# ── PE headers ────────────────────────────────────────────────────────────────

def _pe_info(fp: Path) -> dict | None:
    try:
        import pefile
        pe   = pefile.PE(str(fp), fast_load=True)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
            pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT'],
        ])
        info: dict = {}

        # File header
        fh = pe.FILE_HEADER
        info["machine"]    = hex(fh.Machine)
        info["timestamp"]  = datetime.utcfromtimestamp(fh.TimeDateStamp).isoformat() + "Z"
        info["sections"]   = fh.NumberOfSections
        info["is_exe"]     = bool(fh.Characteristics & 0x0002)
        info["is_dll"]     = bool(fh.Characteristics & 0x2000)

        # Optional header
        if hasattr(pe, 'OPTIONAL_HEADER'):
            oh = pe.OPTIONAL_HEADER
            info["subsystem"]    = oh.Subsystem
            info["entry_point"]  = hex(oh.AddressOfEntryPoint)
            info["image_base"]   = hex(oh.ImageBase)

        # Imports
        imports: list[str] = []
        if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
            for entry in pe.DIRECTORY_ENTRY_IMPORT:
                dll = entry.dll.decode(errors='replace') if entry.dll else "?"
                fns = []
                for imp in entry.imports:
                    if imp.name:
                        fns.append(imp.name.decode(errors='replace'))
                imports.append({"dll": dll, "functions": fns[:20]})
        info["imports"] = imports[:30]

        # Exports
        exports: list[str] = []
        if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
            for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                if exp.name:
                    exports.append(exp.name.decode(errors='replace'))
        info["exports"] = exports[:50]

        # Sections
        sections = []
        for sec in pe.sections:
            sections.append({
                "name":             sec.Name.rstrip(b'\x00').decode(errors='replace'),
                "virtual_address":  hex(sec.VirtualAddress),
                "raw_size":         sec.SizeOfRawData,
                "entropy":          round(sec.get_entropy(), 2),
            })
        info["section_list"] = sections

        pe.close()
        return info
    except Exception as e:
        return {"error": str(e)[:100]}


# ── Strings ───────────────────────────────────────────────────────────────────

_INTERESTING = re.compile(
    r'(?:'
    r'https?://[^\x00-\x1f\x7f]{8,}'
    r'|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    r'|(?:[0-9]{1,3}\.){3}[0-9]{1,3}'
    r'|(?:[A-Z][a-z]+){2,}'                        # CamelCase identifiers
    r'|HKEY_[A-Z_]+'                                # Registry keys
    r'|cmd\.exe|powershell|wscript|cscript'         # Shell references
    r'|\\[Ss]ystem32\\'
    r'|CREATE\s+TABLE|SELECT\s+\*\s+FROM'           # SQL
    r'|CVE-\d{4}-\d{4,7}'
    r')'
)

def _extract_strings(fp: Path, min_len: int = 6, max_bytes: int = 2 * 1024 * 1024) -> dict | None:
    try:
        with fp.open("rb") as f:
            data = f.read(max_bytes)

        # ASCII strings
        ascii_pat = re.compile(rb'[\x20-\x7e]{' + str(min_len).encode() + rb',}')
        all_strings = [m.group().decode('ascii', errors='replace') for m in ascii_pat.finditer(data)]

        # Unicode (UTF-16 LE) strings
        unicode_pat = re.compile(rb'(?:[\x20-\x7e]\x00){' + str(min_len).encode() + rb',}')
        all_strings += [
            m.group().decode('utf-16-le', errors='replace')
            for m in unicode_pat.finditer(data)
        ]

        # Filter interesting
        interesting = list({s for s in all_strings if _INTERESTING.search(s)})[:80]

        return {
            "total_ascii":   len(all_strings),
            "interesting":   sorted(interesting)[:60],
            "truncated":     len(data) >= max_bytes,
        }
    except Exception:
        return None


# ── ffprobe (optional) ────────────────────────────────────────────────────────

def _ffprobe(fp: Path) -> dict | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", str(fp)],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return None
        data  = json.loads(out.stdout)
        fmt   = data.get("format", {})
        info  = {
            "duration_s":  float(fmt.get("duration", 0)),
            "bit_rate":    int(fmt.get("bit_rate", 0)),
            "format_name": fmt.get("format_long_name", ""),
            "streams":     [],
        }
        for s in data.get("streams", []):
            stream = {
                "index":     s.get("index"),
                "codec":     s.get("codec_name"),
                "type":      s.get("codec_type"),
            }
            if s.get("width"):
                stream["resolution"] = f"{s['width']}×{s['height']}"
            if s.get("sample_rate"):
                stream["sample_rate"] = s["sample_rate"]
            info["streams"].append(stream)
        return info
    except Exception:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
