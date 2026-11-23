"""
Thin wrapper around the Claude API.

The engine never depends on the model for arithmetic. The model is used for:
  * reading unstructured rate notices into a strict JSON schema (tool use)
  * writing explanations / memos from facts the engine has already computed

If ANTHROPIC_API_KEY is not set (or CAPAI_OFFLINE=1) every caller falls back to a
deterministic path, and the output is labelled with the method that produced it.
"""
from __future__ import annotations

import json
import os

DEFAULT_MODEL = os.environ.get("CAPAI_MODEL", "claude-sonnet-5-5")


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self._client = None
        if os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("CAPAI_OFFLINE") != "1":
            try:
                import anthropic

                self._client = anthropic.Anthropic()
            except Exception:  # pragma: no cover - SDK missing
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def extract(self, system: str, document: str, tool: dict) -> dict:
        """Force a single tool call and return its input (schema-validated by the API)."""
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": document}],
        )
        for block in msg.content:
            if block.type == "tool_use":
                return block.input
        raise RuntimeError("model did not return a tool call")

    def write(self, system: str, facts: dict, instruction: str, max_tokens: int = 1200) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": f"{instruction}\n\n<facts>\n{json.dumps(facts, indent=1, default=str)}\n</facts>"}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
