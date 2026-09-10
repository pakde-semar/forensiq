"""
Investigator time tracking — clock-in/out, manual entries, summary, CSV export.
"""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..core import audit
from ..templates_env import templates

router = APIRouter(prefix="/cases/{case_id}", tags=["timeclock"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_minutes(minutes: int | None) -> str:
    if not minutes:
        return "0h 0m"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m"


def _open_entry(inv_id: int, db: Session) -> models.TimeEntry | None:
    return (
        db.query(models.TimeEntry)
        .filter_by(investigator_id=inv_id, clock_out=None, entry_type="clockinout")
        .order_by(models.TimeEntry.clock_in.desc())
        .first()
    )


def _rebuild_total(inv: models.Investigator, db: Session) -> None:
    entries = (
        db.query(models.TimeEntry)
        .filter_by(investigator_id=inv.id)
        .filter(models.TimeEntry.duration_minutes.isnot(None))
        .all()
    )
    inv.timeclock_minutes = sum(e.duration_minutes for e in entries if e.duration_minutes)
    db.commit()


# ── Clock-in ──────────────────────────────────────────────────────────────────

@router.post("/investigators/{inv_id}/clockin")
def clockin(
    case_id:  int,
    inv_id:   int,
    activity: str = Form(""),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Investigator).filter_by(id=inv_id, case_id=case_id).first()
    if not inv:
        return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)

    if not _open_entry(inv_id, db):
        db.add(models.TimeEntry(
            investigator_id=inv_id,
            case_id=case_id,
            clock_in=datetime.utcnow(),
            activity=activity,
        ))
        db.commit()
        audit.log(db, case_id, f"CLOCK IN: {inv.name}", app_name="TimeClock")

    return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)


# ── Clock-out ─────────────────────────────────────────────────────────────────

@router.post("/investigators/{inv_id}/clockout")
def clockout(
    case_id:  int,
    inv_id:   int,
    activity: str = Form(""),
    db: Session = Depends(get_db),
):
    inv   = db.query(models.Investigator).filter_by(id=inv_id, case_id=case_id).first()
    entry = _open_entry(inv_id, db)
    if inv and entry:
        now = datetime.utcnow()
        entry.clock_out        = now
        entry.duration_minutes = max(1, int((now - entry.clock_in).total_seconds() / 60))
        if activity:
            entry.activity = activity
        _rebuild_total(inv, db)
        audit.log(db, case_id,
                  f"CLOCK OUT: {inv.name} — {_fmt_minutes(entry.duration_minutes)}",
                  app_name="TimeClock")

    return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)


# ── Manual entry ──────────────────────────────────────────────────────────────

@router.post("/time/manual")
def time_manual(
    case_id:  int,
    inv_id:   int   = Form(...),
    date_in:  str   = Form(...),   # YYYY-MM-DD
    time_in:  str   = Form(...),   # HH:MM
    date_out: str   = Form(...),
    time_out: str   = Form(...),
    activity: str   = Form(""),
    db: Session = Depends(get_db),
):
    inv = db.query(models.Investigator).filter_by(id=inv_id, case_id=case_id).first()
    if not inv:
        return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)

    try:
        cin  = datetime.fromisoformat(f"{date_in}T{time_in}")
        cout = datetime.fromisoformat(f"{date_out}T{time_out}")
        dur  = max(1, int((cout - cin).total_seconds() / 60))
    except ValueError:
        return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)

    db.add(models.TimeEntry(
        investigator_id=inv_id,
        case_id=case_id,
        clock_in=cin,
        clock_out=cout,
        duration_minutes=dur,
        activity=activity,
        entry_type="manual",
    ))
    _rebuild_total(inv, db)
    audit.log(db, case_id,
              f"TIME MANUAL: {inv.name} — {_fmt_minutes(dur)} ({activity or 'no note'})",
              app_name="TimeClock")

    return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)


# ── Delete entry ──────────────────────────────────────────────────────────────

@router.post("/time/entries/{entry_id}/delete")
def time_entry_delete(
    case_id:  int,
    entry_id: int,
    db: Session = Depends(get_db),
):
    entry = db.query(models.TimeEntry).filter_by(id=entry_id, case_id=case_id).first()
    if entry:
        inv = db.query(models.Investigator).filter_by(id=entry.investigator_id).first()
        db.delete(entry)
        db.commit()
        if inv:
            _rebuild_total(inv, db)
    return RedirectResponse(f"/cases/{case_id}#tab-timeclock", status_code=303)


# ── JSON summary ──────────────────────────────────────────────────────────────

@router.get("/time/summary")
def time_summary(case_id: int, db: Session = Depends(get_db)):
    investigators = db.query(models.Investigator).filter_by(case_id=case_id).all()
    result = []
    for inv in investigators:
        open_e = _open_entry(inv.id, db)
        result.append({
            "id":           inv.id,
            "name":         inv.name,
            "is_lead":      bool(inv.is_lead),
            "total_minutes": inv.timeclock_minutes or 0,
            "total_fmt":    _fmt_minutes(inv.timeclock_minutes),
            "clocked_in":   bool(open_e),
            "clock_in_since": open_e.clock_in.isoformat() if open_e else None,
        })
    case_total = sum(r["total_minutes"] for r in result)
    return JSONResponse({"investigators": result, "case_total_fmt": _fmt_minutes(case_total)})


# ── CSV export ────────────────────────────────────────────────────────────────

@router.get("/time/export.csv")
def time_export_csv(case_id: int, db: Session = Depends(get_db)):
    case    = db.query(models.Case).filter_by(id=case_id).first()
    entries = (
        db.query(models.TimeEntry)
        .filter_by(case_id=case_id)
        .order_by(models.TimeEntry.clock_in.asc())
        .all()
    )
    inv_map = {
        inv.id: inv.name
        for inv in db.query(models.Investigator).filter_by(case_id=case_id).all()
    }

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["case_number", "investigator", "clock_in", "clock_out",
                "duration_minutes", "duration_fmt", "activity", "entry_type"])
    for e in entries:
        w.writerow([
            case.case_number if case else "",
            inv_map.get(e.investigator_id, ""),
            e.clock_in.strftime("%Y-%m-%d %H:%M") if e.clock_in else "",
            e.clock_out.strftime("%Y-%m-%d %H:%M") if e.clock_out else "OPEN",
            e.duration_minutes or "",
            _fmt_minutes(e.duration_minutes),
            e.activity or "",
            e.entry_type or "",
        ])

    fn = f"timelog_{case.case_number}_{datetime.utcnow().strftime('%Y%m%d')}.csv" if case else "timelog.csv"
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
