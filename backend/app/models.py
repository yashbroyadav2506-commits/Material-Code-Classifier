from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class CPSE(Base):
    __tablename__ = "cpse"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    short_name = Column(String(50), nullable=False, unique=True)
    sector = Column(String(100), default="")

    materials = relationship("Material", back_populates="cpse")


class Material(Base):
    """One legacy material-master record reported by a CPSE."""

    __tablename__ = "material_records"

    id = Column(Integer, primary_key=True)
    cpse_id = Column(Integer, ForeignKey("cpse.id"), nullable=False)
    legacy_code = Column(String(100), nullable=False)
    raw_description = Column(Text, nullable=False)
    normalized_description = Column(Text, default="")
    category = Column(String(100), default="")
    raw_unit = Column(String(50), default="")
    normalized_unit = Column(String(50), default="")
    manufacturer = Column(String(200), default="")
    part_number = Column(String(100), default="")
    source_file = Column(String(255), default="")
    attributes = Column(JSON, default=dict)
    extraction_method = Column(String(50), default="none")  # llm | regex | none
    status = Column(String(50), default="ingested")  # ingested|extracted|matched|unmatched
    is_duplicate = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    cpse = relationship("CPSE", back_populates="materials")
    procurements = relationship("Procurement", back_populates="material")

    @property
    def label(self):
        return f"{self.cpse.short_name if self.cpse else '?'}:{self.legacy_code}"


class Procurement(Base):
    __tablename__ = "procurement_history"

    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("material_records.id"), nullable=False)
    year = Column(Integer)
    quantity = Column(Float)
    unit_price = Column(Float)  # per unit in selected currency
    currency = Column(String(10), default="INR")
    vendor = Column(String(200), default="")

    material = relationship("Material", back_populates="procurements")


class CommonMaterial(Base):
    """An approved national unified material master record."""

    __tablename__ = "common_material_master"

    id = Column(Integer, primary_key=True)
    national_code = Column(String(120), nullable=False, unique=True)
    standardized_name = Column(String(300), nullable=False)
    classification_code = Column(String(100), default="")
    standard_attributes = Column(JSON, default=dict)
    description = Column(Text, default="")
    approved_by = Column(String(100), default="")
    approved_at = Column(DateTime)
    is_active = Column(Boolean, default=True)

    mappings = relationship("Mapping", back_populates="common_material")


class Mapping(Base):
    """Traceable link between a legacy CPSE code and a common national code.

    Unapproved rows with no common_material_id act as pending review tasks
    created by the AI candidate-generation phase.
    """

    __tablename__ = "mapping"

    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("material_records.id"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("material_records.id"), nullable=True)
    common_material_id = Column(Integer, ForeignKey("common_material_master.id"), nullable=True)

    match_type = Column(String(50), default="duplicate")  # identical|duplicate|near_duplicate|functionally_equivalent
    confidence_score = Column(Float, default=0.0)
    evidence = Column(JSON, default=dict)          # shared/conflicting attrs, per-component scores
    safety_flag = Column(Boolean, default=False)
    review_status = Column(String(50), default="pending")  # pending|approved|rejected|edited|escalated
    reviewer_comment = Column(Text, default="")
    decided_by = Column(String(100), default="")
    decided_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)

    material = relationship("Material", foreign_keys=[material_id])
    candidate = relationship("Material", foreign_keys=[candidate_id])
    common_material = relationship("CommonMaterial", back_populates="mappings")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    action = Column(String(100), nullable=False)
    entity = Column(String(100), default="")
    entity_id = Column(String(50), default="")
    performed_by = Column(String(100), default="")
    old_value = Column(JSON, default=dict)
    new_value = Column(JSON, default=dict)
    timestamp = Column(DateTime, default=utcnow)