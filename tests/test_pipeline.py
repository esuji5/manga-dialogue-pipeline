from __future__ import annotations

import json
from pathlib import Path

import pytest

from manga_dialogue_pipeline.extract import extract_images
from manga_dialogue_pipeline.gemini import StructuredResult
from manga_dialogue_pipeline.index import build_index
from manga_dialogue_pipeline.io import load_roster, write_json
from manga_dialogue_pipeline.schema import (
    BBox,
    CharacterBox,
    Dialogue,
    PageExtraction,
    Panel,
    SpeakerPage,
    SpeakerPrediction,
)
from manga_dialogue_pipeline.search import SearchIndex, SearchPolicy, SearchRequest
from manga_dialogue_pipeline.speaker import link_speakers


def extraction(page_id: str) -> PageExtraction:
    return PageExtraction(
        page_id=page_id,
        layout_type="four_koma_1col",
        panels=[
            Panel(
                panel_id="1",
                bbox=BBox(ymin=0, xmin=0, ymax=500, xmax=1000),
                character_boxes=[
                    CharacterBox(
                        box_id="p1_c1",
                        bbox=BBox(ymin=100, xmin=100, ymax=480, xmax=450),
                    )
                ],
                dialogues=[
                    Dialogue(
                        dialogue_id="p1_d1",
                        reading_order_index=1,
                        text="プリン半額!",
                        bbox=BBox(ymin=30, xmin=550, ymax=180, xmax=900),
                    )
                ],
            )
        ],
    )


class FakeEngine:
    model = "fake-model"

    def generate(self, *, image_path, prompt, response_model, temperature=0.0):
        if response_model is PageExtraction:
            value = extraction(prompt.splitlines()[0].removeprefix("page_id: "))
        elif response_model is SpeakerPage:
            packet = json.loads(prompt.split("INPUT JSON:\n", 1)[1])
            value = SpeakerPage(
                page_id=packet["page_id"],
                predictions=[
                    SpeakerPrediction(
                        dialogue_id="p1_d1",
                        panel_id="1",
                        speaker_box_id="p1_c1",
                        speaker_name="ハル",
                        speaker_type="in_panel",
                        confidence=0.9,
                    )
                ],
            )
        else:
            raise AssertionError(response_model)
        return StructuredResult(value=value, model=self.model, latency_sec=0.01, usage={})


def test_bbox_rejects_reversed_edges() -> None:
    with pytest.raises(ValueError):
        BBox(ymin=100, xmin=0, ymax=20, xmax=100)


def test_image_to_json_to_speaker_to_search(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    (images / "001.png").write_bytes(b"not-a-real-png-needed-by-fake-engine")
    data = tmp_path / "data"

    extract_stats = extract_images(
        images=images,
        work_id="sample",
        output_dir=data,
        extraction_prompt="extract",
        base_path=tmp_path,
        engine=FakeEngine(),
    )
    assert extract_stats == {"images": 1, "extracted": 1, "skipped": 0, "errors": 0}

    roster_file = tmp_path / "characters.yaml"
    roster_file.write_text(
        "characters:\n  - name: ハル\n    description: 明るい髪\n",
        encoding="utf-8",
    )
    speaker_stats = link_speakers(
        data_dir=data,
        work_id="sample",
        prompt="link",
        roster=load_roster(roster_file),
        base_path=tmp_path,
        engine=FakeEngine(),
    )
    assert speaker_stats["linked"] == 1

    database = data / "search.db"
    index_stats = build_index(data, database)
    assert index_stats.dialogues == 1
    assert index_stats.named_speakers == 1

    index = SearchIndex(database)
    result = index.search(
        SearchRequest(query="プリン", speaker="ハル"),
        SearchPolicy(),
    )
    assert result["total_panels"] == 1
    assert result["panels"][0]["dialogues"][0]["text"] == "プリン半額!"
    assert result["panels"][0]["dialogues"][0]["speaker"] == "ハル"


def test_index_works_without_speaker_step(tmp_path: Path) -> None:
    data = tmp_path / "data"
    write_json(
        data / "work" / "pages" / "work-001.json",
        {
            "schema_version": "manga-page/1.0",
            "work_id": "work",
            "page_id": "work-001",
            "image_path": "images/001.png",
            "analysis": extraction("work-001").model_dump(),
        },
    )
    database = data / "search.db"
    stats = build_index(data, database)
    assert stats.unknown_speakers == 1
    result = SearchIndex(database).search(
        SearchRequest(query="半額", exclude_unknown=True),
        SearchPolicy(),
    )
    assert result["total_panels"] == 0


def test_public_policy_redacts_payload_and_media(tmp_path: Path) -> None:
    data = tmp_path / "data"
    image = tmp_path / "images" / "001.png"
    image.parent.mkdir()
    image.write_bytes(b"image")
    write_json(
        data / "real" / "pages" / "real-001.json",
        {
            "schema_version": "manga-page/1.0",
            "work_id": "real",
            "page_id": "real-001",
            "image_path": "images/001.png",
            "analysis": extraction("real-001").model_dump(),
        },
    )
    database = data / "search.db"
    build_index(data, database)
    index = SearchIndex(database)
    policy = SearchPolicy(public=True)
    result = index.search(SearchRequest(query="プリン"), policy)
    panel = result["panels"][0]
    assert panel["content_visible"] is False
    assert panel["dialogues"] == []
    assert "image_url" not in panel
    assert "panel_bbox" not in panel
    assert index.media_path("real", "real-001", policy, tmp_path) is None


def test_public_policy_can_allow_self_authored_work(tmp_path: Path) -> None:
    data = tmp_path / "data"
    write_json(
        data / "sample" / "pages" / "sample-001.json",
        {
            "schema_version": "manga-page/1.0",
            "work_id": "sample",
            "page_id": "sample-001",
            "image_path": None,
            "analysis": extraction("sample-001").model_dump(),
        },
    )
    database = data / "search.db"
    build_index(data, database)
    policy = SearchPolicy(public=True, full_content_works=frozenset({"sample"}))
    panel = SearchIndex(database).search(SearchRequest(query="プリン"), policy)["panels"][0]
    assert panel["content_visible"] is True
    assert panel["dialogues"][0]["text"] == "プリン半額!"
