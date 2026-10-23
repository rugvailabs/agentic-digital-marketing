# TrendForge — design notes (step 1: the trend board)

Written before the UI, per CLAUDE.md. Scope here is the board only: region
strip, ranked ladder, and the Desk panel that will host the content studio in
step 2.

## Why this doesn't look generic

A wire desk is a tool for people who read fast and act, so the page is built
out of ranked rows and rules rather than cards: the only boxes on the screen
are the ones that will eventually hold a rendered image or video, which makes a
card mean "asset" instead of "any content at all". Hierarchy comes from the
64px Bricolage rank numeral hanging outside the text column — the way a
newspaper folio sits in the margin — so your eye lands on position before it
lands on words, and no stat tiles or eyebrow labels are needed to tell you what
matters. Chilli red is spent only on heat, focus and the live dot, which means a
single glance separates rising from settled without reading a legend.

## Checked against the CLAUDE.md avoid-list

| Avoided                                     | What we do instead                                        |
| ------------------------------------------- | --------------------------------------------------------- |
| Cream + serif + terracotta                  | Cool paper `#EEF1F6`, two grotesks, chilli `#D8322B`      |
| Black + neon green                          | Ink `#1B2230` on paper; neem green only as a settled state |
| Identical rounded cards with grey shadows   | Rules and spacing; no shadow anywhere; cards only for assets |
| All-caps tracked eyebrow labels             | Sentence-case section headings at 12/14px in slate        |
| "01/02/03" where nothing is a sequence      | Numerals are the actual rank — a real ordering            |
| Gradient blobs                              | Flat surfaces only                                        |
| Middle-dot meta strings                     | Meta sits in labelled columns and chips                   |
| Arrows appended to buttons                  | Verb-only labels: "Generate post", "Render reel"          |
| Inter                                       | Bricolage Grotesque (display), Schibsted Grotesk (UI)     |
| Stat tiles across the top                   | Top bar is app name, IST clock, pipeline dot — nothing else |
| Icons/emoji next to every label             | Text labels; the only non-text marks are sparklines and the dot |
| Centered hero text                          | Everything left-aligned, no hero                          |

## Tokens

One `@theme` block in `globals.css`. Light is the base; dark redefines the same
names, so no component ever branches on theme.

| Token             | Light     | Dark      | Role                                  |
| ----------------- | --------- | --------- | ------------------------------------- |
| `--color-paper`   | `#EEF1F6` | `#121722` | Page ground                           |
| `--color-surface` | `#FFFFFF` | `#1A2130` | Asset cards, Desk panel, strip        |
| `--color-ink`     | `#1B2230` | `#EDF0F5` | Primary text, rank numerals           |
| `--color-slate`   | `#5B6578` | `#9AA6BA` | Secondary text, meta, labels          |
| `--color-rule`    | `#D5DAE3` | `#2A3344` | Hairlines, dotted ladder separators   |
| `--color-chilli`  | `#D8322B` | `#FF6459` | Heat / rising, focus ring, live dot   |
| `--color-turmeric`| `#E3A51D` | `#F0B94A` | Watch                                 |
| `--color-neem`    | `#1E7D5A` | `#3FA87E` | Settled                               |

Dark mode lifts chilli/turmeric/neem because the CLAUDE.md light values fall
under 4.5:1 on `#121722`; the hues are unchanged.

Type: `--font-display` Bricolage Grotesque (500/700/800, optical size on),
`--font-ui` Schibsted Grotesk (400/500/600). Scale `12 14 16 20 28 40 64`.
Rank numerals are 64px display; nothing else goes above 28px.

Velocity colour is derived, not stored: last point vs the mean of the previous
five — above +10% is chilli (rising), within ±10% is neem (settled), below is
turmeric (cooling).

## Wireframe

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TrendForge                                      14:32 IST   ● ingest ok      │  56px fixed
├────────────────────────────────┬─────────────────────────────────────────────┤
│ WIRE                           │ DESK                                        │
│                                │                                             │
│ ┌ region strip ──────────────┐ │  Maharashtra · rank 1                       │
│ │ India  Andhra  Assam  Bih… │ │  ┌───────────────────────────────────────┐  │
│ │ ◀ scrolls, ←/→ + Home/End  │ │  │ Eng vs sl                         28px│  │
│ └────────────────────────────┘ │  └───────────────────────────────────────┘  │
│                                │  #EngSl  #EngVsSl  #Sports                  │
│ 40 topics · updated 14:30 IST  │                                             │
│                                │  Volume   2,00,000      Score      100.0    │
│ ╭──╮                           │  Sources  Trends        Category   Sports   │
│ │ 1│ Eng vs sl          ╱╲_╱   │  Velocity ▁▁▁▃▇█        First seen 11:30    │
│ ╰──╯ Sports · Trends     2.0L  │                                             │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  Evidence                                   │
│ ╭──╮                           │   1  Trends   eng vs sl                     │
│ │ 2│ Gold rate today   _╱‾╲_   │   2  News     The Hindu — Gold prices…      │
│ ╰──╯ Business · Trends   1.0L  │                                             │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  ┌───────────────────────────────────────┐  │
│ ╭──╮                           │  │  Content studio arrives in step 2.    │  │
│ │ 3│ नेहा बोरा          ╱‾‾‾   │  │  Captions, images and reels will be   │  │
│ ╰──╯ Law · Trends        50K   │  │  generated here from this topic.      │  │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  └───────────────────────────────────────┘  │
│  …                             │                                             │
└────────────────────────────────┴─────────────────────────────────────────────┘
   Wire: 420px fixed              Desk: fills remaining width
```

The `╭──╮` box is drawn here only to show the numeral's bounds — there is no box
in the UI. The numeral hangs into the left gutter, partly outside the text
column.

Below 900px the Desk moves under the Wire and the rank numeral drops to 40px;
the ladder itself never reflows into cards.

## Behaviour

- **Region strip**: horizontally scrollable, `role="tablist"`. `←`/`→` move,
  `Home`/`End` jump, `Enter`/`Space` select; the selected region gets a 2px
  chilli underline, not a pill. Regions with no board show their name in slate.
- **Ladder**: `role="listbox"`, one row per topic, `↑`/`↓` move the selection
  and the Desk follows. Rows are separated by a 1px dotted rule. Hover/focus
  tints the row ground only — no lift, no shadow.
- **Sparkline**: inline SVG, 6 points, 56×18, 1.5px stroke, no axes, no dots.
- **Motion**: one ladder load-in, rows settling top to bottom over 240ms total
  (`translateY(4px)` + opacity, 18ms stagger). Desk panel cross-fades in 120ms
  when the selection changes. Nothing else animates. All of it collapses under
  `prefers-reduced-motion`.
- **Numbers**: `en-IN` formatting throughout — `2,00,000` not `200,000`; volume
  compacts to `2.0L` / `1.2Cr` on the ladder and shows in full on the Desk.
- **Empty states** say what to do next: "No topics for Ladakh yet. Run
  `tf.ps1 ingest` to pull the first snapshot."
- **Focus** is a 2px chilli ring with a 2px offset, visible on every
  interactive element, never suppressed.

## Known gap, visible in the UI

Source chips almost always show a single source. The step-1 merge dedupes by
normalised title, and Google Trends emits short keywords ("eng vs sl") while
Google News emits full headlines, so the two never collide and the weighted sum
never actually sums. This is the specified merge, so it stands; the cheap
non-LLM fix is a containment pass (Trends keyword appearing inside a news
headline), which is worth doing only if it survives the obvious failure mode of
short keywords like "whatsapp" matching everything.
