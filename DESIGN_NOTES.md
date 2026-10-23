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
matters. Chilli red is spent on one thing only — a topic whose velocity is
rising — so a single glance separates what is climbing from what is holding,
with no legend to read and no second meaning to learn.

## Checked against the CLAUDE.md avoid-list

| Avoided                                     | What we do instead                                        |
| ------------------------------------------- | --------------------------------------------------------- |
| Cream + serif + terracotta                  | Cool paper `#EEF1F6`, two grotesks, chilli `#D8322B`      |
| Black + neon green                          | Ink `#1B2230` on paper; neem green only marks falling velocity |
| Identical rounded cards with grey shadows   | Rules and spacing; no shadow anywhere; cards only for assets |
| All-caps tracked eyebrow labels             | Sentence-case section headings at 12/14px in slate        |
| "01/02/03" where nothing is a sequence      | Numerals are the actual rank — a real ordering            |
| Gradient blobs                              | Flat surfaces only                                        |
| Middle-dot meta strings                     | One meta line of labelled values divided by hairline rules |
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
| `--color-slate`   | `#5B6578` | `#9AA6BA` | Secondary text, meta, labels; flat velocity |
| `--color-rule`    | `#D5DAE3` | `#2A3344` | Hairlines, dotted ladder separators   |
| `--color-chilli`  | `#D8322B` | `#FF6459` | Rising velocity, focus ring           |
| `--color-neem`    | `#1E7D5A` | `#3FA87E` | Falling velocity                      |
| `--color-turmeric`| `#E3A51D` | `#F0B94A` | Watch — sensitive topics, from step 2 |

Dark mode lifts chilli/turmeric/neem because the CLAUDE.md light values fall
under 4.5:1 on `#121722`; the hues are unchanged.

**Chilli is spent on rising velocity and the focus ring, nothing else.** Source
chips, hashtags, rank numerals and the selected region tab are all ink or
slate. One accent used in one place stays readable; used in five it is
decoration. (The focus ring keeps chilli because CLAUDE.md requires it by
name.)

Type: `--font-display` Bricolage Grotesque (variable, optical size on),
`--font-ui` Schibsted Grotesk (variable). Scale `12 14 16 20 28 40 64`.
Rank numerals are ink at 800: 64px for ranks 1-3, 48px from rank 4. The Desk
title is 40px; nothing else goes above 28px.

Velocity colour is derived, not stored: last point vs the mean of the previous
five, with a ±10% dead band. Rising is chilli, flat is slate, falling is neem —
matching the CLAUDE.md palette line. `velocity()` returns the label and the
colour from one derivation, so the word and the line cannot disagree.

Turmeric is the one colour with no use on the board yet: it is held for topics
the curator flags as sensitive (disaster, death, communal, election result),
which arrives with the planner in step 2. Nothing else may claim it in the
meantime — a reserved colour that leaks into an unrelated state stops being
reserved.

The top bar's pipeline dot carries a system state rather than a velocity, so
it uses neither: slate when the ingest is healthy, chilli when it is degraded
or unreachable. A working pipeline is not news; a broken one is the most
urgent thing on the screen.

## Wireframe

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TrendForge  Trend desk India               14:32 IST   ● Ingest ok, 3 sources│ 56px
├────────────────────────────────┬─────────────────────────────────────────────┤
│ India Tamil Nadu Maha… [Jump▾] │  India · rank 1                             │
│ 20 of 40 topics   updated 14:30│  Eng vs sl                             40px │
│                                │  #EngSl  #EngVsSl  #Sports                  │
│ ╭──╮                           │  ─────────────────────────────────────────  │
│ │ 1│ Eng vs sl       ────  10L │  Volume    │ Velocity   │ Category │ Updated│
│ ╰──╯ Sports                    │  10,00,000 │ ╱╲ Rising  │ Sports   │ 14:30  │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  ─────────────────────────────────────────  │
│ ╭──╮                           │                                             │
│ │ 2│ Gold rate today ╱╲    1L  │  Evidence                                   │
│ ╰──╯ Business                  │   1  Trends  eng vs sl · +1K%               │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │   2  News    The Hindu — Gold prices…       │
│ ╭─╮                            │  ─────────────────────────────────────────  │
│ │3│ नेहा बोरा        ────  50K │  Content studio arrives in step 2.          │
│ ╰─╯ Law                        │  Captions, images and reels will be         │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │  generated here from this topic.            │
│  …  48px numerals from rank 4  │                                             │
└────────────────────────────────┴─────────────────────────────────────────────┘
   Ladder: 420px fixed            Desk: 760px measure, left-aligned
