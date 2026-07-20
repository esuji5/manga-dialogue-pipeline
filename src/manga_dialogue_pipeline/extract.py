"""Page routing and coordinate-aware dialogue extraction."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from .gemini import GeminiEngine, StructuredResult
from .io import collect_images, relative_or_absolute, write_json
from .schema import PageExtraction, PageRoute


class StructuredEngine(Protocol):
    model: str

    def generate(
        self,
        *,
        image_path: Path,
        prompt: str,
        response_model: type[PageExtraction] | type[PageRoute],
        temperature: float = 0.0,
    ) -> StructuredResult: ...


def page_id_for(work_id: str, image_path: Path) -> str:
    prefix = f"{work_id}-"
    return image_path.stem if image_path.stem.startswith(prefix) else f"{prefix}{image_path.stem}"


def route_page(
    engine: StructuredEngine,
    image_path: Path,
    page_id: str,
    prompt: str,
) -> tuple[PageRoute, dict]:
    result = engine.generate(
        image_path=image_path,
        prompt=f"page_id: {page_id}\n\n{prompt}",
        response_model=PageRoute,
    )
    return result.value, {
        "model": result.model,
        "latency_sec": result.latency_sec,
        "usage": result.usage,
    }


def extract_page(
    engine: StructuredEngine,
    image_path: Path,
    page_id: str,
    prompt: str,
) -> tuple[PageExtraction, dict]:
    result = engine.generate(
        image_path=image_path,
        prompt=f"page_id: {page_id}\n\n{prompt}",
        response_model=PageExtraction,
    )
    extraction = result.value
    if extraction.page_id != page_id:
        extraction.page_id = page_id
    return extraction, {
        "model": result.model,
        "latency_sec": result.latency_sec,
        "usage": result.usage,
    }


def extract_images(
    *,
    images: Path,
    work_id: str,
    output_dir: Path,
    extraction_prompt: str,
    model: str | None = None,
    route_prompt: str | None = None,
    route_pages: bool = False,
    continue_on_error: bool = False,
    base_path: Path | None = None,
    engine: StructuredEngine | None = None,
) -> dict:
    """Extract every image and write one JSON envelope per page."""
    image_paths = collect_images(images)
    engine = engine or GeminiEngine(model)
    pages_dir = output_dir / work_id / "pages"
    routes_dir = output_dir / work_id / "routes"
    base_path = (base_path or Path.cwd()).resolve()
    stats = {"images": len(image_paths), "extracted": 0, "skipped": 0, "errors": 0}

    for image_path in image_paths:
        page_id = page_id_for(work_id, image_path)
        route: PageRoute | None = None
        route_meta: dict | None = None
        try:
            if route_pages:
                if not route_prompt:
                    raise ValueError("route_prompt is required when route_pages=True")
                route, route_meta = route_page(engine, image_path, page_id, route_prompt)
                write_json(
                    routes_dir / f"{page_id}.json",
                    {
                        "schema_version": "manga-route/1.0",
                        "work_id": work_id,
                        "page_id": page_id,
                        "image_path": relative_or_absolute(image_path, base_path),
                        "provider": "gemini",
                        **route_meta,
                        "route": route.model_dump(),
                    },
                )
                if not route.is_comic_page:
                    stats["skipped"] += 1
                    continue

            extraction, meta = extract_page(engine, image_path, page_id, extraction_prompt)
            write_json(
                pages_dir / f"{page_id}.json",
                {
                    "schema_version": "manga-page/1.0",
                    "work_id": work_id,
                    "page_id": page_id,
                    "image_path": relative_or_absolute(image_path, base_path),
                    "provider": "gemini",
                    "created_at": datetime.now(UTC).isoformat(),
                    **meta,
                    "route": route.model_dump() if route else None,
                    "analysis": extraction.model_dump(),
                },
            )
            stats["extracted"] += 1
        except Exception as exc:
            stats["errors"] += 1
            if not continue_on_error:
                raise
            write_json(
                pages_dir / f"{page_id}.error.json",
                {
                    "schema_version": "manga-page-error/1.0",
                    "work_id": work_id,
                    "page_id": page_id,
                    "image_path": relative_or_absolute(image_path, base_path),
                    "error": repr(exc),
                },
            )
    return stats
