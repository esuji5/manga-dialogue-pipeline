"""Manga dialogue extraction, speaker linking, and local search."""

from .schema import (
    BBox,
    CharacterBox,
    Dialogue,
    PageExtraction,
    Panel,
    SpeakerPage,
    SpeakerPrediction,
)

__all__ = [
    "BBox",
    "CharacterBox",
    "Dialogue",
    "PageExtraction",
    "Panel",
    "SpeakerPage",
    "SpeakerPrediction",
]

__version__ = "0.1.0"
