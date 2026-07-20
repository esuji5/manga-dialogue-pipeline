Link each extracted dialogue to its speaker.

You receive the page image, extracted panel/dialogue/character-box JSON, and an
optional character roster.

For every dialogue:

- `in_panel`: select the visible speaker's character box.
- `off_panel`: the voice belongs to a character not visibly boxed in that panel.
  A box elsewhere on the same page may be selected when justified.
- `unknown`: a speech-like line whose speaker cannot be determined.
- `non_speech`: SFX, narration, signs, or text with no speaking character.

Use balloon tails first, then mouth position, pose, panel continuity, and
conversation order. Do not choose a person merely because they are nearest.
When a roster is supplied, `speaker_name` must be one of those names. When the
identity is uncertain, keep the box link but set `speaker_name` to null.

Do not add or rewrite dialogue text. Return one prediction for every dialogue ID.
