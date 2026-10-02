"""Helpers shared between workflow, matching and savings services."""

import logging

logger = logging.getLogger(__name__)

# default attribute skeleton — every material carries at least these keys
ATTR_DEFAULTS = {
    "material_type": "",
    "category": "",
    "grade": "",
    "material_family": "",
    "thread": "",
    "size": "",
    "nominal_size": "",
    "length_mm": None,
    "pressure_class": "",
    "voltage": "",
    "power": "",
    "standard": "",
    "end_connection": "",
    "manufacturer": "",
    "part_number": "",
    "unit": "",
    "key_spec": "",
}


def extract_with(material, llm):
    """Extract attributes preferring the LLM, falling back to regex rules."""
    try:
        attrs = llm.extract_attributes(material.raw_description)
        if not isinstance(attrs, dict) or not attrs:
            attrs = {}
        if not attrs.get("material_type") and not attrs.get("category"):
            # LLM came back empty/garbage -> use regex
            from .attributes import extract_attributes_regex

            return extract_attributes_regex(material.raw_description), "regex"
        merged = dict(ATTR_DEFAULTS)
        merged.update({k: (v if v is not None else "") for k, v in attrs.items()})
        method = f"llm:{llm.mode}"
        return merged, method
    except Exception as exc:
        logger.warning("LLM extraction failed (%s); using regex", exc)
        from .attributes import extract_attributes_regex

        return extract_attributes_regex(material.raw_description), "regex"


def material_dict(material) -> dict:
    """Render a Material ORM row into the shape the matching engine expects."""
    attrs = dict(material.attributes or {})
    base = dict(ATTR_DEFAULTS)
    base.update({k: (v if v is not None else "") for k, v in attrs.items()})
    return {
        "id": material.id,
        "legacy_code": material.legacy_code,
        "cpse": material.cpse.short_name if material.cpse else "?",
        "desc": material.normalized_description or material.raw_description,
        "raw_desc": material.raw_description,
        "attrs": base,
        "category": base.get("category") or material.category or "",
        "unit": material.normalized_unit or base.get("unit") or "",
        "manufacturer": base.get("manufacturer") or material.manufacturer or "",
        "part_number": base.get("part_number") or material.part_number or "",
    }