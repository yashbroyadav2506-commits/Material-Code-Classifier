from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm.provider import get_llm
from ..models import Material
from ..schemas import MaterialOut
from ..services.attributes import extract_attributes_regex
from ..services.normalization import normalize_description
from ..services.services_deps import ATTR_DEFAULTS, extract_with, material_dict

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=list[MaterialOut])
def list_materials(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    cpse: Optional[str] = Query(None),
    limit: int = Query(200),
    db: Session = Depends(get_db),
):
    query = db.query(Material)
    if q:
        query = query.filter(Material.raw_description.ilike(f"%{q}%"))
    if category:
        query = query.filter(Material.category == category.upper())
    if status:
        query = query.filter(Material.status == status)
    if cpse:
        from ..models import CPSE

        cps = db.query(CPSE).filter(CPSE.short_name.ilike(cpse)).first()
        if cps:
            query = query.filter(Material.cpse_id == cps.id)
        else:
            return []
    return query.order_by(Material.id).limit(limit).all()


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    from sqlalchemy import func

    rows = []
    for cat, cnt in db.query(Material.category, func.count(Material.id)).group_by(Material.category).all():
        if cat:
            rows.append({"category": cat, "count": cnt})
    return {"categories": rows}


@router.get("/{material_id}", response_model=MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_db)):
    mat = db.get(Material, material_id)
    if not mat:
        raise HTTPException(404, "material not found")
    return mat


@router.post("/extract-preview")
def extract_preview(body: dict):
    desc = body.get("description", "")
    llm = get_llm()
    result = {"description": desc, "normalized": normalize_description(desc)}
    if llm.mode != "mock":
        try:
            attrs = llm.extract_attributes(desc)
            if attrs and (attrs.get("material_type") or attrs.get("category")):
                result["attributes"] = {**ATTR_DEFAULTS, **attrs}
                result["method"] = f"llm:{llm.mode}"
                return result
        except Exception:
            pass
    result["attributes"] = extract_attributes_regex(desc)
    result["method"] = "regex"
    return result