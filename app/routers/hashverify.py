"""
Batch hash re-verification for all evidence in a case.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from .. import models
from ..core.hashing import hash_file
from ..core import audit

log = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/evidence", tags=["hashverify"])


# ── Status helpers ────────────────────────────────────────────────────────────

def _verify_evidence(ev: models.Evidence) -> dict:
    fp = Path(ev.file_path) if ev.file_path else None
    base = {
        "evidence_id":     ev.id,
        "evidence_number": ev.evidence_number,
        "file_name":       ev.file_name,
        "stored_md5":      ev.md5 or "",
        "stored_sha256":   ev.sha256 or "",
        "computed_md5":    "",
        "computed_sha256": "",
        "file_size":       ev.file_size or 0,
        "verified_at":     datetime.utcnow().isoformat(),
    }

    if not fp or not fp.exists():
        return {**base, "status": "missing"}

    if not ev.md5 and not ev.sha256:
        return {**base, "status": "no_hash", "file_size": fp.stat().st_size}

    try:
        md5, sha256 = hash_file(fp)
        base["computed_md5"]    = md5
        base["computed_sha256"] = sha256
        base["file_size"]       = fp.stat().st_size

        ok = True
        if ev.md5    and ev.md5    != md5:    ok = False
        if ev.sha256 and ev.sha256 != sha256: ok = False
        base["status"] = "ok" if ok else "tampered"
        return base
    except Exception as e:
        log.error("Hash error on %s: %s", fp, e)
        return {**base, "status": "error", "error": str(e)}


def _run_batch(case_id: int, run_by: str) -> None:
    db = SessionLocal()
    try:
        case = db.query(models.Case).filter_by(id=case_id).first()
        if not case:
            return

        results = []
        counts = {"ok": 0, "tampered": 0, "missing": 0, "no_hash": 0}

        for ev in case.evidence:
            r = _verify_evidence(ev)
            results.append(r)
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if r["status"] in ("ok", "tampered"):
                ev.verified_at = datetime.utcnow()

        batch = models.HashVerifyBatch(
            case_id        = case_id,
            run_by         = run_by,
            total          = len(results),
            ok_count       = counts["ok"],
            tampered_count = counts["tampered"],
            missing_count  = counts["missing"],
            no_hash_count  = counts["no_hash"],
            results_json   = json.dumps(results),
        )
        db.add(batch)
        db.commit()

        summary = (f"{counts['ok']} OK, {counts['tampered']} TAMPERED, "
                   f"{counts['missing']} MISSING, {counts['no_hash']} NO HASH")
        audit.log(db, case_id,
                  f"HASH VERIFY BATCH: {len(results)} evidence — {summary}",
                  investigator=run_by, app_name="HashVerify")
        if counts.get("tampered", 0) > 0:
            from .alerts import maybe_notify
            maybe_notify(
                db,
                rule_type="hash_tampered",
                title=f"Hash tampered: {counts['tampered']} evidence item(s)",
                body=summary,
                severity="critical",
                link=f"/cases/{case_id}",
                case_id=case_id,
            )
    except Exception as e:
        log.exception("Hash verify batch crashed: %s", e)
    finally:
        db.close()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/verify_batch")
def verify_batch(
    case_id: int,
    investigator: str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    background_tasks.add_task(_run_batch, case_id, investigator or "manual")
    return RedirectResponse(f"/cases/{case_id}#tab-hashverify", status_code=303)


@router.get("/verify_batch/results")
def verify_batch_results(case_id: int, db: Session = Depends(get_db)):
    latest = (
        db.query(models.HashVerifyBatch)
        .filter_by(case_id=case_id)
        .order_by(models.HashVerifyBatch.run_at.desc())
        .first()
    )
    if not latest:
        return JSONResponse({"status": "none"})
    return JSONResponse({
        "status":         "ok",
        "run_at":         latest.run_at.isoformat(),
        "run_by":         latest.run_by,
        "total":          latest.total,
        "ok_count":       latest.ok_count,
        "tampered_count": latest.tampered_count,
        "missing_count":  latest.missing_count,
        "no_hash_count":  latest.no_hash_count,
        "results":        json.loads(latest.results_json),
    })
