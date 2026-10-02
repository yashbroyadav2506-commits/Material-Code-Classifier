"""NLP attribute extraction.

converts unstructured industrial descriptions into structured technical
attributes. Primary path is the LLM (see llm/provider.py); this module
implements the deterministic regex fallback so the demo works offline too.

Example: "VALVE BALL 2IN CL150 SS316 FLANGED ASTM A351"
 -> {material_type: ball valve, category: valve, size: 2in,
     pressure_class: CL150, grade: SS316, end_connection: flanged,
     standard: ASTM A351}
"""

import datetime
import re

from .normalization import GRADE_TOKENS, canonical_grade, material_family
from .units import canonical_unit

CATEGORY_PATTERNS = [
    (r"\b(hex(agonal)?\s*bolt|hex\s*bolt|bolt)\b", "FASTENER", "bolt"),
    (r"\b(screw|self( |-)?tapping\s*screw)\b", "FASTENER", "screw"),
    (r"\b(nut)\b", "FASTENER", "nut"),
    (r"\b(washer)\b", "FASTENER", "washer"),
    (r"\b(stud|stud\s*bolt)\b", "FASTENER", "stud"),
    (r"\banchor\b", "FASTENER", "anchor"),
    (r"\b(valve|ball\s*valve|gate\s*valve|globe\s*valve|check\s*valve|butterfly\s*valve|safety\s*valve)\b", "VALVE", "valve"),
    (r"\b(bearing|brg)\b", "BEARING", "bearing"),
    (r"\b(cable)\b", "CABLE", "cable"),
    (r"\b(wire)\b", "CABLE", "wire"),
    (r"\b(pipe|tube|tubing|hose)\b", "PIPE", "pipe"),
    (r"\b(flange)\b", "FLANGE", "flange"),
    (r"\b(gasket|washer\s*for\s*gasket)\b", "GASKET", "gasket"),
    (r"\b(motor)\b", "MOTOR", "motor"),
    (r"\b(pump)\b", "PUMP", "pump"),
    (r"\b(electrode|welding\s*rod)\b", "ELECTRODE", "electrode"),
    (r"\b(plate|sheet)\b", "METAL", "plate"),
    (r"\b(pipe\s*fitting|elbow|tee|reducer|coupling|coupler|nipple|union)\b", "FITTING", "fitting"),
    (r"\b(oil|lubricant|grease)\b", "LUBRICANT", "oil"),
    (r"\b(fuse|contactor|breaker|switch|starter|relay|transformer)\b", "ELECTRICAL", "switchgear"),
    (r"\b(gauge|transmitter|meter|instrument)\b", "INSTRUMENT", "instrument"),
    (r"\b(conveyor\s*belt|belt)\b", "BELT", "belt"),
    (r"\b(chain)\b", "CHAIN", "chain"),
    (r"\b(lamp|bulb|light|led)\b", "LIGHTING", "lighting"),
    (r"\b(chemical|acid|sulphuric\s*acid)\b", "CHEMICAL", "chemical"),
    (r"\b(paint|coating|thinner)\b", "PAINT", "paint"),
]

TYPE_KEYWORDS = {
    "ball valve": "valve",
    "gate valve": "valve",
    "globe valve": "valve",
    "check valve": "valve",
    "butterfly valve": "valve",
    "hex bolt": "fastener",
    "hexagonal bolt": "fastener",
    "screw": "fastener",
    "nut": "fastener",
    "washer": "fastener",
    "stud bolt": "fastener",
    "flange": "flange",
    "gasket": "gasket",
    "bearing": "bearing",
    "deep groove ball bearing": "bearing",
    "conveyor belt": "belt",
    "v belt": "belt",
}

PRESSURE_RE = re.compile(
    r"(?<![a-z0-9])(CL\s?\d{2,4}|CLASS\s?\d{3,4}|PN\s?\d{1,4}|#150|#300|1500\s*#|ANSI\s?\d{2,4})\b",
    re.IGNORECASE,
)

VOLTAGE_RE = re.compile(
    r"(?<![a-z0-9])(\d+(?:\.\d)?\s*K?V\b|\d+(?:\.\d)?\s*VOLT\b)",
    re.IGNORECASE,
)

POWER_RE = re.compile(r"(?<![a-z0-9])(\d+(?:\.\d)?\s*(?:HP|H\.P|KW|W))\b", re.IGNORECASE)

STANDARD_RE = re.compile(
    r"(?<![a-z0-9])(ASTM\s?[A-Z0-9-]+(?:\.\d+)?|IS\s?\d{3,6}(?:[-/]\d{4})?|BS\s?\d{3,6}|DIN\s?\d{2,6}|ISO\s?\d{4,5}|API\s?\d{2,3}|EN\s?[\d-]+|AISI\s?\d{3})",
    re.IGNORECASE,
)

END_CONNECTION_RE = re.compile(
    r"(?<![a-z0-9])(flanged|threaded|socket\s*weld|socket-weld|butt\s*weld|butt-weld|welded|screwed)\b",
    re.IGNORECASE,
)

IMPERIAL_SIZE = {"1/2": 0.5, '" inch': 25.4}


