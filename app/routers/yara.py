"""
Yara rule management and per-case scanning.
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import yara
from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db, SessionLocal
from .. import models
from ..templates_env import templates
from ..core import audit

log = logging.getLogger(__name__)

router = APIRouter(tags=["yara"])


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE_RULES = [
    {
        "name": "Webshell_PHP_Generic",
        "source": "sample",
        "tags": "webshell,php",
        "description": "Generic PHP webshell patterns",
        "content": """rule Webshell_PHP_Generic {
    meta:
        description = "Generic PHP webshell detection"
        severity = "high"
    strings:
        $s1 = "eval(base64_decode(" ascii
        $s2 = "system($_GET" ascii
        $s3 = "passthru($_POST" ascii
        $s4 = "shell_exec($_REQUEST" ascii
        $s5 = "<?php @eval" ascii
        $s6 = "preg_replace(\"/.*/e\"" ascii
    condition:
        any of them
}""",
    },
    {
        "name": "Mimikatz_Strings",
        "source": "sample",
        "tags": "credential,mimikatz",
        "description": "Mimikatz credential dumper strings",
        "content": """rule Mimikatz_Strings {
    meta:
        description = "Mimikatz credential dumper indicators"
        severity = "critical"
    strings:
        $s1 = "sekurlsa::logonpasswords" ascii nocase
        $s2 = "lsadump::sam" ascii nocase
        $s3 = "lsadump::dcsync" ascii nocase
        $s4 = "mimikatz" ascii nocase
        $s5 = "Benjamin DELPY" ascii
        $s6 = "kiwi" ascii fullword
    condition:
        2 of them
}""",
    },
    {
        "name": "Ransomware_Strings",
        "source": "sample",
        "tags": "ransomware,encryption",
        "description": "Common ransomware note and extension patterns",
        "content": """rule Ransomware_Strings {
    meta:
        description = "Common ransomware indicators"
        severity = "critical"
    strings:
        $n1 = "YOUR FILES HAVE BEEN ENCRYPTED" ascii nocase wide
        $n2 = "HOW TO RECOVER" ascii nocase wide
        $n3 = "DECRYPT_INSTRUCTION" ascii nocase wide
        $n4 = "Bitcoin" ascii wide
        $n5 = ".WNCRY" ascii
        $n6 = "WanaCrypt0r" ascii
        $n7 = "HELP_DECRYPT" ascii nocase
        $n8 = "READ_ME.txt" ascii nocase
    condition:
        2 of them
}""",
    },
    {
        "name": "Suspicious_PowerShell",
        "source": "sample",
        "tags": "powershell,obfuscation",
        "description": "Obfuscated or suspicious PowerShell patterns",
        "content": """rule Suspicious_PowerShell {
    meta:
        description = "Suspicious or obfuscated PowerShell usage"
        severity = "medium"
    strings:
        $s1 = "powershell" ascii nocase
        $d1 = "-enc " ascii nocase
        $d2 = "-encodedcommand" ascii nocase
        $d3 = "-windowstyle hidden" ascii nocase
        $d4 = "IEX(" ascii nocase
        $d5 = "Invoke-Expression" ascii nocase
        $d6 = "DownloadString(" ascii nocase
        $d7 = "Net.WebClient" ascii nocase
        $d8 = "-noprofile" ascii nocase
        $d9 = "bypass" ascii nocase
    condition:
        $s1 and 2 of ($d*)
}""",
    },
    {
        "name": "Embedded_PE_in_Document",
        "source": "sample",
        "tags": "dropper,macro",
        "description": "PE executable header inside a document file",
        "content": """rule Embedded_PE_in_Document {
    meta:
        description = "Detects embedded PE binary inside document (dropper)"
        severity = "high"
    strings:
        $mz  = { 4D 5A }
        $pe  = { 50 45 00 00 }
        $doc1 = "Microsoft Office" ascii
        $doc2 = "%PDF-" ascii
        $doc3 = "\\x50\\x4B\\x03\\x04" // ZIP (docx/xlsx)
    condition:
        ($mz at 0 or $pe) and (any of ($doc*))
}""",
    },
    {
        "name": "Log_Bruteforce_Indicators",
        "source": "sample",
        "tags": "bruteforce,login",
        "description": "Brute force login indicators in log files",
        "content": """rule Log_Bruteforce_Indicators {
    meta:
        description = "Multiple failed authentication attempts in log files"
        severity = "medium"
    strings:
        $s1 = "Failed password" ascii
        $s2 = "authentication failure" ascii nocase
        $s3 = "Invalid user" ascii nocase
        $s4 = "FAILED LOGIN" ascii nocase
        $s5 = "401 Unauthorized" ascii
        $s6 = "403 Forbidden" ascii
        $s7 = "Too many authentication" ascii nocase
    condition:
        3 of them
}""",
    },
]


def _compile_enabled_rules(db: Session) -> yara.Rules | None:
    rules_src = db.query(models.YaraRule).filter_by(enabled=1).all()
    if not rules_src:
        return None
    sources: dict[str, str] = {}
    for r in rules_src:
        try:
            yara.compile(source=r.content)  # validate first
            sources[f"ns_{r.id}"] = r.content
        except yara.SyntaxError as e:
            log.warning("Yara rule '%s' skipped (syntax error): %s", r.name, e)
    if not sources:
        return None
    return yara.compile(sources=sources)


def _scan_case_background(case_id: int, scanned_by: str) -> None:
    db = SessionLocal()
    try:
        case = db.query(models.Case).filter_by(id=case_id).first()
        if not case:
            return

        rules = _compile_enabled_rules(db)
        results = []
        file_count = 0

        for ev in case.evidence:
            fp = Path(ev.file_path) if ev.file_path else None
            if not fp or not fp.exists():
                continue
            file_count += 1
            if rules is None:
                continue
            try:
                matches = rules.match(str(fp), timeout=30)
                if matches:
                    match_list = []
                    for m in matches:
                        strings = []
                        for s in m.strings:
                            strings.append({
                                "id":     s.identifier,
                                "offset": s.instances[0].offset if s.instances else 0,
                                "data":   repr(bytes(s.instances[0].matched_data)[:80])
                                          if s.instances else "",
                            })
                        match_list.append({
                            "rule":    m.rule,
                            "tags":    list(m.tags),
                            "strings": strings[:20],
                        })
                    results.append({
                        "evidence_id":     ev.id,
                        "evidence_number": ev.evidence_number,
                        "file_name":       ev.file_name,
                        "file_path":       str(fp),
                        "matches":         match_list,
                    })
            except yara.TimeoutError:
                log.warning("Yara scan timeout on %s", fp)
            except Exception as e:
                log.error("Yara scan error on %s: %s", fp, e)

        match_count = sum(len(r["matches"]) for r in results)
        sr = models.YaraScanResult(
            case_id      = case_id,
            scanned_by   = scanned_by,
            file_count   = file_count,
            match_count  = match_count,
            results_json = json.dumps(results),
        )
        db.add(sr)
        db.commit()

        audit.log(db, case_id,
                  f"YARA SCAN: {file_count} file(s) scanned, {match_count} match(es) found",
                  investigator=scanned_by, app_name="Yara")
    except Exception as e:
        log.exception("Yara background scan crashed: %s", e)
    finally:
        db.close()


# ── Rule management page ──────────────────────────────────────────────────────

@router.get("/yara")
def yara_index(request: Request, db: Session = Depends(get_db)):
    rules = db.query(models.YaraRule).order_by(models.YaraRule.created_at.desc()).all()
    return templates.TemplateResponse(request, "yara/index.html", {"rules": rules})


@router.post("/yara/rules")
def yara_rule_add(
    name:        str = Form(...),
    description: str = Form(""),
    tags:        str = Form(""),
    content:     str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        yara.compile(source=content)
    except yara.SyntaxError as e:
        rules = db.query(models.YaraRule).order_by(models.YaraRule.created_at.desc()).all()
        return templates.TemplateResponse(None, "yara/index.html", {
            "rules": rules,
            "error": f"Syntax error in rule: {e}",
            "form_name": name, "form_desc": description,
            "form_tags": tags, "form_content": content,
        }, status_code=422)
    rule = models.YaraRule(name=name, description=description, tags=tags, content=content)
    db.add(rule)
    db.commit()
    return RedirectResponse("/yara", status_code=303)


@router.post("/yara/rules/{rule_id}/toggle")
def yara_rule_toggle(rule_id: int, db: Session = Depends(get_db)):
    r = db.query(models.YaraRule).filter_by(id=rule_id).first()
    if r:
        r.enabled = 0 if r.enabled else 1
        db.commit()
    return RedirectResponse("/yara", status_code=303)


@router.post("/yara/rules/{rule_id}/edit")
def yara_rule_edit(
    rule_id:     int,
    name:        str = Form(...),
    description: str = Form(""),
    tags:        str = Form(""),
    content:     str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        yara.compile(source=content)
    except yara.SyntaxError as e:
        return RedirectResponse(f"/yara?error={e}", status_code=303)
    r = db.query(models.YaraRule).filter_by(id=rule_id).first()
    if r:
        r.name, r.description, r.tags, r.content = name, description, tags, content
        r.updated_at = datetime.utcnow()
        db.commit()
    return RedirectResponse("/yara", status_code=303)


@router.post("/yara/rules/{rule_id}/delete")
def yara_rule_delete(rule_id: int, db: Session = Depends(get_db)):
    r = db.query(models.YaraRule).filter_by(id=rule_id).first()
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse("/yara", status_code=303)


@router.post("/yara/rules/load_samples")
def yara_load_samples(db: Session = Depends(get_db)):
    existing = {r.name for r in db.query(models.YaraRule.name).all()}
    for s in _SAMPLE_RULES:
        if s["name"] not in existing:
            db.add(models.YaraRule(
                name=s["name"], description=s["description"],
                tags=s["tags"], content=s["content"], source=s["source"],
            ))
    db.commit()
    return RedirectResponse("/yara", status_code=303)


# ── Per-case scan endpoints ───────────────────────────────────────────────────

@router.post("/cases/{case_id}/yara/scan")
def yara_scan_case(
    case_id: int,
    investigator: str = Form(""),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    enabled_count = db.query(models.YaraRule).filter_by(enabled=1).count()
    if enabled_count == 0:
        return RedirectResponse(f"/cases/{case_id}#tab-yara", status_code=303)
    background_tasks.add_task(_scan_case_background, case_id, investigator or "manual")
    return RedirectResponse(f"/cases/{case_id}#tab-yara", status_code=303)


@router.get("/cases/{case_id}/yara/results")
def yara_scan_results(case_id: int, db: Session = Depends(get_db)):
    latest = (
        db.query(models.YaraScanResult)
        .filter_by(case_id=case_id)
        .order_by(models.YaraScanResult.scanned_at.desc())
        .first()
    )
    if not latest:
        return JSONResponse({"status": "none"})
    return JSONResponse({
        "status":      "ok",
        "scanned_at":  latest.scanned_at.isoformat(),
        "scanned_by":  latest.scanned_by,
        "file_count":  latest.file_count,
        "match_count": latest.match_count,
        "results":     json.loads(latest.results_json),
    })
