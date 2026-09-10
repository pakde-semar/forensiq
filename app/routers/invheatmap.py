"""Investigator workload heatmap — per-investigator stats and calendar view."""
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..templates_env import templates

router = APIRouter(prefix="/investigators", tags=["investigators"])


# ── Helper: aggregate by investigator name ────────────────────────────────────

def _aggregate(db: Session):
    """Return dict name → {total_minutes, cases: [{case_id, case_number, case_name, minutes}]}"""
    rows = (
        db.query(models.Investigator)
        .join(models.Case)
        .order_by(models.Investigator.name)
        .all()
    )
    by_name: dict[str, dict] = {}
    for inv in rows:
        n = inv.name
        if n not in by_name:
            by_name[n] = {"total_minutes": 0, "cases": [], "is_lead_any": False}
        by_name[n]["total_minutes"] += inv.timeclock_minutes or 0
        by_name[n]["cases"].append({
            "case_id":     inv.case_id,
            "case_number": inv.case.case_number,
            "case_name":   inv.case.name,
            "minutes":     inv.timeclock_minutes or 0,
            "is_lead":     bool(inv.is_lead),
        })
        if inv.is_lead:
            by_name[n]["is_lead_any"] = True
    return by_name


# ── List page ─────────────────────────────────────────────────────────────────

@router.get("")
def investigator_list(request: Request, db: Session = Depends(get_db)):
    by_name = _aggregate(db)
    investigators = []
    for name, data in sorted(by_name.items()):
        investigators.append({
            "name":          name,
            "total_minutes": data["total_minutes"],
            "total_hours":   round(data["total_minutes"] / 60, 1),
            "case_count":    len(data["cases"]),
            "is_lead_any":   data["is_lead_any"],
            "slug":          urllib.parse.quote(name, safe=""),
        })
    investigators.sort(key=lambda x: x["total_minutes"], reverse=True)
    return templates.TemplateResponse(request, "investigators/index.html", {
        "investigators": investigators,
    })


# ── Detail page ───────────────────────────────────────────────────────────────

@router.get("/{name}")
def investigator_detail(name: str, request: Request, db: Session = Depends(get_db)):
    decoded = urllib.parse.unquote(name)
    by_name = _aggregate(db)
    if decoded not in by_name:
        return RedirectResponse("/investigators")
    return templates.TemplateResponse(request, "investigators/detail.html", {
        "inv_name": decoded,
        "slug":     urllib.parse.quote(decoded, safe=""),
    })


# ── JSON data endpoint ────────────────────────────────────────────────────────

@router.get("/{name}/data")
def investigator_data(name: str, db: Session = Depends(get_db)):
    decoded = urllib.parse.unquote(name)
    now     = datetime.utcnow()

    # All time entries for this investigator name
    entries = (
        db.query(models.TimeEntry)
        .join(models.Investigator, models.TimeEntry.investigator_id == models.Investigator.id)
        .filter(models.Investigator.name == decoded)
        .all()
    )

    # ── Heatmap: daily minutes for last 91 days ───────────────────
    cutoff       = now - timedelta(days=91)
    daily: dict[str, int] = defaultdict(int)
    for e in entries:
        if e.clock_in and e.clock_in >= cutoff:
            key = e.clock_in.strftime("%Y-%m-%d")
            daily[key] += e.duration_minutes or 0

    heat_max = max(daily.values(), default=1)
    heatmap  = []
    for i in range(90, -1, -1):
        d   = now - timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        m   = daily.get(key, 0)
        heatmap.append({
            "date":    key,
            "label":   d.strftime("%b %d"),
            "minutes": m,
            "hours":   round(m / 60, 1),
            "level":   min(4, int(m / max(heat_max, 1) * 4 + 0.5)),
        })

    # ── By case ───────────────────────────────────────────────────
    by_name = _aggregate(db)
    data    = by_name.get(decoded, {})
    by_case = sorted(data.get("cases", []), key=lambda x: x["minutes"], reverse=True)

    # ── Weekly trend: last 12 weeks ───────────────────────────────
    weekly = []
    for i in range(11, -1, -1):
        week_start = (now - timedelta(weeks=i)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=(now - timedelta(weeks=i)).weekday())
        week_end = week_start + timedelta(days=7)
        mins = sum(
            e.duration_minutes or 0 for e in entries
            if e.clock_in and week_start <= e.clock_in < week_end
        )
        weekly.append({
            "week":    week_start.strftime("%d %b"),
            "minutes": mins,
            "hours":   round(mins / 60, 1),
        })

    # ── Recent entries ────────────────────────────────────────────
    recent = []
    for e in sorted(entries, key=lambda x: x.clock_in or datetime.min, reverse=True)[:20]:
        recent.append({
            "date":     e.clock_in.strftime("%Y-%m-%d %H:%M") if e.clock_in else "—",
            "case":     e.case.case_number if e.case else "—",
            "case_id":  e.case_id,
            "activity": e.activity or "",
            "minutes":  e.duration_minutes or 0,
            "type":     e.entry_type,
        })

    return {
        "name":          decoded,
        "total_minutes": data.get("total_minutes", 0),
        "total_hours":   round(data.get("total_minutes", 0) / 60, 1),
        "case_count":    len(by_case),
        "heatmap":       heatmap,
        "heat_max":      heat_max,
        "by_case":       by_case,
        "weekly":        weekly,
        "recent":        recent,
    }
