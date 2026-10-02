"""Orchestration of the end-to-end workflow.

ingest -> normalize -> attribute extraction -> candidate matching ->
human review -> common-code creation -> audit trail
"""

import itertools
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..llm.provider import get_llm
from ..models import AuditLog, Mapping, Material
from . import audit, matching as matching_svc
from .normalization import canonical_unit, normalize_description
from .services_deps import extract_with, material_dict

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


def process_record(db: Session, material: Material, llm=None):
    """Normalize + extract attributes for one record in place."""
    llm = llm or get_llm()
    material.normalized_description = normalize_description(material.raw_description)
    material.normalized_unit = canonical_unit(material.raw_unit)
    attrs, method = extract_with(material, llm)
    material.attributes = attrs
    if attrs.get("category"):
        material.category = attrs["category"]
    if attrs.get("unit"):
        material.normalized_unit = attrs.get("unit") or material.normalized_unit
    material.extraction_method = method
    material.status = "extracted" if method != "none" else "ingested"
    return attrs


def run_matching_candidates(db: Session, llm=None, limit_record_ids=None):
    """Generate candidate Mapping rows for pending review.

    Compares records across CPSEs within the same category family and stores
    high/medium confidence pairs as pending review tasks.
    """
    llm = llm or get_llm()
    from ..config import settings

    refine_llm = settings.llm_refine_matching_bulk
    q = db.query(Material)
    if limit_record_ids:
        q = q.filter(Material.id.in_(limit_record_ids))
    materials = q.all()
    if len(materials) < 2:
        return 0

    # group by category family so pairwise work stays small
    by_cat = {}
    for m in materials:
        cat = (m.category or "UNCAT").upper()
        by_cat.setdefault(cat, []).append(m)

    created = 0
    pairs = []
    for cat, group in by_cat.items():
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                a, b = group[i], group[j]
                if a.cpse_id == b.cpse_id and a.legacy_code == b.legacy_code:
                    continue
                m_a = material_dict(a)
                m_b = material_dict(b)
                if not (m_a.get("attrs") or m_b.get("attrs")):
                    continue
                try:
                    verdict = matching_svc.compare(m_a, m_b, llm, refine=False)
                except Exception as exc:
                    logger.warning("compare failed %s vs %s: %s", a.id, b.id, exc)
                    continue
                if verdict["score"] < 50:
                    continue
                if verdict["match_type"] == "different":
                    continue
                pairs.append((a, b, m_a, m_b, verdict))

    # Optionally refine the top pairs with the live LLM so the demo shows
    # semantic judgments without paying for every pairwise combination.
    if llm.mode != "mock" and refine_llm:
        pairs.sort(key=lambda p: p[4]["score"], reverse=True)
        top = itertools.islice(pairs, 10)
        for a, b, m_a, m_b, verdict in top:
            try:
                verdict = matching_svc.compare(m_a, m_b, llm, refine=True)
            except Exception as exc:
                logger.warning("LLM refine failed %s vs %s: %s", a.id, b.id, exc)

    for a, b, m_a, m_b, verdict in pairs:
        existing = (
            db.query(Mapping)
            .filter(
                Mapping.material_id == a.id,
                Mapping.candidate_id == b.id,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            Mapping(
                material_id=a.id,
                candidate_id=b.id,
                match_type=verdict["match_type"],
                confidence_score=verdict["score"],
                evidence=verdict["evidence"],
                safety_flag=verdict["safety_flag"],
                review_status="pending",
            )
        )
        created += 1
    db.commit()
    logger.info("generated %d candidate mappings (%s mode)", created, llm.mode)
    return created


def approve_mapping(db: Session, mapping: Mapping, decision: str, comment: str,
                    performed_by: str, standardized_name: str = None,
                    national_code: str = None) -> Mapping:
    """Apply a reviewer decision to a candidate mapping."""
    from .codegen import build_code

    old = {
        "review_status": mapping.review_status,
        "match_type": mapping.match_type,
        "confidence": mapping.confidence_score,
    }

    if decision == "approve" or decision == "edit":
        target_a = mapping.material
        target_b = mapping.candidate
        base_attrs = {**(target_a.attributes or {}), **(target_b.attributes or {})}
        from ..models import CommonMaterial

        existing_codes = {
            cm.national_code for cm in db.query(CommonMaterial).all()
        }
        code = national_code or build_code(base_attrs.get("category", ""), base_attrs, existing_codes)
        name = standardized_name or fallback_name(mapping, base_attrs)

        cm = CommonMaterial(
            national_code=code,
            standardized_name=name,
            classification_code=base_attrs.get("category", ""),
            standard_attributes={
                k: v for k, v in base_attrs.items() if k not in ("extracted_at",)
            },
            approved_by=performed_by,
            is_active=True,
        )
        cm.approved_at = _utcnow()
        db.add(cm)
        db.flush()

        mapping.common_material_id = cm.id
        mapping.review_status = "approved"
        new_national = code
    elif decision == "reject":
        mapping.review_status = "rejected"
        new_national = None
    elif decision == "escalate":
        mapping.review_status = "escalated"
        new_national = None
    else:
        raise ValueError(f"unknown decision: {decision}")

    mapping.reviewer_comment = comment
    mapping.decided_by = performed_by
    mapping.decided_at = _utcnow()

    db.add(
        audit.log(
            db,
            action=f"mapping:{decision}",
            entity="mapping",
            entity_id=mapping.id,
            old=old,
            new={
                "review_status": mapping.review_status,
                "common_code": new_national,
                "comment": comment,
            },
            performed_by=performed_by,
        )
    )
    db.commit()
    return mapping


def fallback_name(mapping: Mapping, attrs: dict) -> str:
    n = attrs.get("material_type") or attrs.get("category") or "item"
    g = attrs.get("grade") or attrs.get("material_family") or ""
    s = attrs.get("size") or attrs.get("nominal_size") or ""
    return " ".join(x for x in [str(n), str(g), str(s)] if x).strip().title() or "Standardized item"