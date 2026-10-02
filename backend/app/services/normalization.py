"""Cleaning and normalization.

Before any AI matching happens the raw ERP/CSV text is standardized:
- case folding and punctuation cleanup
- abbreviation expansion (SS -> Stainless Steel, 2 INCH -> 50.8 mm, ...)
- common spelling/typo correction
- uniform vocabulary for grades and material families
"""

import re

from .units import UNIT_CANON, canonical_unit, to_mm

# ---------------------------------------------------------------------------
# Abbreviation / synonym expansions applied to descriptions
# ---------------------------------------------------------------------------
WORD_EXPANSIONS = {
    "stainless steel": "stainless steel",
    "ss": "stainless steel",
    "s.s": "stainless steel",
    "ss304": "stainless steel 304",
    "ss-304": "stainless steel 304",
    "ss316": "stainless steel 316",
    "ss-316": "stainless steel 316",
    "ss316l": "stainless steel 316l",
    "ss410": "stainless steel 410",
    "carbon steel": "carbon steel",
    "c.s.": "carbon steel",
    "cs": "carbon steel",
    "mild steel": "mild steel",
    "m.s.": "mild steel",
    "ms": "mild steel",
    "gi": "galvanized iron",
    "g.i.": "galvanized iron",
    "galvanised iron": "galvanized iron",
    "galvanized steel": "galvanized iron",
    "pvc": "pvc",
    "xlpe": "xlpe",
    "hmdpe": "hmdpe",
    "pe": "polyethylene",
    "hdpe": "hdpe",
    "cu": "copper",
    "alu": "aluminium",
    "al": "aluminium",
    "alum": "aluminium",
    "brass": "brass",
    "bronze": "bronze",
    "gunmetal": "gunmetal",
    "cast iron": "cast iron",
    "ci": "cast iron",
    "ductile iron": "ductile iron",
    "di": "ductile iron",
    "hex": "hexagonal",
    "hexag": "hexagonal",
    "hexagon": "hexagonal",
    "flg": "flanged",
    "flg'd": "flanged",
    "sw": "socket weld",
    "bw": "butt weld",
    "galv": "galvanized",
    "galv.": "galvanized",
    "std": "standard",
    "mfr": "manufacturer",
    "mfg": "manufacturer",
    "meas": "measurement",
    "appx": "approximately",
    "approx": "approximately",
    "incl": "including",
    "w/": "with",
    "w/o": "without",
    "no.": "number",
    "nos.": "number",
    "volt": "volt",
    "volt.": "volt",
    "deg": "degree",
    "conn": "connection",
    "conn.": "connection",
}

# grade tokens -> canonical material grade
GRADE_TOKENS = {
    "ss304": "SS304",
    "ss-304": "SS304",
    "ss316": "SS316",
    "ss-316": "SS316",
    "ss316l": "SS316L",
    "ss316ti": "SS316Ti",
    "ss410": "SS410",
    "ss430": "SS430",
    "ss904l": "SS904L",
    "a312": "ASTM A312",
    "a351": "ASTM A351",
    "a240": "ASTM A240",
    "a106": "ASTM A106",
    "a105": "ASTM A105",
    "a53": "ASTM A53",
    "e7018": "E7018",
    "e6013": "E6013",
    "e7024": "E7024",
    "p265gh": "P265GH",
}

# material families for classification
MATERIAL_FAMILIES = {
    "stainless steel": "SS",
    "carbon steel": "CS",
    "mild steel": "MS",
    "galvanized iron": "MS",
    "ductile iron": "DI",
    "cast iron": "CI",
    "brass": "BRASS",
    "bronze": "BRONZE",
    "gunmetal": "GUNMETAL",
    "copper": "CU",
    "aluminium": "AL",
    "pvc": "PVC",
    "xlpe": "XLPE",
    "hdpe": "HDPE",
    "polyethylene": "PE",
    "rubber": "RUBBER",
    "nitrile": "NBR",
    "ptfe": "PTFE",
    "fiberglass": "FRP",
    "frp": "FRP",
}

NOISE_TOKENS = {
    "material", "item", "items", "for", "and", "as", "per", "with", "made",
    "make", "type", "category", "code", "description", "of", "the", "a", "an",
    "or", "&", "spec", "specs", "specification", "approx", "qty", "quantity",
    "required", "requirement", "please", "should", "etc", "etc.", "various",
    "other", "eg", "i.e.", "e.g.", "suitable", "complete", "set", "1 no", "1no",
}

