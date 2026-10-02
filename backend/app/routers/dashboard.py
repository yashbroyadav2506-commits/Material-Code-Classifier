from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, CommonMaterial, CPSE, Mapping, Material, Procurement
from ..services.clustering import cluster_materials
from ..services.savings import compute_savings, total_savings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    total_records = db.query(func.count(Material.id)).scalar()
    cpse_count = db.query(func.count(CPSE.id)).scalar()

    mappings = db.query(Mapping).all()
    pairs = [(m.material_id, m.candidate_id, m.confidence_score) for m in mappings if m.confidence_score >= 50]
    clusters = cluster_materials(pairs, min_score=50.0)
    multi_clusters = [c for c in clusters if len(c) >= 2]

    approved = db.query(func.count(Mapping.id)).filter(Mapping.review_status == "approved").scalar() or 0
    pending = db.query(func.count(Mapping.id)).filter(Mapping.review_status == "pending").scalar() or 0
    near_miss = db.query(func.count(Mapping.id)).filter(Mapping.safety_flag.is_(True)).scalar() or 0
    national_codes = db.query(func.count(CommonMaterial.id)).scalar() or 0

    material_map = {m.id: _cluster_material(m) for m in db.query(Material).all()}
    procurement_map = {}
    for p in db.query(Procurement).all():
        procurement_map.setdefault(p.material_id, []).append(
            {"quantity": p.quantity or 0.0, "unit_price": p.unit_price or 0.0}
        )
    savings_rows = compute_savings(multi_clusters, material_map, procurement_map)

    quality = data_quality(db)

    cat_rows = []
    for cat, cnt in db.query(Material.category, func.count(Material.id)).group_by(Material.category).all():
        if cat:
            dup = 0
            for m in db.query(Material.id).filter(Material.category == cat).all():
                dup += len(
                    db.query(Mapping).filter(Mapping.material_id == m[0]).all()
                )
            cat_rows.append({"category": cat, "records": cnt, "mapping_candidates": dup})

    return {
        "total_records": total_records,
        "cpse_count": cpse_count,
        "duplicate_clusters": len(multi_clusters),
        "approved_mappings": approved,
        "pending_reviews": pending,
        "national_codes": national_codes,
        "near_miss_count": near_miss,
        "potential_savings": total_savings(savings_rows),
        "data_quality": quality,
        "category_duplicates": cat_rows,
    }


@router.get("/quality")
def data_quality(db: Session = Depends(get_db)):
    total = db.query(func.count(Material.id)).scalar() or 0
    if not total:
        return {"completeness": 0.0, "records": 0}
    no_cat = db.query(func.count(Material.id)).filter(Material.category == "").scalar() or 0
    no_unit = db.query(func.count(Material.id)).filter(Material.normalized_unit == "").scalar() or 0
    no_attrs = db.query(func.count(Material.id)).filter(Material.extraction_method == "none").scalar() or 0
    completeness = round(100 * (1 - (no_cat + no_unit + no_attrs) / (3 * total)), 1)
    return {
        "records": total,
        "completeness": completeness,
        "no_category": no_cat,
        "no_unit": no_unit,
        "no_attributes": no_attrs,
    }


@router.get("/savings")
def savings(db: Session = Depends(get_db)):
    mappings = db.query(Mapping).all()
    pairs = [(m.material_id, m.candidate_id, m.confidence_score) for m in mappings if m.confidence_score >= 50]
    clusters = cluster_materials(pairs, min_score=50.0)
    material_map = {m.id: _cluster_material(m) for m in db.query(Material).all()}
    procurement_map = {}
    for p in db.query(Procurement).all():
        procurement_map.setdefault(p.material_id, []).append(
            {"quantity": p.quantity or 0.0, "unit_price": p.unit_price or 0.0}
        )
    rows = compute_savings(clusters, material_map, procurement_map)
    return {"rows": rows, "total": total_savings(rows)}


@router.get("/activity")
def activity(db: Session = Depends(get_db)):
    rows = []
    for a in db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50).all():
        rows.append(
            {
                "id": a.id,
                "action": a.action,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "performed_by": a.performed_by,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "new_value": a.new_value or {},
            }
        )
    return {"activity": rows}


def _cluster_material(mat: Material) -> dict:
    from ..services.services_deps import material_dict

    d = material_dict(mat)
    d["national_code"] = ""
    return d