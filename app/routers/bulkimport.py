"""Bulk evidence import from a ZIP archive."""
import io
import uuid
import zipfile
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from .. import models
from ..core.hashing import hash_file
from ..core.coc import next_evidence_number
from ..core import audit

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["bulkimport"])

UPLOADS_DIR = Path("uploads")
MAX_FILE_SIZE = 500 * 1024 * 1024   # 500 MB per file
MAX_FILES     = 300
SKIP_PREFIXES = ("__MACOSX/", ".", "_")

# In-memory task status (per process lifetime)
_tasks: dict[str, dict] = {}


# ── Status endpoint ───────────────────────────────────────────────────────────

@router.get("/bulk_import/{task_id}")
def bulk_import_status(case_id: int, task_id: str):
    task = _tasks.get(task_id)
    if not task:
        return JSONResponse({"status": "not_found"}, status_code=404)
    return task


# ── Upload endpoint ───────────────────────────────────────────────────────────

@router.post("/bulk_import")
async def bulk_import(
    case_id:      int,
    background:   BackgroundTasks,
    zip_file:     UploadFile = File(...),
    category:     str = Form(""),
    investigator: str = Form(""),
    notes_prefix: str = Form(""),
    db: Session = Depends(get_db),
):
    # Validate case
    case = db.query(models.Case).filter_by(id=case_id).first()
    if not case:
        return JSONResponse({"error": "Case not found"}, status_code=404)

    # Read ZIP content
    raw = await zip_file.read()
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        return JSONResponse({"error": "File is not a valid ZIP archive"}, status_code=400)

    # Count files first
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        entries = [
            e for e in zf.infolist()
            if not e.is_dir()
            and not _should_skip(e.filename)
            and e.file_size <= MAX_FILE_SIZE
        ]

    if len(entries) > MAX_FILES:
        return JSONResponse(
            {"error": f"ZIP contains {len(entries)} files — max {MAX_FILES} allowed"},
            status_code=400,
        )

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "status":    "running",
        "total":     len(entries),
        "processed": 0,
        "imported":  0,
        "skipped":   0,
        "errors":    [],
        "files":     [],
        "zip_name":  zip_file.filename or "archive.zip",
    }

    background.add_task(
        _process_zip,
        task_id, case_id, raw, entries,
        category, investigator, notes_prefix, zip_file.filename or "archive.zip",
    )

    return {"task_id": task_id, "total": len(entries)}


# ── Background processing ─────────────────────────────────────────────────────

def _should_skip(name: str) -> bool:
    parts = Path(name).parts
    if not parts:
        return True
    base = parts[-1]
    if base.startswith(".") or base.startswith("_"):
        return True
    if any(p.startswith("__MACOSX") for p in parts):
        return True
    # Path traversal guard
    if ".." in parts:
        return True
    return False


def _process_zip(
    task_id:      str,
    case_id:      int,
    raw:          bytes,
    entries:      list,
    category:     str,
    investigator: str,
    notes_prefix: str,
    zip_name:     str,
):
    db = SessionLocal()
    try:
        task = _tasks[task_id]

        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for entry in entries:
                fname = Path(entry.filename).name  # only the filename, no dirs
                try:
                    # Destination path
                    dest_dir = UPLOADS_DIR / f"case_{case_id}"
                    dest_dir.mkdir(parents=True, exist_ok=True)

                    # Unique filename if collision
                    dest = dest_dir / fname
                    if dest.exists():
                        stem = dest.stem
                        suf  = dest.suffix
                        dest = dest_dir / f"{stem}_{uuid.uuid4().hex[:6]}{suf}"

                    # Extract
                    data = zf.read(entry.filename)
                    dest.write_bytes(data)

                    # Hash
                    md5, sha256 = hash_file(dest)

                    # Evidence number
                    ev_num = next_evidence_number(case_id, db)

                    note_txt = f"Bulk imported from {zip_name}"
                    if notes_prefix.strip():
                        note_txt = notes_prefix.strip() + " · " + note_txt

                    ev = models.Evidence(
                        case_id         = case_id,
                        evidence_number = ev_num,
                        file_name       = fname,
                        file_path       = str(dest),
                        category        = category or models.EvidenceCategory.other,
                        size_bytes      = entry.file_size,
                        md5             = md5,
                        sha256          = sha256,
                        added_by        = investigator,
                        notes           = note_txt,
                        acquired_at     = datetime.utcnow(),
                    )
                    db.add(ev)
                    db.commit()
                    db.refresh(ev)

                    task["files"].append({"name": fname, "status": "ok", "ev_num": ev_num})
                    task["imported"] += 1

                except Exception as e:
                    task["errors"].append({"name": fname, "error": str(e)[:200]})
                    task["skipped"] += 1

                task["processed"] += 1

        audit.log(
            db, case_id,
            f"Bulk imported {task['imported']} evidence from {zip_name}",
            investigator=investigator, app_name="BulkImport",
        )
        task["status"] = "done"

    except Exception as e:
        _tasks[task_id]["status"] = "error"
        _tasks[task_id]["errors"].append({"name": "—", "error": str(e)[:300]})
    finally:
        db.close()
