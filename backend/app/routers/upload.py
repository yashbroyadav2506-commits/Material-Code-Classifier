import csv
import io
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm.provider import get_llm
from ..models import CPSE, Material, Procurement
from ..schemas import UploadSummary
from ..services import workflow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload", tags=["ingestion"])

EXPECTED_COLUMNS = [
    "cpse", "legacy_code", "description", "unit", "manufacturer",
    "part_number", "category", "year", "quantity", "unit_price",
]


@router.post("", response_model=UploadSummary)
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    raw = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))

    if not reader.fieldnames:
        return UploadSummary(inserted=0, skipped_duplicates=0, errors=["empty file"], total_records=0, llm_mode=get_llm().mode)

    cpses = {c.short_name: c for c in db.query(CPSE).all()}
    llm = get_llm()
    inserted = 0
    skipped = 0
    errors = []
    ids = []

    for row in reader:
        try:
            cpse_short = (row.get("cpse") or "").strip()
            if not cpse_short:
                errors.append("row missing cpse")
                continue
            if cpse_short not in cpses:
                cp = CPSE(name=cpse_short, short_name=cpse_short.upper()[:12], sector="Imported")
                db.add(cp)
                db.flush()
                cpses[cpse_short] = cp

            code = (row.get("legacy_code") or "").strip()
            desc = (row.get("description") or "").strip()
            if not code or not desc:
                errors.append(f"row missing legacy_code/description ({code!r})")
                continue

            dup = (
                db.query(Material)
                .filter(Material.cpse_id == cpses[cpse_short].id, Material.legacy_code == code)
                .first()
            )
            if dup:
                skipped += 1
                continue

            unit = (row.get("unit") or "").strip()
            cat = (row.get("category") or "").strip()
            mfr = (row.get("manufacturer") or "").strip()
            pn = (row.get("part_number") or "").strip()

            mat = Material(
                cpse_id=cpses[cpse_short].id,
                legacy_code=code,
                raw_description=desc,
                raw_unit=unit,
                category=cat,
                manufacturer=mfr,
                part_number=pn,
                source_file=file.filename or "upload",
                status="ingested",
            )
            db.add(mat)
            db.flush()
            ids.append(mat.id)
            inserted += 1

            year = _int(row.get("year"))
            qty = _float(row.get("quantity"))
            price = _float(row.get("unit_price"))
            if year and qty:
                db.add(
                    Procurement(
                        material_id=mat.id,
                        year=year,
                        quantity=qty,
                        unit_price=price or 0.0,
                        currency="INR",
                    )
                )
        except Exception as exc:  # per-row resilience, keep going without rollback
            errors.append(f"row error: {exc}")

    db.commit()

    llm_mode = llm.mode
    if ids:
        for mat in db.query(Material).filter(Material.id.in_(ids)).all():
            workflow.process_record(db, mat, llm)
        db.commit()
        workflow.run_matching_candidates(db, llm, limit_record_ids=ids)

    return UploadSummary(
        inserted=inserted,
        skipped_duplicates=skipped,
        errors=errors[:20],
        total_records=inserted + skipped,
        llm_mode=llm_mode,
    )


def _int(v):
    try:
        return int(float(str(v).replace(",", ""))) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None