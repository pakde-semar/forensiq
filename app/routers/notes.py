"""
Case wiki notes — Obsidian-style per-case markdown notes with wiki links.
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from ..templates_env import templates

router = APIRouter(prefix="/cases/{case_id}/notes", tags=["notes"])

_WELCOME = """# Case Overview

Welcome to the **Case Wiki**. Use this space to document your investigation.

## Summary

*Add a brief summary of the case here.*

## Key Findings

-

## IOCs

Paste extracted indicators here, or use the **IOC Extractor** tab.

## Timeline

| Date | Event |
|------|-------|
|      |       |

## References

- [[Evidence Log]]
- [[Chain of Custody]]
"""


def _get_or_create_welcome(case_id: int, db: Session) -> models.CaseNote:
    note = db.query(models.CaseNote).filter_by(case_id=case_id).order_by(
        models.CaseNote.updated_at.desc()).first()
    if not note:
        note = models.CaseNote(case_id=case_id, title="Case Overview", content=_WELCOME)
        db.add(note)
        db.commit()
        db.refresh(note)
    return note


def _find_backlinks(note: models.CaseNote, all_notes: list[models.CaseNote]) -> list[models.CaseNote]:
    pattern = re.compile(r'\[\[' + re.escape(note.title) + r'\]\]', re.IGNORECASE)
    return [n for n in all_notes if n.id != note.id and pattern.search(n.content or "")]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
@router.get("/")
def notes_index(case_id: int, db: Session = Depends(get_db)):
    note = _get_or_create_welcome(case_id, db)
    return RedirectResponse(f"/cases/{case_id}/notes/{note.id}", status_code=302)


@router.get("/new")
def notes_new_get(case_id: int, title: str = "", db: Session = Depends(get_db)):
    note = models.CaseNote(case_id=case_id, title=title or "Untitled", content="")
    db.add(note)
    db.commit()
    db.refresh(note)
    return RedirectResponse(f"/cases/{case_id}/notes/{note.id}", status_code=302)


@router.get("/{note_id}")
def notes_editor(case_id: int, note_id: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(models.Case).filter_by(id=case_id).first()
    note = db.query(models.CaseNote).filter_by(id=note_id, case_id=case_id).first()
    if not note:
        return RedirectResponse(f"/cases/{case_id}/notes", status_code=302)
    all_notes  = db.query(models.CaseNote).filter_by(case_id=case_id).order_by(
        models.CaseNote.updated_at.desc()).all()
    backlinks  = _find_backlinks(note, all_notes)
    notes_meta = [{"id": n.id, "title": n.title} for n in all_notes]
    return templates.TemplateResponse(request, "notes/editor.html", {
        "case":       case,
        "note":       note,
        "all_notes":  all_notes,
        "backlinks":  backlinks,
        "notes_meta": notes_meta,
    })


@router.post("/{note_id}/save")
async def notes_save(case_id: int, note_id: int, request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    note = db.query(models.CaseNote).filter_by(id=note_id, case_id=case_id).first()
    if not note:
        return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
    if "title" in body:
        note.title = body["title"].strip() or "Untitled"
    if "content" in body:
        note.content = body["content"]
    note.updated_at = datetime.utcnow()
    db.commit()
    return JSONResponse({"ok": True, "updated_at": note.updated_at.strftime("%H:%M:%S")})


@router.post("/{note_id}/delete")
def notes_delete(case_id: int, note_id: int, db: Session = Depends(get_db)):
    note = db.query(models.CaseNote).filter_by(id=note_id, case_id=case_id).first()
    if note:
        db.delete(note)
        db.commit()
    return RedirectResponse(f"/cases/{case_id}/notes", status_code=302)
