# Data format

Generated files stay under `data/`, which is ignored by Git.

```text
data/
  <work-id>/
    routes/
      <page-id>.json
    pages/
      <page-id>.json
    speakers/
      <page-id>.json
  search.db
```

## Page extraction

`pages/*.json` contains provenance plus an `analysis` object:

```json
{
  "schema_version": "manga-page/1.0",
  "work_id": "mybook",
  "page_id": "mybook-001",
  "image_path": "images/001.png",
  "provider": "gemini",
  "model": "your-model-id",
  "analysis": {
    "page_id": "mybook-001",
    "layout_type": "four_koma_1col",
    "panels": [
      {
        "panel_id": "1",
        "bbox": {"ymin": 0, "xmin": 0, "ymax": 240, "xmax": 1000},
        "character_boxes": [
          {
            "box_id": "p1_c1",
            "bbox": {"ymin": 40, "xmin": 80, "ymax": 230, "xmax": 420}
          }
        ],
        "dialogues": [
          {
            "dialogue_id": "p1_d1",
            "reading_order_index": 1,
            "text": "example",
            "text_type": "speech",
            "bbox": {"ymin": 20, "xmin": 600, "ymax": 150, "xmax": 900}
          }
        ]
      }
    ]
  }
}
```

All bounding boxes are normalized to the full page from 0 to 1000.

## Speaker linking

`speakers/*.json` keeps the extraction immutable and stores a separate prediction for every dialogue ID.

```json
{
  "schema_version": "manga-speakers/1.0",
  "work_id": "mybook",
  "page_id": "mybook-001",
  "predictions": [
    {
      "dialogue_id": "p1_d1",
      "panel_id": "1",
      "speaker_box_id": "p1_c1",
      "speaker_name": "Character A",
      "speaker_type": "in_panel",
      "confidence": 0.9,
      "reason": "balloon tail"
    }
  ]
}
```

`speaker_type` is one of `in_panel`, `off_panel`, `unknown`, or `non_speech`.
