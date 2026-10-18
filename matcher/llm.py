"""The only module that talks to an LLM (Google Gemini).

Everything else calls two functions, so changing model or vendor touches this file only:
- generate_text(system, prompt): free text, used to reword explanations.
- generate_json(system, parts, schema): structured output validated by Pydantic, used for CV
  extraction. `parts` can mix text and (bytes, mime_type) pairs, so scanned PDFs and photos
  of CVs go to Gemini directly.

Configuration (environment or Streamlit secrets): GEMINI_API_KEY, optional GEMINI_MODEL and
GEMINI_TEXT_MODEL.
"""
from __future__ import annotations

import os
from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)
Part = str | tuple[bytes, str]

EXTRACT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")  # light model, rarely busy       # accuracy matters
TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.5-flash-lite")  # cheap rewording


class LLMError(RuntimeError):
    pass


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def describe() -> str:
    return f"Gemini ({EXTRACT_MODEL} / {TEXT_MODEL})" if available() else "not configured"


def _client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def generate_text(system: str, prompt: str, max_tokens: int = 400) -> str:
    from google.genai import types
    if not available():
        raise LLMError("GEMINI_API_KEY is not set")
    resp = _client().models.generate_content(
        model=TEXT_MODEL, contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system, temperature=0.2,
                                           max_output_tokens=max_tokens))
    return (resp.text or "").strip()


def generate_json(system: str, parts: list[Part], schema: type[M]) -> M:
    """Ask for JSON matching `schema`, validate it, and retry once with the error fed back."""
    from google.genai import types
    if not available():
        raise LLMError("GEMINI_API_KEY is not set")
    contents = [p if isinstance(p, str) else types.Part.from_bytes(data=p[0], mime_type=p[1]) for p in parts]
    config = types.GenerateContentConfig(system_instruction=system, temperature=0,
                                         response_mime_type="application/json",
                                         response_json_schema=schema.model_json_schema())
    client = _client()
    for attempt in range(2):
        raw = client.models.generate_content(model=EXTRACT_MODEL, contents=contents, config=config).text
        try:
            return schema.model_validate_json(raw)
        except ValidationError as e:
            error = e
            contents = contents + [f"Your previous JSON was invalid: {e.errors()[:5]}. Return corrected JSON only."]
    raise LLMError(f"Model output did not match the schema: {error.errors()[:3]}")
