"""Unit normalization and conversion helpers.

Maps the messy units seen in legacy ERP exports ("Nos.", "no", "Pcs",
"2 INCH", "lbs", "KVA") onto a small canonical vocabulary, and converts
imperial + common engineering units to metric where sensible.
"""

import re

# canonical unit -> synonyms (lowercased, punctuation stripped)
UNIT_SYNONYMS = {
    "nos": {"nos", "no", "nos.", "nos ", "pcs", "pcs.", "pcs ", "pieces", "piece", "number", "numbers", "num", "unit", "units", "u", "set", "sets"},
    "mm": {"mm", "millimeter", "millimetre", "millimeters", "millimetres", "mm."},
    "m": {"m", "meter", "metre", "meters", "metres"},
    "cm": {"cm", "centimeter", "centimetre", "centimeters"},
    "km": {"km", "kilometer", "kilometre"},
    "kg": {"kg", "kgs", "kilogram", "kilograms", "kilo", "kgs."},
    "g": {"gm", "g", "gram", "grams"},
    "t": {"mt", "ton", "tonne", "tonnes", "tons", "metric ton"},
    "l": {"l", "litre", "liter", "litres", "liters", "lt", "ltr", "ltrs"},
    "ml": {"ml", "millilitre", "milliliter"},
    "m2": {"sqm", "sq.m", "sqm", "square meter", "square metre", "m2", "sq. mtr"},
    "m3": {"cum", "m3", "cubic meter", "cubic metre", "cu.m"},
    "kw": {"kw", "kilowatt", "kilowatts", "kva"},
    "w": {"w", "watt", "watts"},
    "hp": {"hp", "horse power", "horsepower"},
    "v": {"v", "volt", "volts"},
    "kv": {"kv", "kilovolt", "kilovolts"},
    "amp": {"a", "amp", "amps", "ampere", "amperes"},
    "bar": {"bar", "barg", "bar(g)"},
    "degc": {"degc", "c", "celsius", "centigrade", "degree c"},
    "mtr": {"mtr", "meters running", "running meter", "rm", "r.m.", "mtrs"},
}

UNIT_CANON = {}
for canon, syns in UNIT_SYNONYMS.items():
    for s in syns:
        s_clean = re.sub(r"[^a-zA-Z0-9()]", "", s.lower())
        UNIT_CANON[s_clean] = canon

# also keep the canonical token itself identifiable
for canon in UNIT_SYNONYMS:
    UNIT_CANON.setdefault(canon, canon)


def _strip(text: str) -> str:
    if text is None:
        return ""
    return re.sub(r"[^a-zA-Z0-9()]", "", str(text).lower())


def canonical_unit(raw: str) -> str:
    """Return canonical unit for a raw unit string ('' if unknown)."""
    if not raw or not str(raw).strip():
        return ""
    key = _strip(raw)
    return UNIT_CANON.get(key, str(raw).strip().lower()[:30])


def is_length_unit(u: str) -> bool:
    return u in {"mm", "cm", "m", "mtr", "km"}


# imperial / length conversions -> mm
LENGTH_TO_MM = {
    "in": 25.4,
    "inch": 25.4,
    "inches": 25.4,
    '"': 25.4,
    "ft": 304.8,
    "foot": 304.8,
    "feet": 304.8,
}


def to_mm(value: float, unit: str) -> float:
    """Convert a length value to millimetres. Unknown units returned as-is."""
    u = _strip(unit)
    if u in UNIT_CANON and UNIT_CANON[u] == "mm":
        return value
    if u == "cm":
        return value * 10.0
    if u == "m":
        return value * 1000.0
    if u in LENGTH_TO_MM:
        return round(value * LENGTH_TO_MM[u], 3)
    return value