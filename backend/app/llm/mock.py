"""Heuristic fallback used when no LLM API key is configured.

Debugging / judging works fully offline: attribute extraction is done by
deterministic regex rules (services/attributes.py) and text similarity by
rapidfuzz token-set ratio, so the whole demo runs with zero cloud calls.
"""

from ..services import attributes as attr_mod
from .base import BaseLLM


class MockLLM(BaseLLM):
    mode = "mock"

    def available(self) -> bool:
        return True

    def extract_attributes(self, description: str) -> dict:
        return attr_mod.extract_attributes_regex(description)

    def semantic_similarity(self, text_a: str, attrs_a: dict, text_b: str, attrs_b: dict) -> float:
        from rapidfuzz import fuzz

        base = fuzz.token_set_ratio(text_a or "", text_b or "")
        return float(base)

    def match_judgment(self, a: dict, b: dict) -> dict:
        """Consensus judgment (used only as a fallback inside the engine)."""
        from .provider import heuristic_judgment

        return heuristic_judgment(a, b)