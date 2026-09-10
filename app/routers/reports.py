import json
import logging
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..core import audit
from ..routers.agency import get_or_create_agency

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/reports", tags=["reports"])
templates = Jinja2Templates(directory="app/templates")

REPORTS_ROOT = Path("reports")


def _render_html(case_id: int, db: Session) -> tuple[str, "models.Case", "models.Agency"]:
    """Render the report HTML string. Returns (html, case, agency)."""
    case   = db.query(models.Case).filter_by(id=case_id).first()
    agency = get_or_create_agency(db)
    html   = templates.get_template("reports/case_report.html").render({
        "case":         case,
        "agency":       agency,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "created_by":   "",
    })
    return html, case, agency


def _html_to_pdf(html: str, base_url: str) -> bytes:
    """Convert HTML string to PDF bytes via WeasyPrint."""
    from weasyprint import HTML as WP_HTML
    return WP_HTML(string=html, base_url=base_url).write_pdf()


@router.post("/generate")
def generate_report(
    case_id:    int,
    title:      str = Form("Case Report"),
    created_by: str = Form(""),
    db: Session = Depends(get_db),
):
    case   = db.query(models.Case).filter_by(id=case_id).first()
    agency = get_or_create_agency(db)
    if not case:
        return RedirectResponse("/cases/", status_code=303)

    ts      = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = REPORTS_ROOT / str(case_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_fname = f"report_{case.case_number}_{ts}.html"
    pdf_fname  = f"report_{case.case_number}_{ts}.pdf"
    html_path  = out_dir / html_fname
    pdf_path   = out_dir / pdf_fname

    # Render template
    html = templates.get_template("reports/case_report.html").render({
        "case":         case,
        "agency":       agency,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "created_by":   created_by,
    })
    html_path.write_text(html, encoding="utf-8")

    # Generate PDF
    pdf_ok = False
    try:
        pdf_bytes = _html_to_pdf(html, base_url=str(html_path.resolve().parent) + "/")
        pdf_path.write_bytes(pdf_bytes)
        pdf_ok = True
    except Exception as e:
        log.warning("PDF generation failed: %s", e)

    report = models.Report(
        case_id    = case_id,
        title      = title or f"Case Report — {case.case_number}",
        file_path  = str(html_path),
        format     = "html+pdf" if pdf_ok else "html",
        created_by = created_by,
    )
    db.add(report)
    db.commit()

    suffix = " (HTML + PDF)" if pdf_ok else " (HTML only)"
    audit.log(db, case_id, f"Report generated: {html_fname}{suffix}",
              investigator=created_by)

    return RedirectResponse(f"/cases/{case_id}#tab-reports", status_code=303)


@router.get("/{report_id}/download")
def download_html(case_id: int, report_id: int, db: Session = Depends(get_db)):
    report = db.query(models.Report).filter_by(id=report_id, case_id=case_id).first()
    if not report or not Path(report.file_path).exists():
        return RedirectResponse(f"/cases/{case_id}", status_code=303)
    return FileResponse(
        report.file_path,
        filename=Path(report.file_path).name,
        media_type="text/html",
    )


@router.get("/{report_id}/download-pdf")
def download_pdf(case_id: int, report_id: int, db: Session = Depends(get_db)):
    report = db.query(models.Report).filter_by(id=report_id, case_id=case_id).first()
    if not report:
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    pdf_path = Path(report.file_path).with_suffix(".pdf")

    # PDF exists from generation
    if pdf_path.exists():
        return FileResponse(
            pdf_path,
            filename=pdf_path.name,
            media_type="application/pdf",
        )

    # Generate on-demand from stored HTML
    html_path = Path(report.file_path)
    if not html_path.exists():
        return RedirectResponse(f"/cases/{case_id}", status_code=303)
    try:
        html      = html_path.read_text(encoding="utf-8")
        pdf_bytes = _html_to_pdf(html, base_url=str(html_path.resolve().parent) + "/")
        pdf_path.write_bytes(pdf_bytes)
        return FileResponse(
            pdf_path,
            filename=pdf_path.name,
            media_type="application/pdf",
        )
    except Exception as e:
        log.error("On-demand PDF failed: %s", e)
        return RedirectResponse(f"/cases/{case_id}", status_code=303)


@router.post("/generate-obsidian")
def generate_obsidian(
    case_id:    int,
    created_by: str = Form(""),
    db: Session = Depends(get_db),
):
    """Generate an Obsidian-ready Markdown note and save as a Report record."""
    from .. import models as _models

    case   = db.query(models.Case).filter_by(id=case_id).first()
    agency = get_or_create_agency(db)
    if not case:
        return RedirectResponse("/cases/", status_code=303)

    # Build pipeline run steps for template
    pipeline_runs = []
    for run in case.pipeline_runs[:5]:
        steps = json.loads(run.steps_json or "[]")
        pipeline_runs.append({
            "pipeline_label": run.pipeline_label,
            "started_at":     run.started_at,
            "risk_score":     run.risk_score,
            "steps":          steps,
        })

    evidence_notes = any(ev.notes for ev in case.evidence)

    md = templates.get_template("reports/obsidian_case.md").render({
        "case":          case,
        "agency":        agency,
        "generated_at":  datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "created_by":    created_by,
        "pipeline_runs": pipeline_runs,
        "evidence_notes": evidence_notes,
    })

    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    fname    = f"{case.case_number}_{ts}.md"
    out_dir  = REPORTS_ROOT / str(case_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / fname
    out_path.write_text(md, encoding="utf-8")

    report = models.Report(
        case_id    = case_id,
        title      = f"Obsidian Note — {case.case_number}",
        file_path  = str(out_path),
        format     = "obsidian",
        created_by = created_by,
    )
    db.add(report)
    db.commit()
    audit.log(db, case_id, f"Obsidian note generated: {fname}", investigator=created_by)

    return RedirectResponse(f"/cases/{case_id}#tab-reports", status_code=303)


@router.get("/{report_id}/download-md")
def download_md(case_id: int, report_id: int, db: Session = Depends(get_db)):
    """Download Obsidian .md note."""
    report = db.query(models.Report).filter_by(id=report_id, case_id=case_id).first()
    if not report or not Path(report.file_path).exists():
        return RedirectResponse(f"/cases/{case_id}", status_code=303)
    content = Path(report.file_path).read_bytes()
    fname   = Path(report.file_path).name
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/generate-notes-md")
def generate_notes_md(
    case_id: int,
    db: Session = Depends(get_db),
):
    """Auto-generate Markdown notes template from case data and save to case notes."""
    case   = db.query(models.Case).filter_by(id=case_id).first()
    agency = get_or_create_agency(db)
    if not case:
        return RedirectResponse("/cases/", status_code=303)

    lines = [
        f"# {case.case_number} — {case.name}",
        "",
        "## Summary",
        f"- **Status:** {case.status}",
        f"- **Priority:** {case.priority}",
        f"- **Classification:** {case.classification}",
        f"- **Opened:** {case.created_at.strftime('%Y-%m-%d')}",
        f"- **Agency:** {agency.name}",
        "",
    ]

    if case.investigators:
        lines += ["## Investigators", ""]
        for inv in case.investigators:
            role = "Lead Investigator" if inv.is_lead else "Investigator"
            lines.append(f"- **{inv.name}** — {role}" + (f" <{inv.email}>" if inv.email else ""))
        lines += [""]

    if case.evidence:
        lines += ["## Evidence", ""]
        for ev in case.evidence:
            lines.append(f"- `{ev.evidence_number}` — **{ev.file_name}** ({ev.category})")
            if ev.md5:
                lines.append(f"  - MD5: `{ev.md5}`")
            if ev.sha256:
                lines.append(f"  - SHA256: `{ev.sha256}`")
        lines += [""]

    lines += [
        "## Findings",
        "",
        "<!-- Describe key findings here -->",
        "",
        "## Timeline",
        "",
        "<!-- Key events and timestamps -->",
        "",
        "## Conclusions",
        "",
        "<!-- Summary of conclusions -->",
        "",
        "## Recommendations",
        "",
        "<!-- Next steps or recommendations -->",
    ]

    template = "\n".join(lines)
    existing = (case.notes or "").strip()
    if existing:
        case.notes = existing + "\n\n---\n\n" + template
    else:
        case.notes = template
    db.commit()
    audit.log(db, case_id, "Notes template generated from case data")
    return RedirectResponse(f"/cases/{case_id}#tab-overview", status_code=303)
