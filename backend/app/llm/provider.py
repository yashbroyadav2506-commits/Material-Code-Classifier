"""LLM provider resolution: OpenAI-compatible, Anthropic, or offline mock.

Works with any OpenAI-compatible endpoint (OpenAI, Groq, DeepSeek, Ollama,
local llama.cpp servers) by setting LLM_BASE_URL + LLM_API_KEY + LLM_MODEL.
"""

import json
import logging
import os
import re

from ..config import settings
from .base import ATTR_SCHEMA_DOC, EXTRACT_PROMPT, build_compare_prompt
from .mock import MockLLM

logger = logging.getLogger(__name__)


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    # try to find first { ... } block
    try:
        start = text.index("{")
        end = text.rindex("}")
        return json.loads(text[start : end + 1])
    except Exception:
        return None


class OpenAICompatible:
    mode = "openai"

    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
        self.model = settings.llm_model

    def available(self) -> bool:
        return bool(settings.llm_api_key)

    def _chat_json(self, prompt: str) -> dict | None:
        kwargs = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        try:
            kwargs["response_format"] = {"type": "json_object"}
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # some providers reject response_format
            logger.info("response_format rejected (%s); retrying without it", exc)
            kwargs.pop("response_format", None)
            resp = self.client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        return _parse_json(content)

    def extract_attributes(self, description: str) -> dict:
        out = self._chat_json(EXTRACT_PROMPT.format(description=description))
        return out or {}

    def semantic_similarity(self, text_a, attrs_a, text_b, attrs_b) -> float | None:
        prompt = (
            "Rate how similar these two industrial material records are on a 0-100 scale "
            "considering both wording and technical specifications. Only integer answer, no prose.\n"
            f"A: {text_a}\nA attrs: {attrs_a}\nB: {text_b}\nB attrs: {attrs_b}\n"
        )
        try:
            content = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            ).choices[0].message.content or ""
            val = float(re.search(r"\d{1,3}", content).group())
            return max(0.0, min(100.0, val))
        except Exception as exc:
            logger.warning("semantic_similarity failed: %s", exc)
            return None

    def match_judgment(self, a: dict, b: dict) -> dict:
        prompt = build_compare_prompt(a, b, {
            "text": settings.match_weights_text,
            "attribute": settings.match_weights_attr,
            "category": settings.match_weights_category,
            "unit": settings.match_weights_unit,
            "manufacturer": settings.match_weights_mfr,
        })
        out = self._chat_json(prompt) or {}
        if not out.get("match_type"):
            out = heuristic_judgment(a, b)
        return out


class AnthropicProvider:
    mode = "anthropic"

    def __init__(self):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    def available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def _chat_json(self, prompt: str) -> dict | None:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        content = resp.content[0].text
        return _parse_json(content)

    def extract_attributes(self, description: str) -> dict:
        out = self._chat_json(EXTRACT_PROMPT.format(description=description))
        return out or {}

    def semantic_similarity(self, text_a, attrs_a, text_b, attrs_b) -> float | None:
        prompt = (
            "Rate how similar these two industrial material records are on a 0-100 scale. "
            "Only integer answer.\n"
            f"A: {text_a}\nA attrs: {attrs_a}\nB: {text_b}\nB attrs: {attrs_b}\n"
        )
        try:
            content = self._chat_json(prompt)
            if isinstance(content, dict):
                content = str(content)
            val = float(re.search(r"\d{1,3}", str(content)).group())
            return max(0.0, min(100.0, val))
        except Exception as exc:
            logger.warning("semantic_similarity failed: %s", exc)
            return None

    def match_judgment(self, a: dict, b: dict) -> dict:
        out = self._chat_json(build_compare_prompt(a, b, {
            "text": settings.match_weights_text,
            "attribute": settings.match_weights_attr,
            "category": settings.match_weights_category,
            "unit": settings.match_weights_unit,
            "manufacturer": settings.match_weights_mfr,
        })) or {}
        if not out.get("match_type"):
            out = heuristic_judgment(a, b)
        return out


def heuristic_judgment(a: dict, b: dict) -> dict:
    """Deterministic fallback judgment used by the engine when LLM absent/fails."""
    import rapidfuzz.fuzz as fuzz

    ta = (a.get("desc") or "").lower()
    tb = (b.get("desc") or "").lower()
    text_sim = fuzz.token_set_ratio(ta, tb)
    aa, bb = a.get("attrs") or {}, b.get("attrs") or {}
    shared = []
    conflicts = []
    safety_block = False
    for key in ("grade", "pressure_class", "voltage", "standard", "thread"):
        va = str(aa.get(key) or "").strip()
        vb = str(bb.get(key) or "").strip()
        if not va and not vb:
            continue
        if va and vb and va.upper() == vb.upper():
            shared.append(key)
        elif va or vb:
            conflicts.append({"attribute": key, "value_a": va, "value_b": vb})
            if key in ("grade", "pressure_class", "voltage"):
                safety_block = True

    if not conflicts and text_sim >= 90:
        mtype, can_merge = "duplicate", True
    elif not conflicts and text_sim >= 75:
        mtype, can_merge = "near_duplicate", True
    elif conflicts and not safety_block:
        mtype, can_merge = "functionally_equivalent", True
    elif safety_block:
        mtype, can_merge = "near_duplicate", False
    else:
        mtype, can_merge = "different", False

    score = float(text_sim)
    if conflicts:
        score = max(30.0, score - 15.0)
    return {
        "overall_similarity": round(score, 2),
        "match_type": mtype,
        "shared_attributes": shared,
        "conflicting_attributes": conflicts,
        "can_safely_merge": can_merge,
        "reason": f"text similarity {text_sim:.0f}%, {len(conflicts)} conflicting attribute(s)",
    }


def get_llm():
    """Return a working provider based on configuration."""
    mode = settings.llm_provider
    if mode == "mock":
        return MockLLM()
    if mode == "anthropic":
        return AnthropicProvider() if AnthropicProvider().available() else MockLLM()
    if mode == "openai":
        return OpenAICompatible() if OpenAICompatible().available() else MockLLM()
    # auto
    if settings.anthropic_api_key:
        return AnthropicProvider()
    if settings.llm_api_key:
        return OpenAICompatible()
    return MockLLM()