```

The `╭──╮` box is drawn here only to show the numeral's bounds — there is no box
in the UI. The numeral hangs into the left gutter, partly outside the text
column.

Below 800px the ladder takes the full width and the Desk arrives as a panel
over it; the ladder itself never reflows into cards.

## Behaviour

- **Region strip**: 14px type, 8px gaps, horizontally scrollable,
  `role="tablist"`. `←`/`→` move, `Home`/`End` jump; the selected region gets a
  2px ink underline, not a pill. Regions with no board show their name in
  slate. Order is India, then states by today's total topic volume, then UTs,
  then cities — the strip is a work queue, and alphabetical buries Maharashtra
  behind Andaman and Nicobar. A compact "Jump to…" select sits at the end of
  the strip for direct keyboard access to any of the 53 regions; it holds no
  value of its own, because a select bound to the selection sizes itself to its
  longest option and eats the column.
- **Ladder**: `role="listbox"`, one row per topic, `↑`/`↓` move the selection
  and the Desk follows. Rows are separated by a 1px dotted rule in `--rule`
  and run 75px (ranks 1-3) / 69px (rank 4+), down from a uniform 87px. Hover
  and selection tint the row ground only — no lift, no shadow.
- **Source chips** appear only when a topic has two or more sources, which is
  the only case where the fact is worth the ink. The category chip always
  shows, shortened ("Business", "Law") to fit the 420px column.
- **Sparkline**: inline SVG, 6 points, 56×18, 1.5px stroke, no axes, one dot
  marking "now". Coloured by direction (see above).
- **Desk**: held to a 760px measure, left-aligned. Heading block (region +
  rank, 40px title, hashtags) / one meta line — volume, velocity, category,
  updated — divided by hairline rules rather than grid cells / evidence list /
  the step-2 note as plain text under a rule. The only bordered box in the app
  is reserved for a rendered asset, so the note does not get one.
- **Below 800px** (`--breakpoint-desk`) the ladder takes the full width and the
  Desk arrives as a panel over it, opened by picking a topic and dismissed with
  "Back to ladder" or Escape. The panel starts below the 56px top bar: the bar
  is sticky at a higher z-index and would otherwise cover the panel's own way
  out.
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

## The content studio (step 2)

The step-2 placeholder is gone. The Desk now ends with a one-line control row
(brand, language, "Generate post"), a status line that polls the job, the
caption as an editable textarea with its hashtags and alt text, and the
rendered images.

**Those image cards are the only cards in the app.** That is what the border
was reserved for from the start: a bordered box means "a rendered asset lives
here", never "some content lives here". Nothing else gained a border, a
shadow or a colour.

Post templates follow the same rules as the board — flat colour, no gradient,
no shadow, type and rules carrying the hierarchy — so a post looks like the
desk it came from. Three of them: bold type on paper, a split brand panel, and
full-bleed flat colour. Headlines autofit by measured bounding box rather than
character count, because Tamil and Devanagari advance widths have nothing to
do with Latin ones and a single long Tamil word cannot wrap.

## Known gaps, visible in the UI

**Multi-source topics are real but uncommon.** The curator clusters in
embedding space, so a Trends keyword and a news headline about the same story
do now merge — but only when they genuinely are the same story, which across
these three sources is a minority of the time. Measured on real vectors, true
cross-source matches score 0.686-0.693 and unrelated same-genre titles
0.54-0.67. Loosening the threshold would manufacture corroboration rather than
find it.

**Topic identity is separate from the topic's title.** The curator writes the
display title fresh every run, so the same story comes back worded differently
and a title-keyed row forks: a second row appears, the first drops to rank 0,
and any content job hanging off it is stranded. Rows are therefore matched
across runs on a stable `cluster_id` derived from the *source* headline of the
cluster's most trusted member, falling back to centroid cosine above 0.9 — far
above the 0.68 used for grouping, because this decides identity rather than
similarity. A reworded topic updates its row, keeps its rank, its velocity
history and its posts.

Rows that forked before this existed stay where they are, at rank 0. They are
not retroactively merged; they simply stop being produced.
