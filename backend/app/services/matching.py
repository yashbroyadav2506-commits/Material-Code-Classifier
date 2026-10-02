"""Hybrid matching and recommendation engine.

Score  S = w1*S_text + w2*S_attr + w3*S_category + w4*S_unit + w5*S_mfr

where weights are configurable per problem-statement guidance, technical
attributes weigh more than plain text, and safety-critical conflicts
(pressure, voltage, grade, standard) can never auto-merge records.
"""

from rapidfuzz import fuzz

from ..config import settings
from ..llm.provider import get_llm, heuristic_judgment

# keys that, if conflicting, must block automatic merging
CRITICAL_ATTRS = ("grade", "pressure_class", "voltage", "standard", "thread")
# keys compared for attribute-level similarity
ATTRIBUTE_KEYS = (
    "grade", "material_family", "thread", "nominal_size", "length_mm",
    "pressure_class", "voltage", "power", "standard", "end_connection",
)
# unit groups that can be considered compatible
UNIT_GROUPS = {
    "nos": {"nos", "pcs", "set"},
    "length": {"mm", "cm", "m", "mtr", "km"},
    "mass": {"kg", "g", "t"},
    "volume": {"l", "ml", "m3"},
    "power": {"kw", "w", "hp"},
    "voltage": {"v", "kv"},
}

W = None


def _weights():
    global W
    if W is None:
        W = {
            "text": settings.match_weights_text,
            "attr": settings.match_weights_attr,
            "category": settings.match_weights_category,
            "unit": settings.match_weights_unit,
            "mfr": settings.match_weights_mfr,
        }
    return W


def _components(m_a: dict, m_b: dict) -> dict:
    """Per-component similarity scores (0-100) between two material dicts.

    Each material dict has keys: desc (normalized_description), attrs (dict),
    category, unit (normalized_unit), manufacturer.
    """
    w = _weights()
    da = (m_a.get("desc") or "").lower()
    db = (m_b.get("desc") or "").lower()

    # 1. text similarity (token sort ratio handles word-order variants)
    s_text = float(fuzz.token_set_ratio(da, db))

    # 2. attribute similarity with critical-attribute weighting
    attrs_a, attrs_b = m_a.get("attrs") or {}, m_b.get("attrs") or {}
    s_attr, weights_used = 0.0, 0.0
    conflicts, shared = [], []
    for key in ATTRIBUTE_KEYS:
        va = _norm_val(attrs_a.get(key))
        vb = _norm_val(attrs_b.get(key))
        if not va and not vb:
            continue
        crit = 2.5 if key in CRITICAL_ATTRS else 1.0
        if va and vb and _attr_equal(key, va, vb):
            s_attr += 100 * crit
            shared.append(key)
        else:
            # one missing -> 50, both present & different -> 0
            s_attr += (50 * crit if (not va or not vb) else 0)
            if va and vb:
                conflicts.append({"attribute": key, "value_a": va, "value_b": vb})
        weights_used += crit
    s_attr = (s_attr / weights_used) if weights_used else 50.0

    # 3. category consistency
    ca = (m_a.get("category") or "").upper()
    cb = (m_b.get("category") or "").upper()
    if not ca or not cb:
        s_cat = 50.0
    elif ca == cb:
        s_cat = 100.0
    else:
        s_cat = 20.0

    # 4. unit compatibility
    ua = _unit_group(name_of(m_a))
    ub = _unit_group(name_of(m_b))
    if not ua or not ub:
        s_unit = 50.0
    else:
        s_unit = 100.0 if ua == ub else 0.0
    if not ua and not ub:
        s_unit = 100.0

    # 5. manufacturer / part-number
    ma = flatten_mfr_or_pn(m_a)
    mb = flatten_mfr_or_pn(m_b)
    if ma and mb:
        s_mfr = float(fuzz.token_set_ratio(ma, mb))
        if s_mfr >= 90:
            s_mfr = 100.0
    elif not ma and not mb:
        s_mfr = 50.0
    else:
        s_mfr = 30.0

    score = (
        w["text"] * s_text
        + w["attr"] * s_attr
        + w["category"] * s_cat
        + w["unit"] * s_unit
        + w["mfr"] * s_mfr
    )
    return {
        "score": round(score, 2),
        "text": round(s_text, 2),
        "attribute": round(s_attr, 2),
        "category": round(s_cat, 2),
        "unit": round(s_unit, 2),
        "manufacturer": round(s_mfr, 2),
        "shared_attributes": shared,
        "conflicting_attributes": conflicts,
    }


