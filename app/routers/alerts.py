"""Notification & Alert Rules endpoints."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from .. import models
from ..templates_env import templates
from ..core import audit

router = APIRouter(tags=["alerts"])

_DEFAULT_RULES = [
    {
        "rule_type": "enrichment_malicious",
        "name":      "Malicious IOC Detected",
        "config":    {"min_provider_count": 1},
    },
    {
        "rule_type": "yara_match",
        "name":      "YARA Rule Matched",
        "config":    {},
    },
    {
        "rule_type": "hash_tampered",
        "name":      "Evidence Hash Tampered",
        "config":    {},
    },
    {
        "rule_type": "evidence_added",
        "name":      "New Evidence Added",
        "config":    {},
    },
    {
        "rule_type": "case_idle",
        "name":      "Case Idle > N Days",
        "config":    {"days": 7},
    },
]


# ── Bootstrap default rules (called from main startup) ────────────────────────

def ensure_default_rules(db: Session):
    for rule in _DEFAULT_RULES:
        existing = db.query(models.AlertRule).filter_by(rule_type=rule["rule_type"]).first()
        if not existing:
            db.add(models.AlertRule(
                name        = rule["name"],
                rule_type   = rule["rule_type"],
                enabled     = 1,
                config_json = json.dumps(rule["config"]),
            ))
    db.commit()


# ── Helper: create notification if rule enabled ────────────────────────────────

def maybe_notify(
    db,
    rule_type:  str,
    title:      str,
    body:       str = "",
    severity:   str = "info",
    link:       str = "",
    case_id:    int | None = None,
):
    rule = db.query(models.AlertRule).filter_by(rule_type=rule_type, enabled=1).first()
    if not rule:
        return
    n = models.Notification(
        rule_type = rule_type,
        severity  = severity,
        title     = title,
        body      = body,
        link      = link,
        case_id   = case_id,
    )
    db.add(n)
    db.commit()


# ── Bell icon unread count (JSON) ─────────────────────────────────────────────

@router.get("/api/notifications/unread")
def unread_count(db: Session = Depends(get_db)):
    count = db.query(models.Notification).filter_by(is_read=0).count()
    return {"count": count}


@router.get("/api/notifications/recent")
def recent_notifications(db: Session = Depends(get_db)):
    items = (
        db.query(models.Notification)
        .order_by(models.Notification.created_at.desc())
        .limit(20)
        .all()
    )
    return [_notif_dict(n) for n in items]


# ── Mark read ─────────────────────────────────────────────────────────────────

@router.post("/api/notifications/{notif_id}/read")
def mark_read(notif_id: int, db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter_by(id=notif_id).first()
    if n:
        n.is_read = 1
        db.commit()
    return {"ok": True}


@router.post("/api/notifications/read_all")
def mark_all_read(db: Session = Depends(get_db)):
    db.query(models.Notification).filter_by(is_read=0).update({"is_read": 1})
    db.commit()
    return {"ok": True}


@router.post("/api/notifications/{notif_id}/delete")
def delete_notification(notif_id: int, db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter_by(id=notif_id).first()
    if n:
        db.delete(n)
        db.commit()
    return {"ok": True}


# ── Alert rules management page ───────────────────────────────────────────────

@router.get("/settings/alerts")
def alerts_page(request: Request, db: Session = Depends(get_db)):
    rules = db.query(models.AlertRule).order_by(models.AlertRule.id).all()
    notifs = (
        db.query(models.Notification)
        .order_by(models.Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(request, "alerts/index.html", {
        "rules":  rules,
        "notifs": notifs,
    })


@router.post("/settings/alerts/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(models.AlertRule).filter_by(id=rule_id).first()
    if rule:
        rule.enabled = 0 if rule.enabled else 1
        db.commit()
    return RedirectResponse("/settings/alerts", status_code=303)


@router.post("/settings/alerts/{rule_id}/config")
async def update_rule_config(rule_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    rule = db.query(models.AlertRule).filter_by(id=rule_id).first()
    if rule:
        try:
            cfg = json.loads(form.get("config_json", "{}"))
        except json.JSONDecodeError:
            cfg = {}
        rule.config_json = json.dumps(cfg)
        db.commit()
    return RedirectResponse("/settings/alerts", status_code=303)


# ── Case-idle scan (manual trigger) ──────────────────────────────────────────

@router.post("/settings/alerts/scan_idle")
def scan_idle(db: Session = Depends(get_db)):
    rule = db.query(models.AlertRule).filter_by(rule_type="case_idle", enabled=1).first()
    if not rule:
        return {"fired": 0}
    cfg  = json.loads(rule.config_json or "{}")
    days = int(cfg.get("days", 7))
    cutoff = datetime.utcnow()
    from datetime import timedelta
    cutoff -= timedelta(days=days)

    fired = 0
    cases = db.query(models.Case).filter(
        models.Case.status.notin_(["Closed", "Archived"]),
        models.Case.updated_at < cutoff,
    ).all()
    for case in cases:
        existing = db.query(models.Notification).filter_by(
            rule_type="case_idle", case_id=case.id
        ).order_by(models.Notification.created_at.desc()).first()
        if existing and existing.is_read == 0:
            continue
        maybe_notify(
            db,
            rule_type="case_idle",
            title=f"Case {case.case_number} idle > {days} days",
            body=f"{case.name} — last update {case.updated_at.strftime('%Y-%m-%d')}",
            severity="warning",
            link=f"/cases/{case.id}",
            case_id=case.id,
        )
        fired += 1
    return {"fired": fired}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _notif_dict(n: models.Notification) -> dict:
    return {
        "id":         n.id,
        "rule_type":  n.rule_type,
        "severity":   n.severity,
        "title":      n.title,
        "body":       n.body,
        "link":       n.link,
        "is_read":    n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "case_id":    n.case_id,
    }
