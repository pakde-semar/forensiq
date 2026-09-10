from sqlalchemy.orm import Session
from .. import models


def next_evidence_number(case_id: int, db: Session) -> str:
    count = db.query(models.Evidence).filter_by(case_id=case_id).count()
    return f"E-{count + 1:03d}"


def next_coc_number(case_id: int, db: Session) -> str:
    count = db.query(models.Evidence).filter_by(case_id=case_id).count()
    return f"COC-{count + 1:03d}"


def generate_case_number(prefix: str, db: Session) -> str:
    count = db.query(models.Case).count()
    return f"{prefix}-{count + 1:04d}"