def _norm_val(v):
    if v is None:
        return ""
    s = str(v).strip()
    return s.upper().replace(" ", "").replace("-", "")


def _attr_equal(key: str, va, vb):
    a = _norm_val(va)
    b = _norm_val(vb)
    if key in ("length_mm",):
        try:
            return abs(float(va) - float(vb)) < 1.0
        except (TypeError, ValueError):
            return a == b
    if key == "thread":
        # M12 vs M12 X 50 - treat thread part equal
        ta = a.split("X")[0] if "X" in a else a
        tb = b.split("X")[0] if "X" in b else b
        return ta == tb
    if key == "nominal_size":
        return a == b or (a and b and (a.rstrip("MM") == b.rstrip("MM")))
    return a == b


def name_of(m: dict) -> str:
    return (m.get("unit") or "")


def _unit_group(unit: str) -> str:
    u = (unit or "").lower()
    for group, members in UNIT_GROUPS.items():
        if u in members or (u and any(u.startswith(x) for x in members if len(x) > 1)):
            return group
    return ""


def flat_map_attrs(attrs_a, attrs_b):
    shared = []
    conflicts = []
    for key in ATTRIBUTE_KEYS:
        va = _norm_val(attrs_a.get(key))
        vb = _norm_val(attrs_b.get(key))
        if not va and not vb:
            continue
        if va and vb and _attr_equal(key, va, vb):
            shared.append(key)
        elif va or vb:
            conflicts.append({"attribute": key, "value_a": attrs_a.get(key), "value_b": attrs_b.get(key)})
    return shared, conflicts


def flatten_mfr_or_pn(m: dict) -> str:
    mfr = (m.get("manufacturer") or "").strip()
    pn = (m.get("part_number") or "").strip()
    return f"{mfr} {pn}".strip()


def classify(score: float, safety_flag: bool) -> str:
    if safety_flag:
        return "near_duplicate"
    if score >= 92:
        return "identical"
    if score >= 80:
        return "duplicate"
    if score >= 50:
        return "functionally_equivalent"
    return "different"


def compare(m_a: dict, m_b: dict, llm=None, refine: bool = False) -> dict:
    """Full comparison of two material dicts; returns evidence + verdict.

    `refine=True` additionally asks a configured LLM for a judgment and a
    semantic similarity reading. Bulk candidate generation runs with
    refine=False (fast, offline, deterministic).
    """
    llm = llm or get_llm()
    comp = _components(m_a, m_b)

    shared, conflicts = flat_map_attrs(m_a.get("attrs") or {}, m_b.get("attrs") or {})
    critical_conflicts = [c for c in conflicts if c["attribute"] in CRITICAL_ATTRS]
    safety_flag = bool(critical_conflicts)

    # try LLM refinement only when configured and explicitly requested
    judgment = None
    semantic = None
    if refine and llm.mode != "mock":
        try:
            judgment = llm.match_judgment(m_a, m_b)
            semantic = llm.semantic_similarity(
                m_a.get("desc", ""), m_a.get("attrs") or {},
                m_b.get("desc", ""), m_b.get("attrs") or {},
            )
        except Exception:
            judgment = None

    score = comp["score"]
    if semantic is not None:
        # blend LLM semantic reading into the text component
        w_text = _weights()["text"]
        score = score + w_text * (semantic - comp["text"])
        comp["text"] = round(semantic, 2)
        comp["score"] = round(max(0.0, min(100.0, score)), 2)

    if judgment and judgment.get("can_safely_merge") is False:
        safety_flag = True

    match_type = classify(comp["score"], safety_flag)
    if judgment and judgment.get("match_type"):
        match_type = judgment["match_type"]
        if safety_flag and match_type not in ("near_duplicate", "different"):
            match_type = "near_duplicate"

    evidence = {
        "components": comp,
        "shared_attributes": shared or comp.get("shared_attributes", []),
        "conflicting_attributes": conflicts or comp.get("conflicting_attributes", []),
        "safety_flag": safety_flag,
        "llm_judgment": judgment,
    }
    return {
        "score": round(min(100.0, max(0.0, comp["score"])), 2),
        "match_type": match_type,
        "safety_flag": safety_flag,
        "evidence": evidence,
    }