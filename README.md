# ForensiQ

Digital forensics case management system built for Indonesian law enforcement and security teams.

![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

### Case Management
- Create and track cases with case number, priority, classification, and case type
- Multi-investigator assignment with lead designation and time tracking
- Case notes with Markdown editor (live preview, formatting toolbar)
- Status workflow: Open → Under Review → Closed
- Full audit trail for every action

### Evidence Handling
- Upload files with automatic MD5 + SHA256 hashing
- Chain of custody (CoC) numbering
- Evidence verification and per-evidence notes
- Category tagging (Disk Image, Memory Dump, Network Capture, Log File, etc.)

### Plugin Tabs
Seven analysis plugins accessible from the case detail page:

| # | Plugin | Description |
|---|--------|-------------|
| 1 | **OSINT Lookup** | IP/domain/hash lookup via ipinfo.io, whois, MalwareBazaar |
| 2 | **Hash Check** | Batch MalwareBazaar check for all evidence hashes |
| 3 | **Timeline** | Chronological view of all case events with date separators |
| 4 | **IOC Extractor** | Regex extraction of IPs, hashes, emails, URLs, CVEs from notes |
| 5 | **Email Header Analyzer** | Parse raw email headers — SPF/DKIM/DMARC badges, routing hops |
| 6 | **Geo IP Map** | Leaflet.js interactive map of IPs found in case notes |
| 7 | **File Metadata** | exiftool-based metadata extraction, highlights GPS/author fields |

### Pipeline Engine
Automated analysis pipelines that run on evidence upload or manual trigger:

| Pipeline | Modules | Auto-run |
|----------|---------|----------|
| Hash Intel | hash_intel | On upload |
| Full Analysis | ioc_extract → metadata → risk_score → flowintel_push | Manual |
| Flowintel Sync | risk_score → flowintel_push | Manual |

Risk scoring: 0–100 across four levels (LOW / MEDIUM / HIGH / CRITICAL).

### Report Export
- **HTML + PDF** — WeasyPrint-rendered A4 report with cover page, section numbering, and page counters
- **Obsidian Export** — `.md` file with YAML frontmatter, callouts (`> [!info]`), and `[[wikilinks]]`

### Integrations
- **Flowintel** — auto-create linked case, push IOC observables, sync risk score
- **MISP** — event linking via pymisp

---

## Stack

| Layer | Library |
|-------|---------|
| Web framework | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 + Alembic |
| Templates | Jinja2 3.1 |
| PDF | WeasyPrint 62.3 |
| HTTP client | httpx 0.27 |
| File magic | python-magic |
| Frontend | Bootstrap 5, Font Awesome 6, Leaflet.js, marked.js |

---

## Requirements

- Python 3.11+
- `exiftool` (for File Metadata plugin) — `apt install libimage-exiftool-perl`
- `whois` (for domain lookup) — `apt install whois`
- WeasyPrint system deps — `apt install libpango-1.0-0 libpangoft2-1.0-0`

---

## Installation

```bash
git clone https://github.com/pakde-semar/forensiq.git
cd forensiq

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy and edit integration config
cp app/integrations/config.py.example app/integrations/config.py

uvicorn app.main:app --host 0.0.0.0 --port 7080
```

Open `http://localhost:7080`.

### Systemd service

```ini
[Unit]
Description=ForensiQ
After=network.target

[Service]
User=bagong
WorkingDirectory=/home/bagong/forensiq
ExecStart=/home/bagong/forensiq/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 7080
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## Configuration

Integration settings live in `app/integrations/config.py`:

```python
FLOWINTEL_BASE_URL = "http://127.0.0.1:7006"
FLOWINTEL_API_KEY  = ""          # set via env or config
MISP_BASE_URL      = "https://your-misp-instance"
MISP_API_KEY       = ""
```

---

## Project Structure

```
forensiq/
├── app/
│   ├── core/           # audit, chain-of-custody, hashing, pipeline engine
│   ├── integrations/   # Flowintel + MISP clients
│   ├── pipelines/      # _1_hash_intel.py … _5_flowintel_push.py
│   ├── plugins/        # _1_osint.py … _7_filemetadata.py
│   ├── routers/        # FastAPI routers (cases, evidence, reports, pipeline, lookup)
│   ├── templates/      # Jinja2 HTML + Obsidian .md templates
│   ├── static/
│   ├── models.py
│   ├── database.py
│   └── main.py
├── alembic/            # DB migrations
├── requirements.txt
└── uploads/            # Evidence files (gitignored)
```

### Adding a plugin

Create `app/plugins/_N_yourplugin.py`:

```python
TAB_LABEL = "My Plugin"
TAB_ICON  = "fa-magnifying-glass"

def render_tab(case) -> str:
    return "<p>Hello from my plugin</p>"
```

The plugin is auto-discovered on next request — no registration needed.

### Adding a pipeline module

Create `app/pipelines/_N_mymodule.py`:

```python
def run(case, context: dict, db) -> dict:
    return {
        "label":    "My Module",
        "status":   "done",
        "ms":       0,
        "findings": [],
        "notes":    "",
    }
```

---

## License

MIT
