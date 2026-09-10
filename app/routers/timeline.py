"""
Case timeline — aggregates all events into a single chronological feed.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter(prefix="/cases/{case_id}/timeline", tags=["timeline"])


def _ts(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


@router.get("/events")
def timeline_events(case_id: int, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return JSONResponse([], status_code=404)

    events: list[dict] = []

    # ── Case created ──────────────────────────────────────────────
    events.append({
        "ts":       _ts(case.created_at),
        "dt":       _fmt(case.created_at),
        "category": "case",
        "icon":     "fa-folder-plus",
        "color":    "#cba6f7",
        "title":    f"Case created: {case.case_number}",
        "detail":   case.name,
        "link":     None,
    })

    # ── Evidence uploads ──────────────────────────────────────────
    for ev in case.evidence:
        events.append({
            "ts":       _ts(ev.date_added),
            "dt":       _fmt(ev.date_added),
            "category": "evidence",
            "icon":     "fa-box-archive",
            "color":    "#89b4fa",
            "title":    f"Evidence added: {ev.file_name}",
            "detail":   f"{ev.evidence_number} · {ev.category} · {ev.submitter or '—'}",
            "link":     None,
        })
        # CoC entries per evidence
        for coc in ev.coc_entries:
            events.append({
                "ts":       _ts(coc.timestamp),
                "dt":       _fmt(coc.timestamp),
                "category": "coc",
                "icon":     "fa-arrow-right-arrow-left",
                "color":    "#fab387",
                "title":    f"CoC {coc.action}: {ev.evidence_number}",
                "detail":   (
                    f"{coc.released_by or '—'} → {coc.received_by or '—'}"
                    + (f" · {coc.purpose}" if coc.purpose else "")
                ),
                "link":     None,
            })

    # ── Audit logs ────────────────────────────────────────────────
    for log in case.audit_logs:
        events.append({
            "ts":       _ts(log.timestamp),
            "dt":       _fmt(log.timestamp),
            "category": "audit",
            "icon":     "fa-clipboard-list",
            "color":    "#a6adc8",
            "title":    log.message[:120],
            "detail":   f"{log.investigator or '—'} · {log.app_name}",
            "link":     None,
        })

    # ── Pipeline runs ─────────────────────────────────────────────
    for run in case.pipeline_runs:
        status_color = {"done": "#a6e3a1", "error": "#f38ba8", "running": "#f9e2af"}
        events.append({
            "ts":       _ts(run.started_at),
            "dt":       _fmt(run.started_at),
            "category": "pipeline",
            "icon":     "fa-diagram-project",
            "color":    status_color.get(run.status, "#a6adc8"),
            "title":    f"Pipeline: {run.pipeline_label}",
            "detail":   (
                f"Status: {run.status}"
                + (f" · Risk: {run.risk_score:.0f}" if run.risk_score else "")
                + (f" · Input: {run.input_ref}" if run.input_ref else "")
            ),
            "link":     None,
        })

    # ── Time entries ──────────────────────────────────────────────
    inv_map = {inv.id: inv.name for inv in case.investigators}
    for te in case.time_entries:
        if te.clock_out:
            dur = te.duration_minutes or 0
            h, m = divmod(dur, 60)
            events.append({
                "ts":       _ts(te.clock_in),
                "dt":       _fmt(te.clock_in),
                "category": "time",
                "icon":     "fa-clock",
                "color":    "#a6e3a1",
                "title":    f"Work session: {inv_map.get(te.investigator_id, '?')}",
                "detail":   (
                    f"{h}h {m}m"
                    + (f" · {te.activity}" if te.activity else "")
                ),
                "link":     None,
            })

    # ── Yara scans ────────────────────────────────────────────────
    for yr in case.yara_scan_results:
        mc = yr.match_count
        events.append({
            "ts":       _ts(yr.scanned_at),
            "dt":       _fmt(yr.scanned_at),
            "category": "yara",
            "icon":     "fa-shield-halved",
            "color":    "#f38ba8" if mc else "#a6e3a1",
            "title":    f"Yara scan: {yr.file_count} file(s) — {mc} match(es)",
            "detail":   f"By: {yr.scanned_by or '—'}",
            "link":     None,
        })

    # ── Hash verify batches ───────────────────────────────────────
    for hb in case.hash_verify_batches:
        events.append({
            "ts":       _ts(hb.run_at),
            "dt":       _fmt(hb.run_at),
            "category": "hashverify",
            "icon":     "fa-shield-check",
            "color":    "#f38ba8" if hb.tampered_count else "#a6e3a1",
            "title":    (
                f"Hash verify: {hb.ok_count} OK"
                + (f", {hb.tampered_count} TAMPERED" if hb.tampered_count else "")
                + (f", {hb.missing_count} MISSING" if hb.missing_count else "")
            ),
            "detail":   f"By: {hb.run_by or '—'} · {hb.total} evidence",
            "link":     None,
        })

    # ── Wiki notes ────────────────────────────────────────────────
    for note in case.notes_wiki:
        events.append({
            "ts":       _ts(note.created_at),
            "dt":       _fmt(note.created_at),
            "category": "notes",
            "icon":     "fa-file-alt",
            "color":    "#f9e2af",
            "title":    f"Note created: {note.title}",
            "detail":   f"{len(note.content or '')} chars",
            "link":     f"/cases/{case_id}/notes/{note.id}",
        })
        if note.updated_at and note.updated_at != note.created_at:
            events.append({
                "ts":       _ts(note.updated_at),
                "dt":       _fmt(note.updated_at),
                "category": "notes",
                "icon":     "fa-pen-to-square",
                "color":    "#f9e2af",
                "title":    f"Note updated: {note.title}",
                "detail":   f"{len(note.content or '')} chars",
                "link":     f"/cases/{case_id}/notes/{note.id}",
            })

    # Sort descending
    events.sort(key=lambda e: e["ts"] or "", reverse=True)
    return JSONResponse(events)
