from sqlalchemy.orm import Session
from datetime import datetime
from .. import models


def log(db: Session, case_id: int, message: str,
        investigator: str = "", app_name: str = "ForensiQ"):
    entry = models.AuditLog(
        case_id      = case_id,
        timestamp    = datetime.utcnow(),
        app_name     = app_name,
        investigator = investigator,
        message      = message,
    )
    db.add(entry)
    db.commit()
