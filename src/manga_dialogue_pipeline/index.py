"""Build a portable SQLite FTS5 index from pipeline JSON outputs."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .io import read_json

SCHEMA_VERSION = 1
TRAILING_NUMBER = re.compile(r"(\d+)$")


@dataclass
class IndexStats:
    works: int = 0
    pages: int = 0
    panels: int = 0
    dialogues: int = 0
    named_speakers: int = 0
    unknown_speakers: int = 0


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        DROP TABLE IF EXISTS dialogues_fts;
        DROP TABLE IF EXISTS dialogues;
        DROP TABLE IF EXISTS works;
        DROP TABLE IF EXISTS metadata;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE works (
            work_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            page_count INTEGER NOT NULL,
            panel_count INTEGER NOT NULL,
            dialogue_count INTEGER NOT NULL
        );

        CREATE TABLE dialogues (
            id INTEGER PRIMARY KEY,
            work_id TEXT NOT NULL,
            page_id TEXT NOT NULL,
            display_page INTEGER,
            panel_id TEXT NOT NULL,
            dialogue_id TEXT NOT NULL,
            reading_order_index INTEGER,
            text TEXT,
            text_type TEXT,
            speaker TEXT,
            speaker_status TEXT NOT NULL,
            speaker_scope TEXT NOT NULL,
            speaker_box_id TEXT,
            speaker_confidence REAL,
            image_path TEXT,
            panel_bbox TEXT,
            dialogue_bbox TEXT
        );

        CREATE INDEX idx_dialogues_location
            ON dialogues(work_id, page_id, panel_id);
        CREATE INDEX idx_dialogues_speaker
            ON dialogues(speaker);
        CREATE INDEX idx_dialogues_status
            ON dialogues(speaker_status);

        CREATE VIRTUAL TABLE dialogues_fts USING fts5(
            text,
            content='dialogues', content_rowid='id',
            tokenize='trigram'
        );
        """
    )


def _display_page(page_id: str) -> int | None:
    match = TRAILING_NUMBER.search(page_id)
    return int(match.group(1)) if match else None


def _speaker_map(data_dir: Path, work_id: str, page_id: str) -> dict[str, dict]:
    path = data_dir / work_id / "speakers" / f"{page_id}.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return {
        str(item["dialogue_id"]): item
        for item in payload.get("predictions") or []
        if item.get("dialogue_id")
    }


def build_index(data_dir: Path, output_db: Path, works: list[str] | None = None) -> IndexStats:
    wanted = set(works or [])
    work_dirs = sorted(path for path in data_dir.iterdir() if path.is_dir())
    if wanted:
        work_dirs = [path for path in work_dirs if path.name in wanted]
    if not work_dirs:
        raise FileNotFoundError(f"no work directories found under: {data_dir}")

    output_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(output_db)
    stats = IndexStats()
    with con:
        create_schema(con)
        con.executemany(
            "INSERT INTO metadata(key,value) VALUES(?,?)",
            [
                ("schema_version", str(SCHEMA_VERSION)),
                ("built_at", datetime.now(UTC).isoformat()),
            ],
        )
        for work_dir in work_dirs:
            work_id = work_dir.name
            page_files = sorted(
                path
                for path in (work_dir / "pages").glob("*.json")
                if not path.name.endswith(".error.json")
            )
            page_count = 0
            panel_count = 0
            dialogue_count = 0
            for page_file in page_files:
                envelope = read_json(page_file)
                page_id = str(envelope["page_id"])
                speakers = _speaker_map(data_dir, work_id, page_id)
                image_path = envelope.get("image_path")
                analysis = envelope.get("analysis") or {}
                page_count += 1
                for panel in analysis.get("panels") or []:
                    panel_id = str(panel["panel_id"])
                    panel_count += 1
                    for dialogue in panel.get("dialogues") or []:
                        text = str(dialogue.get("text") or "").strip() or None
                        prediction = speakers.get(str(dialogue.get("dialogue_id"))) or {}
                        text_type = dialogue.get("text_type") or "speech"
                        speaker = prediction.get("speaker_name")
                        status = prediction.get("speaker_type") or (
                            "non_speech" if text_type in {"sfx", "narration", "sign"} else "unknown"
                        )
                        if status in {"in_panel", "off_panel"}:
                            status = "named" if speaker else "unknown"
                        scope = (
                            "off_panel"
                            if prediction.get("speaker_type") == "off_panel"
                            else "in_panel"
                        )
                        con.execute(
                            """
                            INSERT INTO dialogues(
                                work_id, page_id, display_page, panel_id, dialogue_id,
                                reading_order_index, text, text_type, speaker,
                                speaker_status, speaker_scope, speaker_box_id,
                                speaker_confidence, image_path, panel_bbox, dialogue_bbox
                            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                work_id,
                                page_id,
                                _display_page(page_id),
                                panel_id,
                                dialogue.get("dialogue_id") or "",
                                dialogue.get("reading_order_index"),
                                text,
                                text_type,
                                speaker,
                                status,
                                scope,
                                prediction.get("speaker_box_id"),
                                prediction.get("confidence"),
                                image_path,
                                json.dumps(panel.get("bbox"), ensure_ascii=False),
                                json.dumps(dialogue.get("bbox"), ensure_ascii=False),
                            ),
                        )
                        if text is not None:
                            dialogue_count += 1
                            stats.dialogues += 1
                            if status == "named":
                                stats.named_speakers += 1
                            elif status == "unknown":
                                stats.unknown_speakers += 1
            con.execute(
                """
                INSERT INTO works(
                    work_id, display_name, page_count, panel_count, dialogue_count
                ) VALUES(?,?,?,?,?)
                """,
                (work_id, work_id, page_count, panel_count, dialogue_count),
            )
            stats.works += 1
            stats.pages += page_count
            stats.panels += panel_count
        con.execute("INSERT INTO dialogues_fts(dialogues_fts) VALUES('rebuild')")
    con.close()
    return stats


def stats_dict(stats: IndexStats) -> dict:
    return asdict(stats)
