"""Link extracted dialogue IDs to character boxes and optional character names."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .gemini import GeminiEngine, StructuredResult
from .io import read_json, write_json
from .schema import CharacterRoster, SpeakerPage


class SpeakerEngine(Protocol):
    model: str

    def generate(
        self,
        *,
        image_path: Path,
        prompt: str,
        response_model: type[SpeakerPage],
        temperature: float = 0.0,
    ) -> StructuredResult[SpeakerPage]: ...


def _resolve_image(image_value: str, base_path: Path) -> Path:
    image_path = Path(image_value)
    return image_path if image_path.is_absolute() else base_path / image_path


def _speaker_packet(page_envelope: dict, roster: CharacterRoster) -> dict:
    analysis = page_envelope["analysis"]
    panels = []
    for panel in analysis.get("panels") or []:
        panels.append(
            {
                "panel_id": panel["panel_id"],
                "character_boxes": panel.get("character_boxes") or [],
                "dialogues": [
                    {
                        "dialogue_id": dialogue["dialogue_id"],
                        "reading_order_index": dialogue.get("reading_order_index"),
                        "text": dialogue.get("text"),
                        "text_type": dialogue.get("text_type"),
                        "bbox": dialogue.get("bbox"),
                    }
                    for dialogue in (panel.get("dialogues") or [])
                ],
            }
        )
    return {
        "page_id": page_envelope["page_id"],
        "characters": [item.model_dump() for item in roster.characters],
        "panels": panels,
    }


def link_page(
    engine: SpeakerEngine,
    *,
    image_path: Path,
    page_envelope: dict,
    roster: CharacterRoster,
    prompt: str,
) -> tuple[SpeakerPage, dict]:
    packet = _speaker_packet(page_envelope, roster)
    result = engine.generate(
        image_path=image_path,
        prompt=f"{prompt}\n\nINPUT JSON:\n{json.dumps(packet, ensure_ascii=False)}",
        response_model=SpeakerPage,
    )
    linked = result.value
    linked.page_id = page_envelope["page_id"]
    expected = {
        dialogue["dialogue_id"] for panel in packet["panels"] for dialogue in panel["dialogues"]
    }
    actual = {item.dialogue_id for item in linked.predictions}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(
            f"speaker output IDs do not match extraction: missing={missing}, extra={extra}"
        )
    return linked, {
        "model": result.model,
        "latency_sec": result.latency_sec,
        "usage": result.usage,
    }


def link_speakers(
    *,
    data_dir: Path,
    work_id: str,
    prompt: str,
    roster: CharacterRoster,
    model: str | None = None,
    base_path: Path | None = None,
    continue_on_error: bool = False,
    engine: SpeakerEngine | None = None,
) -> dict:
    pages_dir = data_dir / work_id / "pages"
    output_dir = data_dir / work_id / "speakers"
    page_files = sorted(
        path for path in pages_dir.glob("*.json") if not path.name.endswith(".error.json")
    )
    if not page_files:
        raise FileNotFoundError(f"no extracted pages found under: {pages_dir}")
    engine = engine or GeminiEngine(model)
    base_path = (base_path or Path.cwd()).resolve()
    stats = {"pages": len(page_files), "linked": 0, "errors": 0}

    for page_file in page_files:
        envelope = read_json(page_file)
        page_id = envelope["page_id"]
        image_path = _resolve_image(envelope["image_path"], base_path)
        try:
            linked, meta = link_page(
                engine,
                image_path=image_path,
                page_envelope=envelope,
                roster=roster,
                prompt=prompt,
            )
            write_json(
                output_dir / f"{page_id}.json",
                {
                    "schema_version": "manga-speakers/1.0",
                    "work_id": work_id,
                    "page_id": page_id,
                    "image_path": envelope["image_path"],
                    "provider": "gemini",
                    "created_at": datetime.now(UTC).isoformat(),
                    **meta,
                    "predictions": [item.model_dump() for item in linked.predictions],
                },
            )
            stats["linked"] += 1
        except Exception as exc:
            stats["errors"] += 1
            if not continue_on_error:
                raise
            write_json(
                output_dir / f"{page_id}.error.json",
                {
                    "schema_version": "manga-speakers-error/1.0",
                    "work_id": work_id,
                    "page_id": page_id,
                    "error": repr(exc),
                },
            )
    return stats
