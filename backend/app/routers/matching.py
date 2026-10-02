from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm.provider import get_llm
from ..models import Mapping, Material
from ..services import matching as matching_svc
from ..services import workflow
from ..services.services_deps import material_dict

router = APIRouter(prefix="/matching", tags=["matching"])


@router.post("/run")
def run_matching(db: Session = Depends(get_db)):
    llm = get_llm()
    created = workflow.run_matching_candidates(db, llm)
    return {"created_candidates": created, "llm_mode": llm.mode}


@router.post("/compare")
def compare_pair(body: dict, db: Session = Depends(get_db)):
    """Explicit pairwise comparison between two records.

    `refine: true` runs the live LLM judgment + semantic similarity so judges
    can see explainable AI evidence on demand.
    """
    a = db.get(Material, body.get("material_a_id"))
    b = db.get(Material, body.get("material_b_id"))
    if not a or not b:
        from fastapi import HTTPException

        raise HTTPException(404, "material not found")
    refine = bool(body.get("refine", True))
    llm = get_llm()
    verdict = matching_svc.compare(material_dict(a), material_dict(b), llm, refine=refine)
    return {
        "record_a": material_for_cluster(a),
        "record_b": material_for_cluster(b),
        "verdict": verdict,
        "llm_mode": llm.mode,
        "refine": refine,
    }


@router.get("/candidates")
def list_candidates(
    status: str = "pending",
    min_score: float = 50.0,
    include_reviewed: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Mapping)
    if not include_reviewed:
        query = query.filter(Mapping.review_status == status)
    if min_score > 0:
        query = query.filter(Mapping.confidence_score >= min_score)
    rows = []
    for m in query.order_by(Mapping.confidence_score.desc()).limit(500).all():
        rows.append(_mapping_payload(m))
    return {"llm_mode": get_llm().mode, "results": rows, "count": len(rows)}


@router.get("/candidates/safety")
def safety_review_queue(db: Session = Depends(get_db)):
    rows = []
    for m in (
        db.query(Mapping)
        .filter(Mapping.safety_flag.is_(True), Mapping.review_status == "pending")
        .order_by(Mapping.confidence_score.desc())
        .all()
    ):
        rows.append(_mapping_payload(m))
    return {"results": rows, "count": len(rows)}


@router.get("/clusters")
def clusters(db: Session = Depends(get_db)):
    """Duplicate / equivalence clusters from approved + high-confidence pairs."""
    from ..services.clustering import cluster_materials

    pairs = []
    for m in db.query(Mapping).filter(Mapping.review_status.in_(["approved", "pending"])).all():
        if m.confidence_score >= 50:
            pairs.append((m.material_id, m.candidate_id, m.confidence_score))
    groups = cluster_materials(pairs, min_score=50.0)

    material_map = {mat.id: material_for_cluster(mat) for mat in db.query(Material).all()}
    out = []
    for g in sorted(groups, key=len, reverse=True):
        if len(g) < 2:
            continue
        out.append(
            {
                "size": len(g),
                "cpse_count": len({material_map.get(i, {}).get("cpse") for i in g}),
                "primary": next((material_map.get(i) for i in g), None),
                "members": [material_map.get(i) for i in g],
            }
        )
    return {"clusters": out, "count": len(out)}


def material_for_cluster(mat: Material) -> dict:
    d = material_dict(mat)
    d["attributes"] = (mat.attributes or {})
    d["raw_description"] = mat.raw_description
    return d


def _mapping_payload(m: Mapping) -> dict:
    a = material_for_cluster(m.material) if m.material else {}
    b = material_for_cluster(m.candidate) if m.candidate else {}
    return {
        "id": m.id,
        "record_a": a,
        "record_b": b,
        "score": m.confidence_score,
        "match_type": m.match_type,
        "safety_flag": bool(m.safety_flag),
        "review_status": m.review_status,
        "evidence": m.evidence or {},
        "comment": m.reviewer_comment or "",
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "common_material_id": m.common_material_id,
    }