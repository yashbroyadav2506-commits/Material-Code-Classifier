from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Mapping
from ..schemas import ReviewDecisionIn
from ..services import workflow

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue")
def review_queue(db: Session = Depends(get_db)):
    from .matching import _mapping_payload

    statuses = ("pending", "escalated")
    rows = [
        _mapping_payload(m)
        for m in db.query(Mapping).filter(Mapping.review_status.in_(statuses)).order_by(Mapping.confidence_score.desc()).all()
    ]
    return {"count": len(rows), "results": rows}


@router.post("/tasks/{mapping_id}")
def decide(mapping_id: int, body: ReviewDecisionIn, db: Session = Depends(get_db)):
    m = db.get(Mapping, mapping_id)
    if not m:
        raise HTTPException(404, "mapping not found")
    result = workflow.approve_mapping(
        db,
        m,
        decision=body.decision,
        comment=body.comment,
        performed_by=body.decided_by,
        standardized_name=body.standardized_name,
        national_code=body.national_code,
    )
    from .matching import _mapping_payload

    return {"ok": True, "mapping": _mapping_payload(result)}