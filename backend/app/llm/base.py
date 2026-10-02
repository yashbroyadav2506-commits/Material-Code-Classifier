"""Base contract for LLM providers."""


class BaseLLM:
    mode = "base"

    def available(self) -> bool:
        return False

    def extract_attributes(self, description: str) -> dict:
        raise NotImplementedError

    def semantic_similarity(self, text_a: str, attrs_a: dict, text_b: str, attrs_b: dict) -> float:
        raise NotImplementedError

    def match_judgment(self, a: dict, b: dict) -> dict:
        raise NotImplementedError


ATTR_SCHEMA_DOC = """{
  "material_type": "e.g. hex bolt, ball valve",
  "category": "FASTENER | VALVE | BEARING | CABLE | PIPE | FLANGE | GASKET | MOTOR | PUMP | ELECTRODE | METAL | FITTING | LUBRICANT | ELECTRICAL | INSTRUMENT | BELT | CHAIN | LIGHTING | CHEMICAL | PAINT | \"\"",
  "grade": "material grade e.g. SS304, CS, MS, brass",
  "material_family": "SS | CS | MS | DI | CI | CU | AL | PVC | XLPE | RUBBER | \"\"",
  "thread": "e.g. M12, M16*1.5",
  "size": "declared thread or dimension token",
  "nominal_size": "e.g. DN80, 2in, 50mm",
  "length_mm": "length in mm if stated as number",
  "pressure_class": "e.g. CL150, PN16, ANSI 300",
  "voltage": "e.g. 415V, 1.1KV",
  "power": "e.g. 5HP, 2.2KW",
  "standard": "e.g. ASTM A351, IS2062, DIN",
  "end_connection": "flanged | threaded | socket weld | butt weld | welded | \"\"",
  "manufacturer": "company name if mentioned",
  "part_number": "manufacturer part / catalog number if mentioned",
  "key_spec": "short distinctive spec token"
}"""

EXTRACT_PROMPT = (
    "You are a materials master data expert for Indian CPSEs.\n"
    "Extract structured technical attributes from the industrial material description.\n"
    "Return ONLY valid JSON matching exactly this schema (no markdown):\n" + ATTR_SCHEMA_DOC +
    "\n\nDescription: {description}"
)


def build_compare_prompt(a: dict, b: dict, weights: dict) -> str:
    return (
        "You are a materials master data reviewer for Indian central public sector enterprises.\n"
        "Two material records are given. Assess whether they refer to the same item "
        "(identical / duplicate / near-duplicate / functionally equivalent / different).\n"
        "Return ONLY valid JSON with keys: overall_similarity (0-100 number), "
        "match_type (one of identical|duplicate|near_duplicate|functionally_equivalent|different), "
        "shared_attributes (list of attribute names), conflicting_attributes (list of objects "
        "{attribute, value_a, value_b}), can_safely_merge (boolean, false if e.g. pressure/voltage/grade differs), "
        "reason (one sentence).\n\n"
        "RECORD A: description={a_desc!r}\nattributes={a_attrs}\n"
        "RECORD B: description={b_desc!r}\nattributes={b_attrs}\n"
        "Configured weights (text/attribute/category/unit/manufacturer): {weights}\n"
        "Never propose automatic merge when safety-critical attributes (pressure_class, voltage, grade, standard) differ."
    ).format(a_desc=a.get("desc", ""), a_attrs=a.get("attrs", {}),
             b_desc=b.get("desc", ""), b_attrs=b.get("attrs", {}),
             weights=weights)