def _extract_nominal_size(desc_low: str, length_val: float | None) -> str:
    """Return a canonical nominal-size token for pipes/valves/gaskets."""
    m = re.search(r"\bDN\s?(\d{1,5})\b", desc_low, re.IGNORECASE)
    if m:
        return f"DN{m.group(1)}"
    m = re.search(r"\bNB\s?(\d{1,4})\b", desc_low, re.IGNORECASE)
    if m:
        return f"DN{m.group(1)}"
    m = re.search(r"(\d{1,3}(?:\.\d)?)\s*(?:inch|in\b)\b", desc_low)
    if m:
        mm = float(m.group(1)) * 25.4
        return f"{mm:g}mm"
    m = re.search(r"(\d{1,3}(?:\.\d)?)\s*mm\b", desc_low)
    if m:
        val = float(m.group(1))
        # a standalone mm value without context: treat as size only when NOT a length of a bolt
        return f"{val:g}mm" if val <= 1200 else ""
    return ""


def detect_category(desc: str) -> tuple[str, str]:
    """Return (category_code, material_type)."""
    low = desc.lower()
    for pat, cat, mtype in CATEGORY_PATTERNS:
        if re.search(pat, low, re.IGNORECASE):
            return cat, mtype
    return "", ""


def extract_attributes_regex(description: str) -> dict:
    """Deterministic attribute extraction used when no LLM is configured."""
    raw = description or ""
    desc_low = raw.lower()

    category, mtype = detect_category(raw)

    grade = canonical_grade(raw)
    family = material_family(grade, raw)

    size = ""
    length_mm = None
    thread = ""
    thread_m = re.search(r"(M\s?\d{1,2}(?:\.\d)?)", desc_low)
    if thread_m:
        thread = thread_m.group(1).replace(" ", "").upper()
    # bolt length
    len_m = re.search(r"\bM\s?\d{1,2}(?:\.\d)?\s*[xX]\s*(\d{1,4}(?:\.\d)?)\s*(mm)?\b", desc_low)
    if len_m:
        length_mm = float(len_m.group(1))
        if len_m.group(2):
            length_mm = to_mm_value(length_mm, "mm")
    else:
        len_m2 = re.search(r"[Ll]\s*[:=]\s*(\d{1,4}(?:\.\d)?)\s*(mm)?\b", desc_low)
        if len_m2:
            length_mm = float(len_m2.group(1))
            if len_m2.group(2):
                length_mm = to_mm_value(length_mm, "mm")
        else:
            len_m3 = re.search(r"\b(\d{1,4}(?:\.\d)?)\s*(mm)\s*long\b", desc_low)
            if len_m3:
                length_mm = to_mm_value(float(len_m3.group(1)), "mm")

    if thread:
        size = thread

    pr = PRESSURE_RE.search(raw)
    pressure = pr.group(1).replace(" ", "").upper() if pr else ""

    vr = VOLTAGE_RE.search(raw)
    voltage = vr.group(1).replace(" ", "").upper() if vr else ""

    pw = POWER_RE.search(raw)
    power = pw.group(1).replace(" ", "").upper() if pw else ""

    st = STANDARD_RE.search(raw)
    standard = st.group(1).replace(" ", "").upper() if st else ""

    ec = END_CONNECTION_RE.search(desc_low)
    end_conn = ec.group(0).replace("-", " ") if ec else ""

    # manufacturer / part number guesses
    manufacturer = ""
    pm = re.search(r"\b(?:make|mfr|manufacturer|brand|of)\s*[:\-]?\s*([A-Z][A-Za-z0-9 .]{2,30})", raw)
    if pm:
        cand = pm.group(1).strip().title()
        if len(cand.split()) <= 3:
            manufacturer = cand
    part_number = ""
    pn = re.search(r"\b(?:part\s*no|p/\?no|pno|ref\s*no|code)\b[:\s]*([A-Z0-9][A-Z0-9\-/]{2,20})", raw, re.IGNORECASE)
    if pn:
        part_number = pn.group(1)

    nominal_size = _extract_nominal_size(desc_low, length_mm)

    attrs = {
        "material_type": detect_material_type(raw, mtype),
        "category": category,
        "grade": grade,
        "material_family": family,
        "thread": thread,
        "size": size,
        "length_mm": length_mm,
        "nominal_size": nominal_size,
        "pressure_class": pressure,
        "voltage": voltage,
        "power": power,
        "standard": standard,
        "end_connection": end_conn,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "extracted_at": datetime.datetime.utcnow().isoformat(),
    }
    attrs["key_spec"] = derive_key_spec(attrs)
    return attrs


def to_mm_value(val: float, unit: str) -> float:
    from .units import to_mm

    return to_mm(val, unit)


def detect_material_type(raw: str, fallback: str) -> str:
    low = raw.lower()
    for key in sorted(TYPE_KEYWORDS, key=len, reverse=True):
        if key in low:
            return key
    return fallback


def derive_key_spec(d: dict) -> str:
    """Pick the 'KEY_SPEC' token used in the NMC code for a category."""
    parts = []
    if d.get("thread"):
        parts.append(d["thread"])
    if d.get("length_mm"):
        parts.append(f"L{int(d['length_mm'])}{'mm' if d['length_mm'] >= 100 else ''}")
    elif d.get("nominal_size"):
        parts.append(d["nominal_size"])
    if d.get("pressure_class"):
        parts.append(d["pressure_class"])
    if d.get("voltage"):
        parts.append(d["voltage"])
    if d.get("power"):
        parts.append(d["power"])
    cat = (d.get("category") or "").upper()
    if cat == "VALVE" and d.get("pressure_class"):
        parts.append(d["pressure_class"])
    return "-".join(parts) if parts else "GENERIC"