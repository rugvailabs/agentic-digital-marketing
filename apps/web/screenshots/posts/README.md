# Generated posts

Rendered by `PillowTemplateProvider` from captions Gemini wrote live, pulled
straight out of MinIO. Not mockups — these are the bytes the API stored.

Three templates, each a different idea rather than one layout recoloured:

| Template | What it is for |
| -------- | -------------- |
| **Poster** | Full-bleed brand colour, headline at 96-120px. A statement. |
| **Split panel** | A secondary-colour block holding one short token — a score, a price, a year — over a white half carrying the headline. A number. |
| **Wire** | The board as a post: paper, dotted rules, "Trending in {region}", and the topic's own velocity sparkline in chilli. "This is moving." |

| File | Language | Size |
| ---- | -------- | ---- |
| `english-*-square.png` | English | 1080×1080 |
| `hindi-*-square.png` | Hindi (Devanagari) | 1080×1080 |
| `tamil-*-portrait.png` | Tamil | 1080×1350 |

Everything is drawn at 2x and downscaled with Lanczos — Pillow does no hinting
at display size, so a 1x render left the 29px hashtag line and Tamil conjuncts
visibly soft. The Indic ones shape correctly (attached matras, real conjuncts)
only because the API image installs `libraqm`.
