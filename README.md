# SIH 2026 · SIH26099 — National Unified Material Master Framework

**AI-Driven Standardization and Harmonization of Material Codes Across CPSEs**
Ministry of Petroleum & Natural Gas · Chennai Petroleum Corporation Limited

Different CPSEs buy the same industrial item but register it under different local material
codes, descriptions, units, abbreviations and classifications. This platform ingests those
legacy masters, normalizes them, extracts technical attributes with NLP, finds identical /
duplicate / near-duplicate / functionally-equivalent records with a weighted hybrid
similarity engine, and maps everything to a traceable **Common National Material Code (NMC)**
after a human approval workflow.

---

## Quick start (Docker)

```bash
docker compose up --build
```

Open:

- **Dashboard** http://localhost:5173
- **Backend API**  http://localhost:8000  (Swagger docs at `/docs`)
- **PostgreSQL**  localhost:5433 (user/pass/db = `nmc`)

The first startup waits for the database, creates tables and seeds ~46 records from
CPCL / NTPC / SAIL / ONGC / BHEL / CIL with the exact examples from the problem statement
(bolt trio `BLT-00123` / `FAST-8871` / `MEC-4458`, the `PN16` vs `PN25` safety near-miss,
and the `NMC-FASTENER-BOLT-SS304-M12-L50` code-generation example) plus procurement history.

> No API key? The app runs fully offline using the deterministic regex/rule engine
> (mode `mock`). Everything is demo-able without any cloud call.

---

## Enabling a live LLM (optional)

Create a `.env` next to `docker-compose.yml`:

```env
# Option A: any OpenAI-compatible endpoint (OpenAI, Groq, DeepSeek, Ollama, LM Studio…)
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
LLM_PROVIDER=openai

# Option B: Anthropic
# ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-sonnet-4-20250514
# LLM_PROVIDER=anthropic
```

The LLM is used for:
1. **NLP attribute extraction** (description → structured technical attributes, JSON).
2. **On-demand explainable comparisons** — the review UI and
   `POST /api/matching/compare` show LLM judgments and semantic similarity.

Bulk candidate generation always uses the fast local engine
(`LLM_REFINE_MATCHING_BULK=true` enables refined LLM judgments on the top pairs).

Matching weights are configurable (`MATCH_WEIGHTS_TEXT/ATTR/CATEGORY/UNIT/MFR`) — technical
attributes carry 0.45 weight by default so grade/size/pressure/voltage dominate over wording.

---

## What the system does (workflow)

```
Upload CPSE data → Clean & normalize → Extract technical attributes
→ Candidate matching (hybrid scoring S = Σ wᵢ·Sᵢ) → Human review
→ Create Common National Material Code → Save mapping + audit trail
```

### Score interpretation (per problem statement)
| Score | Meaning |
|-------|---------|
| ≥ 92% | Identical — fast approval path |
| 80–89% | Duplicate — engineer review |
| 50–79% | Possibly functionally equivalent — deeper review |
| < 50% | Different materials — no mapping |

**Safety guarantee:** records with conflicting safety-critical attributes
(pressure class, voltage, material grade, standard) are flagged and *never*
auto-merged — e.g. ball valve `PN16` vs `PN25` stays separate.

### NMC code format
`NMC-[CATEGORY]-[TYPE]-[MATERIAL]-[SIZE]-[KEY_SPEC]`
→ e.g. `NMC-FST-BOLT-SS304-M12-L50`. Generation templates are configurable per category
(backend/app/services/codegen.py).

---

## Repository layout

```
.
├── docker-compose.yml          # db + backend + frontend, one command
├── backend/
│   └── app/
│       ├── main.py             # FastAPI app, startup seeding
│       ├── models.py           # CPSE, Material, Procurement, CommonMaterial, Mapping, AuditLog
│       ├── llm/                # provider abstraction (openai/anthropic/mock)
│       └── services/
│           ├── normalization.py  # abbreviations, grade tokens, noise removal
│           ├── units.py          # unit canonicalisation + conversions (2 INCH → 50.8 mm)
│           ├── attributes.py     # regex attribute extraction fallback
│           ├── matching.py       # weighted hybrid engine + near-miss detection
│           ├── clustering.py     # union-find duplicate clusters
│           ├── codegen.py        # NMC generator
│           ├── savings.py        # procurement-savings estimation
│           └── workflow.py       # ingest → match → review → audit pipeline
├── frontend/
│   └── src/
│       ├── pages/Dashboard.jsx  # KPIs, charts, clusters, savings, activity
│       ├── pages/Upload.jsx     # CSV ingestion + NLP extractor preview
│       ├── pages/Materials.jsx  # material master with extracted attributes
│       ├── pages/Review.jsx     # human-in-the-loop approval queue
│       └── pages/Audit.jsx      # traceability log
└── data/sample_materials.csv    # import template
```

## API summary

| Endpoint | Purpose |
|---|---|
| `GET /api/system/info` | Current AI engine mode + weights |
| `POST /api/upload` | CSV/Excel material-master ingestion |
| `POST /api/materials/extract-preview` | Run attribute extraction on one description |
| `GET /api/materials?q=&category=&status=` | Material master search |
| `GET /api/matching/candidates` | Pending AI recommendations |
| `GET /api/matching/candidates/safety` | Safety near-miss queue |
| `POST /api/matching/compare` | Explainable pair comparison (LLM when enabled) |
| `GET /api/matching/clusters` | Duplicate clusters |
| `GET /api/review/queue` | Review queue |
| `POST /api/review/tasks/{id}` | approve / reject / escalate / edit |
| `GET /api/dashboard/stats · savings · activity · quality` | Analytics |
| `GET /api/audit` | Audit trail |

## Judge demo script (2 minutes)

1. **Dashboard** — total records, duplicate clusters, potential savings, data-quality
   completeness, category-wise duplicate bars.
2. **Review queue** — open a candidate pair, press *Evidence*: shows per-component scores
   (`S = Σ wᵢSᵢ`), shared and conflicting attributes. Highlight the **Safety tab**:
   `PN16` vs `PN25` ball valves flagged and *never* auto-merged.
3. **Approve** a bolt pair → the system issues `NMC-FST-BOLT-SS304-M12-L50`.
4. **Ingest** a fresh CSV and watch the pipeline automatically queue new candidates.
5. **Audit trail** — every recommendation and decision is timestamped and attributable.