"""National Unified Material Master Framework — FastAPI backend.

Startup creates tables, seeds demo data, and exposes a REST API consumed by
the React dashboard. The AI pipeline (LLM or offline regex fallback) lives in
app/services and app/llm.
"""

import logging
import time

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (register tables)
from .config import settings
from .database import Base, engine, get_db
from .llm.provider import get_llm
from .routers import audit, dashboard, materials, matching, review, upload
from .seed_data import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nmc")

app = FastAPI(
    title="National Unified Material Master Framework (SIH26099)",
    version="1.0.0",
    description="AI-driven standardization and harmonization of material codes across CPSEs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api")
app.include_router(materials.router, prefix="/api")
app.include_router(matching.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(audit.router, prefix="/api")


@app.on_event("startup")
def startup():
    for attempt in range(30):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except Exception as exc:
            logger.warning("db not ready (%s), retrying…", exc)
            time.sleep(2)
    db: Session = next(get_db())
    try:
        result = seed(db)
        logger.info("seed: %s", result)
    finally:
        db.close()


@app.get("/")
def health(db: Session = Depends(get_db)):
    llm = get_llm()
    return {
        "service": "National Unified Material Master Framework",
        "status": "ok",
        "llm_mode": llm.mode,
        "llm_model": settings.llm_model if llm.mode != "mock" else "offline-regex",
        "message": (
            "Running with a live LLM. Set LLM_API_KEY/LLM_BASE_URL or ANTHROPIC_API_KEY "
            "to use it, otherwise the offline heuristic engine is used."
            if llm.mode == "mock"
            else "Live LLM provider active."
        ),
    }


@app.get("/api/system/info")
def system_info():
    llm = get_llm()
    return {
        "llm_mode": llm.mode,
        "llm_model": settings.llm_model if llm.mode != "mock" else "offline-regex",
        "weights": {
            "text": settings.match_weights_text,
            "attribute": settings.match_weights_attr,
            "category": settings.match_weights_category,
            "unit": settings.match_weights_unit,
            "manufacturer": settings.match_weights_mfr,
        },
        "weights_src": "configurable in backend/app/config.py or env",
    }