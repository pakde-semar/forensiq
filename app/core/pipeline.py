"""
ForensiQ Pipeline Engine.

A pipeline is an ordered list of modules that share a context dict.
Each module outputs findings and optional notes; findings accumulate
in context["prior_findings"] so downstream modules can build on them.
"""
import importlib.util
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ─── Pipeline definitions ─────────────────────────────────────────────────────

PIPELINES: dict[str, dict] = {
    "evidence_intake": {
        "label":       "Evidence Intake",
        "icon":        "fa-upload",
        "description": "Auto-runs on each evidence upload: hash reputation, IOC extraction, metadata.",
        "auto_on":     ["evidence_upload"],
        "modules":     ["hash_intel", "ioc_extract", "metadata"],
    },
    "case_assessment": {
        "label":       "Case Assessment",
        "icon":        "fa-chart-bar",
        "description": "Full analysis: hash check all evidence → extract IOCs → risk score.",
        "auto_on":     [],
        "modules":     ["hash_intel", "ioc_extract", "risk_score"],
    },
    "threat_intel_sync": {
        "label":       "Threat Intel Sync",
        "icon":        "fa-diagram-project",
        "description": "Extract all IOCs → score risk → push to Flowintel as observables.",
        "auto_on":     [],
        "modules":     ["ioc_extract", "risk_score", "flowintel_push"],
    },
    "misp_sync": {
        "label":       "MISP Sync",
        "icon":        "fa-shield-virus",
        "description": "Extract IOCs from case → push to linked MISP event as attributes.",
        "auto_on":     [],
        "modules":     ["ioc_extract", "misp_push"],
    },
    "yara_scan": {
        "label":       "Yara Scan",
        "icon":        "fa-shield-halved",
        "description": "Scan all evidence files against enabled Yara rules.",
        "auto_on":     [],
        "modules":     ["yara_scan"],
    },
    "hash_verify": {
        "label":       "Hash Verify",
        "icon":        "fa-shield-check",
        "description": "Re-hash all evidence files and compare against stored hashes.",
        "auto_on":     [],
        "modules":     ["hashverify"],
    },
}

# ─── Module loader ─────────────────────────────────────────────────────────────

_MODULE_DIR = Path(__file__).resolve().parent.parent / "pipelines"
_cache: dict[str, Any] = {}


def _load_module(name: str) -> Any | None:
    if name in _cache:
        return _cache[name]
    for f in _MODULE_DIR.glob(f"_*_{name}.py"):
        spec = importlib.util.spec_from_file_location(f"app.pipelines.{f.stem}", str(f))
        if not spec:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            _cache[name] = mod
            return mod
        except Exception as e:
            log.error("Failed to load pipeline module %s: %s", name, e)
    log.warning("Pipeline module not found: %s", name)
    return None


# ─── Background runner ────────────────────────────────────────────────────────

def run_pipeline_background(
    pipeline_name: str,
    case_id: int,
    evidence_id: int | None = None,
    triggered_by: str = "auto",
) -> None:
    """
    Runs a pipeline in a FastAPI background task.
    Creates its own DB session — must NOT receive the request's session.
    """
    from ..database import SessionLocal
    from .. import models
    from .audit import log as audit_log

    pipeline = PIPELINES.get(pipeline_name)
    if not pipeline:
        log.error("Unknown pipeline: %s", pipeline_name)
        return

    db = SessionLocal()
    try:
        case     = db.query(models.Case).filter_by(id=case_id).first()
        evidence = db.query(models.Evidence).filter_by(id=evidence_id).first() if evidence_id else None
        if not case:
            return

        input_ref = evidence.file_name if evidence else f"case:{case.case_number}"

        run = models.PipelineRun(
            case_id        = case_id,
            pipeline_name  = pipeline_name,
            pipeline_label = pipeline["label"],
            status         = "running",
            input_type     = "evidence" if evidence else "case",
            input_ref      = input_ref,
            steps_json     = "[]",
            triggered_by   = triggered_by,
            started_at     = datetime.utcnow(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        context: dict[str, Any] = {
            "case":           case,
            "evidence":       evidence,
            "prior_findings": [],
            "iocs":           {},
        }

        steps: list[dict] = []

        for module_name in pipeline["modules"]:
            mod = _load_module(module_name)
            step: dict[str, Any] = {
                "module": module_name,
                "label":  getattr(mod, "MODULE_LABEL", module_name) if mod else module_name,
                "icon":   getattr(mod, "MODULE_ICON", "fa-circle") if mod else "fa-circle",
                "status": "error",
                "findings": [],
                "ms": 0,
            }

            if not mod:
                step["findings"] = [{"type": "warning", "title": f"Module '{module_name}' not found", "detail": ""}]
                steps.append(step)
                continue

            t0 = time.monotonic()
            try:
                result = mod.run(context)
                step["status"]   = result.get("status", "done")
                step["findings"] = result.get("findings", [])
                step["ms"]       = round((time.monotonic() - t0) * 1000)

                # Propagate IOCs and risk score to context
                if "iocs" in result:
                    context["iocs"] = result["iocs"]
                if "risk_score" in result:
                    context["risk_score"] = result["risk_score"]
                    context["risk_level"]  = result.get("risk_level", "")
                    run.risk_score = result["risk_score"]

                # Append notes
                if result.get("notes") and case:
                    case.notes = (case.notes or "").rstrip() + result["notes"]
                    db.commit()

                # Flowintel link-back
                if result.get("flowintel_case_id") and not case.flowintel_case_id:
                    case.flowintel_case_id = result["flowintel_case_id"]
                    db.commit()

                context["prior_findings"].extend(step["findings"])

            except Exception as e:
                step["status"]   = "error"
                step["findings"] = [{"type": "error", "title": str(e)[:200], "detail": ""}]
                step["ms"]       = round((time.monotonic() - t0) * 1000)
                log.exception("Module %s failed", module_name)

            steps.append(step)

            # Save progress after each step
            run.steps_json = json.dumps(steps)
            db.commit()

            if step["status"] == "error":
                break

        # Finalize
        has_error    = any(s["status"] == "error"   for s in steps)
        critical_ct  = sum(
            1 for s in steps for f in s["findings"] if f.get("type") == "critical"
        )
        run.status       = "error" if has_error else "done"
        run.steps_json   = json.dumps(steps)
        run.completed_at = datetime.utcnow()
        db.commit()

        suffix = f" — {critical_ct} critical" if critical_ct else ""
        audit_log(
            db, case_id,
            f"Pipeline '{pipeline['label']}' {run.status}{suffix} ({len(steps)} step(s))",
            investigator=triggered_by,
            app_name="Pipeline",
        )

    except Exception as e:
        log.exception("Pipeline runner crashed: %s", e)
        try:
            if "run" in dir() and run.id:
                run.status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


def trigger_auto(
    trigger: str,
    case_id: int,
    evidence_id: int | None = None,
    background_tasks: Any = None,
) -> None:
    """Queue all pipelines that auto-run on the given trigger."""
    for name, p in PIPELINES.items():
        if trigger in p.get("auto_on", []):
            if background_tasks:
                background_tasks.add_task(
                    run_pipeline_background, name, case_id, evidence_id, "auto"
                )
            else:
                run_pipeline_background(name, case_id, evidence_id, "auto")
