"""Command-line interface for the complete local pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from .extract import extract_images
from .index import build_index, stats_dict
from .io import load_env, load_roster
from .search import SearchIndex, SearchPolicy, SearchRequest
from .server import serve
from .speaker import link_speakers

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "prompts"


def _prompt(path: str | None, default_name: str) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    source_prompt = PROMPTS / default_name
    if source_prompt.is_file():
        return source_prompt.read_text(encoding="utf-8")
    return (
        files("manga_dialogue_pipeline")
        .joinpath("prompts", default_name)
        .read_text(encoding="utf-8")
    )


def _add_env_and_model(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env", default=".env")
    parser.add_argument("--model", help="Gemini model ID; defaults to GEMINI_MODEL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manga-pipeline",
        description="Image → structured JSON → speaker labels → SQLite search.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract", help="extract panels, text and coordinates")
    extract.add_argument("images", type=Path)
    extract.add_argument("--work-id", required=True)
    extract.add_argument("--data-dir", type=Path, default=Path("data"))
    extract.add_argument(
        "--prompt",
        help="custom extraction prompt; defaults to the bundled prompt",
    )
    extract.add_argument("--route", action="store_true", help="classify and skip non-comic pages")
    extract.add_argument("--route-prompt", help="custom routing prompt")
    extract.add_argument("--continue-on-error", action="store_true")
    _add_env_and_model(extract)

    speakers = sub.add_parser("speakers", help="link dialogues to boxes and names")
    speakers.add_argument("--work-id", required=True)
    speakers.add_argument("--data-dir", type=Path, default=Path("data"))
    speakers.add_argument("--characters", type=Path)
    speakers.add_argument("--prompt", help="custom speaker-linking prompt")
    speakers.add_argument("--continue-on-error", action="store_true")
    _add_env_and_model(speakers)

    index = sub.add_parser("index", help="build the SQLite FTS5 index")
    index.add_argument("--data-dir", type=Path, default=Path("data"))
    index.add_argument("--out", type=Path, default=Path("data/search.db"))
    index.add_argument("--work", action="append", default=[])

    search = sub.add_parser("search", help="search from the terminal")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--db", type=Path, default=Path("data/search.db"))
    search.add_argument("--work", action="append", default=[])
    search.add_argument("--speaker")
    search.add_argument("--exclude-unknown", action="store_true")
    search.add_argument("--page")
    search.add_argument("--panel")
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--public", action="store_true")
    search.add_argument("--json", action="store_true")

    web = sub.add_parser("serve", help="start the read-only search UI")
    web.add_argument("--db", type=Path, default=Path("data/search.db"))
    web.add_argument("--media-root", type=Path, default=Path.cwd())
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8787)
    web.add_argument("--public", action="store_true")
    web.add_argument("--full-content-work", action="append", default=[])

    run = sub.add_parser("run", help="run extraction through indexing")
    run.add_argument("images", type=Path)
    run.add_argument("--work-id", required=True)
    run.add_argument("--data-dir", type=Path, default=Path("data"))
    run.add_argument("--characters", type=Path)
    run.add_argument("--link-speakers", action="store_true")
    run.add_argument("--route", action="store_true")
    run.add_argument("--serve", action="store_true")
    run.add_argument("--port", type=int, default=8787)
    run.add_argument("--continue-on-error", action="store_true")
    _add_env_and_model(run)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command_extract(args: argparse.Namespace) -> int:
    load_env(args.env)
    stats = extract_images(
        images=args.images,
        work_id=args.work_id,
        output_dir=args.data_dir,
        extraction_prompt=_prompt(args.prompt, "page_extraction.md"),
        model=args.model,
        route_prompt=_prompt(args.route_prompt, "page_router.md") if args.route else None,
        route_pages=args.route,
        continue_on_error=args.continue_on_error,
        base_path=Path.cwd(),
    )
    _print(stats)
    return 0 if not stats["errors"] else 1


def command_speakers(args: argparse.Namespace) -> int:
    load_env(args.env)
    stats = link_speakers(
        data_dir=args.data_dir,
        work_id=args.work_id,
        prompt=_prompt(args.prompt, "speaker_linking.md"),
        roster=load_roster(args.characters),
        model=args.model,
        base_path=Path.cwd(),
        continue_on_error=args.continue_on_error,
    )
    _print(stats)
    return 0 if not stats["errors"] else 1


def command_index(args: argparse.Namespace) -> int:
    stats = build_index(args.data_dir, args.out, args.work)
    _print(stats_dict(stats))
    print(f"DB: {args.out}")
    return 0


def command_search(args: argparse.Namespace) -> int:
    index = SearchIndex(args.db)
    result = index.search(
        SearchRequest(
            query=args.query,
            works=tuple(args.work),
            speaker=args.speaker,
            exclude_unknown=args.exclude_unknown,
            page=args.page,
            panel=args.panel,
            limit=args.limit,
        ),
        SearchPolicy(public=args.public),
    )
    if args.json:
        _print(result)
        return 0
    for panel in result["panels"]:
        page = (
            f"p.{panel['display_page']}" if panel["display_page"] is not None else panel["page_id"]
        )
        print(f"{panel['work_id']} {page} コマ{panel['panel_id']}")
        for dialogue in panel["dialogues"]:
            scope = " [画面外]" if dialogue["speaker_scope"] == "off_panel" else ""
            print(f"  {dialogue['speaker'] or 'unknown'}{scope}: {dialogue['text']}")
    print(f"{result['total_panels']}コマ" + (" (上限あり)" if result["truncated"] else ""))
    return 0


def command_serve(args: argparse.Namespace) -> int:
    serve(
        database=args.db,
        media_root=args.media_root,
        host=args.host,
        port=args.port,
        public=args.public,
        full_content_works=frozenset(args.full_content_work),
    )
    return 0


def command_run(args: argparse.Namespace) -> int:
    load_env(args.env)
    extraction_stats = extract_images(
        images=args.images,
        work_id=args.work_id,
        output_dir=args.data_dir,
        extraction_prompt=_prompt(None, "page_extraction.md"),
        model=args.model,
        route_prompt=_prompt(None, "page_router.md") if args.route else None,
        route_pages=args.route,
        continue_on_error=args.continue_on_error,
        base_path=Path.cwd(),
    )
    _print({"extraction": extraction_stats})
    if args.link_speakers:
        speaker_stats = link_speakers(
            data_dir=args.data_dir,
            work_id=args.work_id,
            prompt=_prompt(None, "speaker_linking.md"),
            roster=load_roster(args.characters),
            model=args.model,
            base_path=Path.cwd(),
            continue_on_error=args.continue_on_error,
        )
        _print({"speakers": speaker_stats})
    database = args.data_dir / "search.db"
    index_stats = build_index(args.data_dir, database, [args.work_id])
    _print({"index": stats_dict(index_stats), "database": str(database)})
    if args.serve:
        serve(database=database, media_root=Path.cwd(), port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    commands = {
        "extract": command_extract,
        "speakers": command_speakers,
        "index": command_index,
        "search": command_search,
        "serve": command_serve,
        "run": command_run,
    }
    try:
        return commands[args.command](args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
