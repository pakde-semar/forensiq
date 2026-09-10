from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    BigInteger, Enum as SAEnum, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .database import Base


class CaseStatus(str, enum.Enum):
    open     = "Open"
    active   = "Active"
    review   = "Review"
    closed   = "Closed"
    archived = "Archived"


class CasePriority(str, enum.Enum):
    informational = "Informational"
    low           = "Low"
    medium        = "Medium"
    high          = "High"
    critical      = "Critical"


class CaseClassification(str, enum.Enum):
    public       = "Public"
    unclassified = "Unclassified"
    confidential = "Confidential"
    restricted   = "Restricted"
    fouo         = "For Official Use Only"
    secret       = "Secret"
    top_secret   = "Top Secret"


class EvidenceCategory(str, enum.Enum):
    graphics        = "Graphics"
    video           = "Video"
    forensic_images = "Forensic Images"
    virtual_machine = "Virtual Machines"
    ram             = "RAM"
    network         = "Network"
    logs            = "Logs"
    triage          = "Triage"
    cryptocurrency  = "Online/Cryptocurrency"
    darkweb         = "Online/DarkWeb"
    domains         = "Online/Domains"
    social_media    = "Online/Social Media"
    documents       = "Supporting Documents"
    other           = "Other"


class Agency(Base):
    __tablename__ = "agency"

    id                        = Column(Integer, primary_key=True)
    name                      = Column(String(255), nullable=False, default="")
    unit                      = Column(String(255), default="")
    address                   = Column(String(500), default="")
    city                      = Column(String(100), default="")
    country                   = Column(String(100), default="")
    phone                     = Column(String(50), default="")
    email                     = Column(String(255), default="")
    website                   = Column(String(255), default="")
    logo_path                 = Column(String(500), default="")
    case_prefix               = Column(String(20), default="CASE")
    supervisor_name           = Column(String(255), default="")
    supervisor_title          = Column(String(255), default="")
    evidence_intake_email     = Column(String(255), default="")
    legal_records_custodian   = Column(String(255), default="")


class Case(Base):
    __tablename__ = "cases"

    id             = Column(Integer, primary_key=True)
    case_number    = Column(String(50), unique=True, nullable=False)
    name           = Column(String(255), nullable=False)
    case_type      = Column(String(100), default="")
    status         = Column(String(50), default=CaseStatus.open)
    priority       = Column(String(50), default=CasePriority.medium)
    classification = Column(String(100), default=CaseClassification.confidential)
    notes          = Column(Text, default="")
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at      = Column(DateTime, nullable=True)

    # MISP / Flowintel links
    misp_event_id      = Column(String(100), default="")
    flowintel_case_id  = Column(Integer, nullable=True)

    investigators  = relationship("Investigator",   back_populates="case", cascade="all, delete-orphan")
    evidence       = relationship("Evidence",       back_populates="case", cascade="all, delete-orphan")
    audit_logs     = relationship("AuditLog",       back_populates="case", cascade="all, delete-orphan")
    reports        = relationship("Report",         back_populates="case", cascade="all, delete-orphan")
    pipeline_runs  = relationship("PipelineRun",    back_populates="case", cascade="all, delete-orphan",
                                  order_by="PipelineRun.started_at.desc()")


class Investigator(Base):
    __tablename__ = "investigators"

    id               = Column(Integer, primary_key=True)
    case_id          = Column(Integer, ForeignKey("cases.id"), nullable=False)
    name             = Column(String(255), nullable=False)
    email            = Column(String(255), default="")
    timeclock_minutes = Column(Integer, default=0)
    is_lead          = Column(Integer, default=0)  # 1 = lead investigator
    added_at         = Column(DateTime, default=datetime.utcnow)

    case = relationship("Case", back_populates="investigators")


class Evidence(Base):
    __tablename__ = "evidence"

    id                = Column(Integer, primary_key=True)
    case_id           = Column(Integer, ForeignKey("cases.id"), nullable=False)
    evidence_number   = Column(String(50), nullable=False)   # E-001
    coc_number        = Column(String(50), nullable=False)   # COC-001
    file_name         = Column(String(500), nullable=False)
    file_path         = Column(String(1000), default="")     # path di server
    file_size         = Column(BigInteger, default=0)        # bytes
    category          = Column(String(100), default=EvidenceCategory.other)
    original_location = Column(String(1000), default="")
    submitter         = Column(String(255), default="")
    md5               = Column(String(32), default="")
    sha256            = Column(String(64), default="")
    notes             = Column(Text, default="")
    date_added        = Column(DateTime, default=datetime.utcnow)
    verified_at       = Column(DateTime, nullable=True)

    case        = relationship("Case", back_populates="evidence")
    coc_entries = relationship("CoCEntry", back_populates="evidence",
                               cascade="all, delete-orphan",
                               order_by="CoCEntry.timestamp")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id           = Column(Integer, primary_key=True)
    case_id      = Column(Integer, ForeignKey("cases.id"), nullable=False)
    timestamp    = Column(DateTime, default=datetime.utcnow)
    app_name     = Column(String(100), default="ForensiQ")
    investigator = Column(String(255), default="")
    message      = Column(Text, nullable=False)

    case = relationship("Case", back_populates="audit_logs")


class Report(Base):
    __tablename__ = "reports"

    id         = Column(Integer, primary_key=True)
    case_id    = Column(Integer, ForeignKey("cases.id"), nullable=False)
    title      = Column(String(255), nullable=False)
    file_path  = Column(String(1000), nullable=False)
    format     = Column(String(10), default="html")   # html | pdf
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(255), default="")

    case = relationship("Case", back_populates="reports")


class CoCEntry(Base):
    __tablename__ = "coc_entries"

    id          = Column(Integer, primary_key=True)
    evidence_id = Column(Integer, ForeignKey("evidence.id"), nullable=False)
    timestamp   = Column(DateTime, default=datetime.utcnow)
    action      = Column(String(50), default="received")   # received|transferred|examined|returned|stored|disposed
    released_by = Column(String(255), default="")
    received_by = Column(String(255), default="")
    purpose     = Column(String(500), default="")
    location    = Column(String(255), default="")
    method      = Column(String(100), default="")          # in-person|courier|digital
    notes       = Column(Text, default="")

    evidence = relationship("Evidence", back_populates="coc_entries")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id             = Column(Integer, primary_key=True)
    case_id        = Column(Integer, ForeignKey("cases.id"), nullable=False)
    pipeline_name  = Column(String(100), nullable=False)
    pipeline_label = Column(String(200), default="")
    status         = Column(String(20), default="running")  # running | done | error
    input_type     = Column(String(50), default="case")     # case | evidence
    input_ref      = Column(String(500), default="")        # ev filename or "case"
    steps_json     = Column(Text, default="[]")             # [{module, status, findings, ms}]
    triggered_by   = Column(String(100), default="auto")
    risk_score     = Column(Float, nullable=True)
    started_at     = Column(DateTime, default=datetime.utcnow)
    completed_at   = Column(DateTime, nullable=True)

    case = relationship("Case", back_populates="pipeline_runs")