UNIT_KEYWORD_HINTS = [
    "nos", "no", "pcs", "pc", "pieces", "piece", "set", "sets",
    "mm", "mtr", "meter", "metre", "cm", "km", "kg", "kgs", "gm", "g",
    "ton", "tonne", "mt", "litre", "liter", "ltr", "ml", "sqm",
    "cum", "kw", "kva", "hp", "watt", "volt", "kv", "amp", "bar", "degc",
]


def expand_units_in_text(text: str) -> str:
    """Normalise common unit spellings inside a description (2 INCH -> 2 inch)."""
    out = text
    unit_map = {
        "nos": "nos", "no": "nos", "pcs": "nos", "pc": "nos",
        "pieces": "nos", "set": "nos",
        "milli meter": "mm", "millimeter": "mm", "millimetre": "mm",
        "mtrs": "m", "meters": "m", "metres": "m", "metre": "m", "meter": "m",
        "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
        "tonnes": "t", "tons": "t", "tonne": "t",
        "litres": "l", "liters": "l",
        "sq. m": "sqm", "sqm": "sqm",
        "cu. m": "cum", "cum": "cum",
        "kva": "kva", "kilowatt": "kw",
        "horse power": "hp",
    }
    for src, dst in unit_map.items():
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)
    return out


def normalize_description(raw: str) -> str:
    """Full description normalization pipeline."""
    if not raw:
        return ""

    text = str(raw)
    # remove units like 1 no, 2 nos leading counts that are baggage
    text = re.sub(r"^\s*[0-9]+\s*(nos|no|pcs|pc)[s]?\b", " ", text, flags=re.IGNORECASE)
    # expand degree symbol
    text = text.replace("`", "'").replace(" inch ", ' " ').replace("inches", " inch")
    text = expand_units_in_text(text)

    # tokenise and expand abbreviations
    words = re.split(r"([\s\-,/()\[\]])", text)
    out = []
    for w in words:
        key = re.sub(r"[^a-zA-Z0-9.]", "", w).lower()
        wl = w.lower()
        # handle dotted abbreviations like s.s / c.s
        key2 = re.sub(r"[^a-zA-Z0-9]", "", wl)
        if key2 in WORD_EXPANSIONS:
            out.append(WORD_EXPANSIONS[key2])
        elif key in WORD_EXPANSIONS:
            out.append(WORD_EXPANSIONS[key])
        else:
            out.append(w)
    joined = "".join(out)
    joined = re.sub(r"\s+", " ", joined)

    # collapse " 304" attached grades that survived
    joined = re.sub(r"\bstainless\s+steel\s*(\d{3})", r"stainless steel \1", joined)
    joined = re.sub(r"\bstainless\s+steel\s+(\d{3})", r" ss\1 ", joined)

    # remove noise tokens
    tokens = joined.split()
    kept = [tok for tok in tokens if tok.lower().strip(" .") not in NOISE_TOKENS]
    result = " ".join(kept).strip()

    # collapse repeated spaces & trim delimiters
    result = re.sub(r"\s+", " ", result).strip("-/|,;: ")
    return result.lower() if result else ""


def canonical_grade(desc: str) -> str:
    """Find a canonical grade token in a description."""
    low = " " + re.sub(r"\s+", " ", desc.lower()) + " "
    for key, canon in sorted(GRADE_TOKENS.items(), key=lambda kv: -len(kv[0])):
        pat = re.escape(key)
        if re.search(rf"(?<![a-z0-9]){pat}(?![a-z0-9])", low):
            return canon
    if "stainless steel 316l" in low:
        return "SS316L"
    if "stainless steel 316" in low or "ss 316" in low:
        return "SS316"
    if "stainless steel 304" in low or "ss 304" in low:
        return "SS304"
    return ""


def material_family(grade: str, desc: str = "") -> str:
    """Map a grade or description to a material family code (SS/CS/MS/...)."""
    if grade:
        g = grade.upper()
        if g.startswith("SS"):
            return "SS"
        if g.startswith("CS"):
            return "CS"
        if g.startswith("MS"):
            return "MS"
    low = (desc or "").lower()
    for family_name, code in MATERIAL_FAMILIES.items():
        if family_name in low:
            return code
    return ""