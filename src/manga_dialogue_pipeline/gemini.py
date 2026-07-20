"""Gemini structured-output adapter used by the public pipeline."""

from __future__ import annotations

import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class StructuredResult(Generic[T]):
    value: T
    model: str
    latency_sec: float
    usage: dict


class GeminiEngine:
    def __init__(self, model: str | None = None) -> None:
        from google import genai

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self.model = model or os.environ.get("GEMINI_MODEL")
        if not self.model:
            raise RuntimeError("Set GEMINI_MODEL in .env or pass --model.")
        self.client = genai.Client(api_key=api_key)

    def generate(
        self,
        *,
        image_path: Path,
        prompt: str,
        response_model: type[T],
        temperature: float = 0.0,
    ) -> StructuredResult[T]:
        from google.genai import types

        mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
        image_bytes = image_path.read_bytes()
        config: dict = {
            "temperature": temperature,
            "response_mime_type": "application/json",
            "response_schema": response_model,
            "max_output_tokens": int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS", "16384")),
        }
        thinking_level = os.environ.get("GEMINI_THINKING_LEVEL")
        if thinking_level:
            config["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)

        started = time.perf_counter()
        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                prompt,
            ],
            config=types.GenerateContentConfig(**config),
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, response_model):
            value = parsed
        elif parsed is not None:
            if hasattr(parsed, "model_dump"):
                parsed = parsed.model_dump()
            value = response_model.model_validate(parsed)
        else:
            value = response_model.model_validate_json(response.text or "")

        usage_meta = getattr(response, "usage_metadata", None)
        usage = usage_meta.model_dump() if hasattr(usage_meta, "model_dump") else {}
        return StructuredResult(
            value=value,
            model=self.model,
            latency_sec=time.perf_counter() - started,
            usage=usage,
        )
