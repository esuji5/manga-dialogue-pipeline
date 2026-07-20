"""Read-only querying and public-result redaction for the search index."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
SPACE_RE = re.compile(r"[\s\u3000]+")


def normalize_speaker(value: str | None) -> str | None:
    if not value:
        return None
    value = SPACE_RE.sub(" ", value).strip()
    if JAPANESE_RE.search(value):
        value = SPACE_RE.sub("", value)
    return value or None


@dataclass(frozen=True)
class SearchPolicy:
    public: bool = False
    full_content_works: frozenset[str] = frozenset()

    def content_visible(self, work_id: str) -> bool:
        return not self.public or work_id in self.full_content_works


@dataclass(frozen=True)
class SearchRequest:
    query: str = ""
    works: tuple[str, ...] = ()
    speaker: str | None = None
    exclude_unknown: bool = False
    page: str | None = None
    panel: str | None = None
    limit: int = 50


class SearchIndex:
    def __init__(self, database: Path):
        if not database.exists():
            raise FileNotFoundError(database)
        self.database = database

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.database}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def config(self, policy: SearchPolicy) -> dict:
        with self.connect() as con:
            works = [dict(row) for row in con.execute("SELECT * FROM works ORDER BY work_id")]
            speakers = []
            if not policy.public:
                speakers = [
                    row[0]
                    for row in con.execute(
                        """
                        SELECT speaker FROM dialogues
                        WHERE speaker_status='named' AND speaker IS NOT NULL
                        GROUP BY speaker ORDER BY COUNT(*) DESC, speaker
                        """
                    )
                ]
            metadata = {
                row["key"]: row["value"] for row in con.execute("SELECT key,value FROM metadata")
            }
        for work in works:
            work["content_visible"] = policy.content_visible(work["work_id"])
        return {
            "mode": "public" if policy.public else "local",
            "works": works,
            "speakers": speakers,
            "metadata": metadata,
        }

    @staticmethod
    def _fts_phrase(query: str) -> str:
        return '"' + query.replace('"', '""') + '"'

    def search(self, request: SearchRequest, policy: SearchPolicy) -> dict:
        query = request.query.strip()
        speaker = normalize_speaker(request.speaker)
        limit = max(1, min(int(request.limit), 200))
        conditions = ["d.text IS NOT NULL"]
        args: list[object] = []

        if query:
            if len(query) >= 3:
                conditions.append(
                    "d.id IN (SELECT rowid FROM dialogues_fts WHERE dialogues_fts MATCH ?)"
                )
                args.append(f"{{text}}: {self._fts_phrase(query)}")
            else:
                conditions.append("d.text LIKE ?")
                args.append(f"%{query}%")
        if request.works:
            placeholders = ",".join("?" for _ in request.works)
            conditions.append(f"d.work_id IN ({placeholders})")
            args.extend(request.works)
        if speaker:
            conditions.append("d.speaker = ?")
            args.append(speaker)
        if request.exclude_unknown:
            conditions.append("d.speaker_status != 'unknown'")
        if request.page:
            conditions.append("d.page_id = ?")
            args.append(request.page)
        if request.panel:
            conditions.append("d.panel_id = ?")
            args.append(request.panel)
        if not query and not request.works and not speaker and not request.page:
            return {"panels": [], "total_panels": 0, "total_dialogues": 0, "truncated": False}

        where = " AND ".join(conditions)
        with self.connect() as con:
            total_panels = con.execute(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM dialogues d WHERE {where}
                    GROUP BY d.work_id,d.page_id,d.panel_id
                )
                """,
                args,
            ).fetchone()[0]
            rows = con.execute(
                f"""
                WITH matched_panels AS (
                    SELECT d.work_id,d.page_id,d.panel_id
                    FROM dialogues d WHERE {where}
                    GROUP BY d.work_id,d.page_id,d.panel_id
                    ORDER BY d.work_id,d.page_id,CAST(d.panel_id AS INTEGER)
                    LIMIT ?
                )
                SELECT d.* FROM dialogues d
                JOIN matched_panels m
                  ON m.work_id=d.work_id AND m.page_id=d.page_id AND m.panel_id=d.panel_id
                WHERE {where}
                ORDER BY d.work_id,d.page_id,CAST(d.panel_id AS INTEGER),
                         d.reading_order_index,d.id
                """,
                [*args, limit, *args],
            ).fetchall()

        panels = []

        def panel_key(row: sqlite3.Row) -> tuple[str, str, str]:
            return row["work_id"], row["page_id"], row["panel_id"]

        for (work_id, page_id, panel_id), grouped in groupby(rows, key=panel_key):
            group = list(grouped)
            first = group[0]
            visible = policy.content_visible(work_id)
            panel_result = {
                "work_id": work_id,
                "page_id": page_id,
                "display_page": first["display_page"],
                "panel_id": panel_id,
                "content_visible": visible,
                "match_count": len(group),
                "dialogues": [],
            }
            if visible:
                panel_result.update(
                    {
                        "panel_bbox": (
                            json.loads(first["panel_bbox"]) if first["panel_bbox"] else None
                        ),
                        "image_url": (
                            f"/media?work={work_id}&page={page_id}" if first["image_path"] else None
                        ),
                        "dialogues": [
                            {
                                "dialogue_id": row["dialogue_id"],
                                "reading_order_index": row["reading_order_index"],
                                "text": row["text"],
                                "text_type": row["text_type"],
                                "speaker": row["speaker"],
                                "speaker_status": row["speaker_status"],
                                "speaker_scope": row["speaker_scope"],
                                "speaker_confidence": row["speaker_confidence"],
                            }
                            for row in group
                        ],
                    }
                )
            panels.append(panel_result)
        return {
            "panels": panels,
            "total_panels": total_panels,
            "total_dialogues": len(rows),
            "truncated": total_panels > limit,
        }

    def media_path(
        self,
        work_id: str,
        page_id: str,
        policy: SearchPolicy,
        media_root: Path,
    ) -> Path | None:
        if not policy.content_visible(work_id):
            return None
        with self.connect() as con:
            row = con.execute(
                """
                SELECT image_path FROM dialogues
                WHERE work_id=? AND page_id=? AND image_path IS NOT NULL LIMIT 1
                """,
                (work_id, page_id),
            ).fetchone()
        if not row:
            return None
        path = Path(row[0])
        if not path.is_absolute():
            path = media_root / path
        try:
            path = path.resolve()
            path.relative_to(media_root.resolve())
        except (OSError, ValueError):
            return None
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            return None
        return path if path.is_file() else None
