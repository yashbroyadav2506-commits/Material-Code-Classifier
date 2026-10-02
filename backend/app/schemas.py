from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, model_validator


class CPSEOut(BaseModel):
    id: int
    name: str
    short_name: str
    sector: str = ""

    class Config:
        from_attributes = True


class MaterialOut(BaseModel):
    id: int
    cpse: str = ""
    cpse_id: int
    legacy_code: str
    raw_description: str
    normalized_description: str = ""
    category: str = ""
    raw_unit: str = ""
    normalized_unit: str = ""
    manufacturer: str = ""
    part_number: str = ""
    source_file: str = ""
    attributes: dict = {}
    extraction_method: str = "none"
    status: str = "ingested"
    is_duplicate: bool = False
    created_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def coerce_cpse(cls, data):
        if data is not None and not isinstance(data, dict) and hasattr(data, "cpse"):
            out = {}
            for f in cls.model_fields:
                if hasattr(data, f):
                    v = getattr(data, f)
                    if f == "cpse" and not isinstance(v, str):
                        v = getattr(v, "short_name", "") or ""
                    out[f] = v
            return out
        return data

    class Config:
        from_attributes = True


class AttributeExtractIn(BaseModel):
    description: str


class MatchResultOut(BaseModel):
    pair_id: int
    material_a: dict
    material_b: dict
    score: float
    match_type: str
    safety_flag: bool
    evidence: dict
    review_status: str


class ReviewDecisionIn(BaseModel):
    decision: str  # approve | reject | edit | escalate
    comment: str = ""
    match_type: Optional[str] = None
    standardized_name: Optional[str] = None
    national_code: Optional[str] = None
    attributes_override: Optional[dict] = None
    decided_by: str = "reviewer@cpse.gov.in"


class AuditOut(BaseModel):
    id: int
    action: str
    entity: str
    entity_id: str
    performed_by: str
    old_value: dict = {}
    new_value: dict = {}
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class UploadSummary(BaseModel):
    inserted: int
    skipped_duplicates: int
    errors: list = []
    total_records: int
    llm_mode: str


class SavingsRow(BaseModel):
    national_code: Optional[str]
    standardized_name: Optional[str]
    category: str
    cpse_count: int
    total_quantity: float
    min_price: Optional[float]
    max_price: Optional[float]
    potential_savings: float
    rank: Optional[Any] = None


class DashboardStats(BaseModel):
    total_records: int
    cpse_count: int
    matched_records: int
    pending_reviews: int
    approved_mappings: int
    national_codes: int
    duplicate_clusters: int
    near_miss_count: int
    potential_savings: float
    data_quality: dict
    category_duplicates: list