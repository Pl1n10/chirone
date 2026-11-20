"""JSON Schemas for the model's two outputs.

The same schema is used three ways: passed to llama.cpp to constrain
decoding (it compiles it to a grammar), used to validate outputs in Python,
and used to build training targets with the same key order.
"""
from __future__ import annotations

from .catalog import Catalog

CONFIDENCE = ["low", "medium", "high"]


def step1_schema(cat: Catalog) -> dict:
    return {
        "type": "object",
        "properties": {"category": {"enum": list(cat.categories)}},
        "required": ["category"],
        "additionalProperties": False,
    }


def _fix_variant(cat: Catalog, fix_id: str) -> dict:
    pb = cat.playbooks[fix_id]
    params = {
        "type": "object",
        "properties": {n: p.json_schema() for n, p in pb.params.items()},
        "required": list(pb.params),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "fix_id": {"const": fix_id},
            "params": params,
            "confidence": {"enum": CONFIDENCE},
        },
        "required": ["fix_id", "params", "confidence"],
        "additionalProperties": False,
    }


def step2_schema(cat: Catalog, category: str) -> dict:
    return {"anyOf": [_fix_variant(cat, f) for f in cat.fixes_for(category)]}


def step2_target(fix_id: str, params: dict, confidence: str = "high") -> dict:
    """Canonical training target: same key order the grammar enforces."""
    return {"fix_id": fix_id, "params": params, "confidence": confidence}
