"""Common National Material Code generator.

Format (configurable per category):
    NMC-[CATEGORY]-[TYPE]-[MATERIAL]-[SIZE]-[KEY_SPEC]

Example: NMC-FASTENER-BOLT-SS304-M12-L50
"""

import re

TEMPLATES = {
    "FASTENER": ["TYPE", "MATERIAL", "THREAD", "LENGTH"],
    "VALVE": ["TYPE", "MATERIAL", "SIZE", "PRESSURE"],
    "BEARING": ["TYPE", "MODEL", "MANUFACTURER"],
    "CABLE": ["TYPE", "MATERIAL", "SIZE", "VOLTAGE"],
    "PIPE": ["TYPE", "MATERIAL", "SIZE"],
    "FLANGE": ["TYPE", "MATERIAL", "SIZE", "PRESSURE"],
    "GASKET": ["TYPE", "MATERIAL", "SIZE", "PRESSURE"],
    "MOTOR": ["TYPE", "POWER", "VOLTAGE"],
    "PUMP": ["TYPE", "POWER", "SIZE"],
    "ELECTRODE": ["TYPE", "GRADE", "SIZE"],
    "METAL": ["TYPE", "GRADE", "SIZE"],
    "FITTING": ["TYPE", "MATERIAL", "SIZE"],
    "LUBRICANT": ["TYPE", "GRADE", "SIZE"],
    "ELECTRICAL": ["TYPE", "SIZE", "VOLTAGE"],
    "INSTRUMENT": ["TYPE", "SIZE", "GRADE"],
    "BELT": ["TYPE", "SIZE"],
    "CHAIN": ["TYPE", "SIZE"],
    "LIGHTING": ["TYPE", "POWER"],
    "CHEMICAL": ["TYPE", "GRADE"],
    "PAINT": ["TYPE", "SIZE"],
}

CATEGORY_SHORT = {
    "FASTENER": "FST",
    "VALVE": "VAL",
    "BEARING": "BRG",
    "CABLE": "CBL",
    "PIPE": "PIP",
    "FLANGE": "FLG",
    "GASKET": "GSK",
    "MOTOR": "MTR",
    "PUMP": "PMP",
    "ELECTRODE": "ELD",
    "METAL": "MET",
    "FITTING": "FTG",
    "LUBRICANT": "LUB",
    "ELECTRICAL": "ELC",
    "INSTRUMENT": "INS",
    "BELT": "BLT",
    "CHAIN": "CHN",
    "LIGHTING": "LGT",
    "CHEMICAL": "CHM",
    "PAINT": "PNT",
}


def _slug(value) -> str:
    s = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return s[:12]


def build_code(category: str, attrs: dict, existing_codes: set) -> str:
    """Create an NMC code from extracted attributes; dedupe against existing."""
    cat = (category or "").upper()
    short_cat = CATEGORY_SHORT.get(cat, "GEN")

    fields = TEMPLATES.get(cat, ["TYPE"])
    tokens = [short_cat]
    for field in fields:
        val = _attr_value(field, attrs)
        if val:
            tokens.append(val)
    base = "NMC-" + "-".join(tokens[:8])

    if base not in existing_codes:
        return base
    n = 2
    while f"{base}-{n:02d}" in existing_codes:
        n += 1
    return f"{base}-{n:02d}"


def _attr_value(field: str, attrs: dict) -> str:
    if not attrs:
        return ""
    if field == "TYPE":
        return _slug(attrs.get("material_type") or "")
    if field == "MATERIAL":
        return _material_token(attrs)
    if field == "GRADE":
        return _slug(attrs.get("grade") or attrs.get("material_family") or "")
    if field == "THREAD":
        return _slug(attrs.get("thread") or "")
    if field in ("SIZE",):
        return _slug(attrs.get("nominal_size") or attrs.get("size") or "")
    if field == "LENGTH":
        lv = attrs.get("length_mm")
        if lv:
            return _slug(f"L{int(lv)}")
        return _slug(attrs.get("key_spec") or "")
    if field == "PRESSURE":
        return _slug(attrs.get("pressure_class") or "")
    if field == "VOLTAGE":
        return _slug(attrs.get("voltage") or "")
    if field == "POWER":
        return _slug(attrs.get("power") or "")
    if field == "MANUFACTURER":
        return _slug((attrs.get("manufacturer") or "")[:4])
    if field == "MODEL":
        return _slug(attrs.get("part_number") or "")
    return ""


def _material_token(attrs: dict) -> str:
    fam = (attrs.get("material_family") or "").upper()
    grade = (attrs.get("grade") or "").upper().replace(" ", "")
    if grade.startswith("SS") and len(grade) >= 5:
        return grade
    if grade:
        return grade
    if fam:
        return fam
    return "GEN"