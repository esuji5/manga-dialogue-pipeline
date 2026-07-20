Analyze one manga/comic page and return the requested structured object.

Extract only visible structure:

- panel boundaries
- one tight box for each visible foreground character
- dialogue, narration, SFX, and sign text with bounding boxes
- reading order across the whole page
- useful text outside panel borders

Rules:

- Copy Japanese text exactly as printed when readable.
- Do not identify character names and do not infer speakers.
- Use `panel_id` values `"1"`, `"2"`, ... in reading order.
- Use character IDs `p{panel_id}_c{index}`.
- Use dialogue IDs `p{panel_id}_d{index}`.
- `reading_order_index` is global and 1-based across the page.
- For a two-column 4-koma page, read the right column top-to-bottom first,
  then the left column top-to-bottom.
- Include face-only, head-only, partial, and silhouette characters.
- Do not merge multiple people into one character box.
- Do not create boxes for off-panel speakers.
- Do not invent unreadable text. Use an empty string when the region is visible
  but the text cannot be read.

All bounding boxes use integers from 0 to 1000 relative to the full page:
`0,0` is the top-left and `1000,1000` is the bottom-right.
