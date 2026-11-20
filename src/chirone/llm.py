"""Model backends.

LlamaCpp talks to a local `llama-server` and asks it to constrain decoding
with a JSON schema. OpenAICompat talks to any OpenAI-compatible API and is
used in the lab (teacher baselines, evaluation), never on the user's PC.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import httpx
import jsonschema


@dataclass
class Completion:
    data: dict
    raw: str
    seconds: float
    timings: dict = field(default_factory=dict)  # llama.cpp prompt/predict stats


class LLMError(RuntimeError):
    pass


class LlamaCpp:
    def __init__(self, base_url: str, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def complete_json(self, messages: list[dict], schema: dict, max_tokens: int = 64) -> Completion:
        body = {
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}},
            "cache_prompt": True,
            # Qwen3.x-style templates: no visible reasoning, we want ~20 tokens out.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        t0 = time.monotonic()
        r = self.client.post(f"{self.base_url}/v1/chat/completions", json=body)
        r.raise_for_status()
        j = r.json()
        raw = j["choices"][0]["message"]["content"]
        return Completion(_parse(raw, schema), raw, time.monotonic() - t0, j.get("timings", {}))


class OpenAICompat:
    """For teacher baselines in eval. Providers differ in structured-output
    support; we request json_schema and still validate locally."""

    def __init__(self, base_url: str, model: str, api_key: str, timeout: float = 120.0,
                 extra: dict | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        # provider-specific body fields, e.g. {"reasoning_effort": "none"} so a
        # Qwen3 teacher on Ollama answers without a long hidden reasoning pass
        self.extra = extra or {}
        self.client = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})

    def complete_json(self, messages: list[dict], schema: dict, max_tokens: int = 256) -> Completion:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "out", "schema": schema, "strict": False},
            },
            **self.extra,
        }
        t0 = time.monotonic()
        r = self.client.post(f"{self.base_url}/chat/completions", json=body)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        return Completion(_parse(raw, schema), raw, time.monotonic() - t0)

    def chat(self, messages: list[dict], max_tokens: int = 2048, temperature: float = 0.9) -> str:
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature, **self.extra}
        r = self.client.post(f"{self.base_url}/chat/completions", json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def _parse(raw: str, schema: dict) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
        jsonschema.validate(data, schema)
    except (json.JSONDecodeError, jsonschema.ValidationError) as e:
        raise LLMError(f"invalid model output {raw!r}: {e}") from e
    return data
