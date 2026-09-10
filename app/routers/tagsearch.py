"""Case tagging and full-text search across cases, evidence, and wiki notes."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..templates_env import templates

router = APIRouter(tags=["tagsearch"])

# ── Full search page ──────────────────────────────────────────────────────────

@router.get("/search")
def search_page(request: Request, q: str = "", tag: str = "", db: Session = Depends(get_db)):
    results = _do_search(q.strip(), tag.strip(), db) if (q.strip() or tag.strip()) else None
    all_tags = _all_tags(db)
    return templates.TemplateResponse(request, "search.html", {
        "q":        q,
        "tag":      tag,
        "results":  results,
        "all_tags": all_tags,
    })


# ── Search JSON API (used by sidebar quick-search, extended) ──────────────────

@router.get("/search/api")
def search_api(q: str = "", db: Session = Depends(get_db)):
    if len(q.strip()) < 2:
        return {"results": []}
    term  = f"%{q.strip()}%"
    items = []

    # Cases
    cases = (
        db.query(models.Case)
        .filter(or_(
            models.Case.case_number.ilike(term),
            models.Case.name.ilike(term),
            models.Case.notes.ilike(term),
        ))
        .limit(5).all()
    )
    for c in cases:
        tag_names = ", ".join(t.name for t in c.tags) if c.tags else ""
        items.append({
            "type":  "case",
            "label": f"{c.case_number} — {c.name}",
            "sub":   c.status + (f" · {tag_names}" if tag_names else ""),
            "url":   f"/cases/{c.id}",
        })

    # Evidence
    evs = (
        db.query(models.Evidence)
        .filter(or_(
            models.Evidence.file_name.ilike(term),
            models.Evidence.notes.ilike(term),
            models.Evidence.md5.ilike(term),
            models.Evidence.sha256.ilike(term),
        ))
        .limit(4).all()
    )
    for ev in evs:
        items.append({
            "type":  "evidence",
            "label": ev.file_name,
            "sub":   f"{ev.evidence_number} · case #{ev.case_id}",
            "url":   f"/cases/{ev.case_id}#tab-evidence",
        })

    # Wiki notes
    notes = (
        db.query(models.CaseNote)
        .filter(or_(
            models.CaseNote.title.ilike(term),
            models.CaseNote.content.ilike(term),
        ))
        .limit(3).all()
    )
    for n in notes:
        items.append({
            "type":  "wiki",
            "label": n.title,
            "sub":   f"Case #{n.case_id} wiki",
            "url":   f"/cases/{n.case_id}/notes/{n.id}",
        })

    return {"results": items}


# ── Tag management ────────────────────────────────────────────────────────────

_TAG_COLORS = [
    "#89b4fa", "#cba6f7", "#a6e3a1", "#f9e2af",
    "#fab387", "#f38ba8", "#94e2d5", "#74c7ec",
]

@router.post("/cases/{case_id}/tags")
def add_tag(
    case_id: int,
    name:    str = Form(...),
    color:   str = Form(""),
    db: Session = Depends(get_db),
):
    name = name.strip()[:50]
    if not name:
        return RedirectResponse(f"/cases/{case_id}", status_code=303)

    # Deduplicate
    exists = db.query(models.CaseTag).filter_by(case_id=case_id, name=name).first()
    if not exists:
        # Auto-pick color if not provided
        if not color or color == "#89b4fa":
            used = {t.color for t in db.query(models.CaseTag).filter_by(case_id=case_id).all()}
            color = next((c for c in _TAG_COLORS if c not in used), _TAG_COLORS[0])
        db.add(models.CaseTag(case_id=case_id, name=name, color=color))
        db.commit()

    return RedirectResponse(f"/cases/{case_id}", status_code=303)


@router.post("/cases/{case_id}/tags/{tag_id}/delete")
def delete_tag(case_id: int, tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(models.CaseTag).filter_by(id=tag_id, case_id=case_id).first()
    if tag:
        db.delete(tag)
        db.commit()
    return RedirectResponse(f"/cases/{case_id}", status_code=303)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _all_tags(db: Session) -> list[dict]:
    tags = db.query(models.CaseTag).all()
    seen: dict[str, dict] = {}
    for t in tags:
        if t.name not in seen:
            seen[t.name] = {"name": t.name, "color": t.color, "count": 0}
        seen[t.name]["count"] += 1
    return sorted(seen.values(), key=lambda x: -x["count"])


def _do_search(q: str, tag: str, db: Session) -> dict:
    results: dict = {"cases": [], "evidence": [], "wiki": []}

    # ── Cases ──────────────────────────────────────────────────────
    case_q = db.query(models.Case)
    if q:
        term = f"%{q}%"
        case_q = case_q.filter(or_(
            models.Case.case_number.ilike(term),
            models.Case.name.ilike(term),
            models.Case.notes.ilike(term),
            models.Case.case_type.ilike(term),
        ))
    if tag:
        case_q = case_q.join(models.CaseTag).filter(models.CaseTag.name == tag)
    for c in case_q.order_by(models.Case.updated_at.desc()).limit(30).all():
        snippet = _snippet(c.notes or "", q)
        results["cases"].append({
            "id":          c.id,
            "case_number": c.case_number,
            "name":        c.name,
            "status":      c.status,
            "priority":    c.priority,
            "tags":        [{"name": t.name, "color": t.color} for t in c.tags],
            "snippet":     snippet,
            "url":         f"/cases/{c.id}",
        })

    # ── Evidence ───────────────────────────────────────────────────
    if q:
        term  = f"%{q}%"
        evs   = (
            db.query(models.Evidence)
            .filter(or_(
                models.Evidence.file_name.ilike(term),
                models.Evidence.notes.ilike(term),
                models.Evidence.md5.ilike(term),
                models.Evidence.sha256.ilike(term),
                models.Evidence.evidence_number.ilike(term),
            ))
            .limit(20).all()
        )
        for ev in evs:
            results["evidence"].append({
                "id":              ev.id,
                "case_id":         ev.case_id,
                "evidence_number": ev.evidence_number,
                "file_name":       ev.file_name,
                "category":        ev.category,
                "snippet":         _snippet(ev.notes or "", q),
                "url":             f"/cases/{ev.case_id}#tab-evidence",
            })

    # ── Wiki notes ─────────────────────────────────────────────────
    if q:
        term  = f"%{q}%"
        notes = (
            db.query(models.CaseNote)
            .filter(or_(
                models.CaseNote.title.ilike(term),
                models.CaseNote.content.ilike(term),
            ))
            .limit(20).all()
        )
        for n in notes:
            results["wiki"].append({
                "id":      n.id,
                "case_id": n.case_id,
                "title":   n.title,
                "snippet": _snippet(n.content or "", q),
                "url":     f"/cases/{n.case_id}/notes/{n.id}",
            })

    results["total"] = len(results["cases"]) + len(results["evidence"]) + len(results["wiki"])
    return results


def _snippet(text: str, q: str, ctx: int = 80) -> str:
    """Return a short snippet around first match of q in text."""
    if not q or not text:
        return text[:120] if text else ""
    idx = text.lower().find(q.lower())
    if idx < 0:
        return text[:120]
    start = max(0, idx - ctx // 2)
    end   = min(len(text), idx + len(q) + ctx // 2)
    pre   = "…" if start > 0 else ""
    suf   = "…" if end < len(text) else ""
    return pre + text[start:end] + suf
