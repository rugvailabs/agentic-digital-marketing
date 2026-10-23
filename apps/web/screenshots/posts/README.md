# Generated posts

Rendered by `PillowTemplateProvider` from captions Gemini wrote live, pulled
straight out of MinIO. Not mockups — these are the bytes the API stored.

| File | Language | Template | Size |
| ---- | -------- | -------- | ---- |
| `english-bold-type-square.png` | English | bold type | 1080×1080 |
| `hindi-split-panel-square.png` | Hindi (Devanagari) | split panel | 1080×1080 |
| `tamil-bold-type-square.png` | Tamil | bold type | 1080×1080 |
| `tamil-flat-colour-portrait.png` | Tamil | flat colour | 1080×1350 |

The Indic ones are the point: they shape correctly (attached matras, real
conjuncts) only because the API image installs `libraqm`. Without it Pillow
draws Devanagari and Tamil with detached vowel signs.
