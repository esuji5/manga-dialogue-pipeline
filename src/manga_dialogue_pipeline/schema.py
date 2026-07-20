"""Structured-output schemas shared by extraction and speaker linking."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BBox(BaseModel):
    """Bounding box normalized to the full page, from 0 to 1000."""

    ymin: int = Field(ge=0, le=1000)
    xmin: int = Field(ge=0, le=1000)
    ymax: int = Field(ge=0, le=1000)
    xmax: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def edges_are_ordered(self) -> BBox:
        if self.ymax <= self.ymin or self.xmax <= self.xmin:
            raise ValueError("bbox must have positive width and height")
        return self


class CharacterBox(BaseModel):
    box_id: str = Field(description='Stable ID such as "p3_c2".')
    bbox: BBox


class Dialogue(BaseModel):
    dialogue_id: str = Field(description='Stable ID such as "p3_d2".')
    reading_order_index: int = Field(ge=1)
    text: str
    text_type: Literal[
        "speech",
        "thought",
        "whisper",
        "shout",
        "sfx",
        "narration",
        "sign",
        "other",
    ] = "speech"
    bbox: BBox


class Panel(BaseModel):
    panel_id: str
    bbox: BBox
    character_boxes: list[CharacterBox] = Field(default_factory=list)
    dialogues: list[Dialogue] = Field(default_factory=list)


class PageText(BaseModel):
    text: str
    text_type: Literal[
        "character_profile",
        "margin_note",
        "chapter_title",
        "page_number",
        "author_note",
        "other",
    ] = "other"
    bbox: BBox


class PageExtraction(BaseModel):
    page_id: str
    layout_type: Literal[
        "four_koma_2col_4row",
        "four_koma_1col",
        "standard",
        "splash",
        "mixed",
        "non_comic",
        "unknown",
    ] = "unknown"
    panels: list[Panel] = Field(default_factory=list)
    page_texts: list[PageText] = Field(default_factory=list)
    uncertain_points: list[str] = Field(default_factory=list)


class PageRoute(BaseModel):
    page_type: Literal[
        "comic",
        "cover",
        "illustration",
        "character_intro",
        "afterword",
        "colophon",
        "blank",
        "unknown",
    ]
    is_comic_page: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class SpeakerPrediction(BaseModel):
    dialogue_id: str
    panel_id: str
    speaker_box_id: str | None = Field(
        default=None,
        description="A character box ID on the same page, or null when no box can be selected.",
    )
    speaker_name: str | None = Field(
        default=None,
        description="A name from the supplied roster, or null when unidentified.",
    )
    speaker_type: Literal["in_panel", "off_panel", "unknown", "non_speech"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class SpeakerPage(BaseModel):
    page_id: str
    predictions: list[SpeakerPrediction] = Field(default_factory=list)


class Character(BaseModel):
    name: str
    description: str = ""


class CharacterRoster(BaseModel):
    characters: list[Character] = Field(default_factory=list)
