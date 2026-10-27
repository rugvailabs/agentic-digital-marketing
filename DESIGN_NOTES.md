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

**Posts are set in the same two faces as the board.** Bricolage Grotesque for
headlines and the display token, with its optical size axis driven by the
drawn size, and Schibsted Grotesk for sublines, hashtags and the brand line —
the pairing CLAUDE.md names. They were rendering in Noto Sans, which is a
perfectly good text face and not this one; a post that does not look like the
desk it came from is the thing this design direction exists to avoid.
`Brand.font_choice` picks which of the two carries headlines.

Indic scripts ignore that choice, because neither Latin face has a Devanagari
or Tamil glyph. A Hindi headline sets in Noto Sans Devanagari with its English
brand line in Schibsted, which is the right trade: matching the Latin face is
not worth setting Devanagari in a font that has no Devanagari.

Post templates follow the same rules as the board — flat colour, no gradient,
no shadow, type and rules carrying the hierarchy — so a post looks like the
desk it came from. Three of them: bold type on paper, a split brand panel, and
full-bleed flat colour. Headlines autofit by measured bounding box rather than
character count, because Tamil and Devanagari advance widths have nothing to
do with Latin ones and a single long Tamil word cannot wrap.

## The reel controls on the Desk

One row of controls, two things made from them. Brand and language are picked
once — a marketer does not choose them twice for the same topic — and then
"Generate post" and "Render reel" sit against their own output and their own
status line. They are separate jobs on separate pipelines with separate ways
of failing, which is exactly how they are reported.

**The status names the stage, not the step.** "Rendering" means two different
things to someone waiting: a post is drawing three images, a reel is driving
a browser across nine hundred frames. A reel says "Writing the script",
"Recording the voiceover", "Rendering frames" — and once, plainly, that this
takes a few minutes. Without that the first run looks stuck.

**The script appears before the video does.** It is written minutes before
the frames finish, so it goes on screen as soon as it exists: something to
read and correct instead of a spinner. The card and the spoken line sit side
by side, divided by a hairline, because they are deliberately different — the
card carries "2 crore", the voice carries "two crore rupees" — and seeing
both is the only way to check they still agree.

**A derived script says so.** When the writer is unavailable the script is
built from the topic instead, and the panel says "Built from the topic, not
written" rather than implying something wrote it.

**The video gets the one card.** A border still means "a rendered asset lives
here", so the player sits in the same box the post images do, capped at 270px
so a 9:16 file does not take the whole Desk, with its size, length, voice and
whether it carries music underneath.

## The reel (step 3)

A reel is the wire desk in motion, not a new visual language. Paper ground,
ink type, one chilli rule, the same two faces and the same left-aligned
column. If a frame were printed it would be a post.

**Three layers.** Chrome on every frame — the edition line, the masthead and
the footer — then the cards, then the grain over the top. The chrome settles
once at the start and holds; re-animating it per card would make the frame
twitch on every edit, the same reason the ladder animates once on load and
not on every selection.

**Type is measured, not scaled.** Nothing is set at a fixed fraction of the
canvas. Each headline and beat is set as large as it can be and still fit its
box, by measuring the wrapped lines — the same autofit the Pillow templates
use, for the same reason: character count is a poor proxy for width in any
script and a useless one in Tamil, where one word carries what English needs
three for and cannot be broken at a space. A three-word beat comes out
enormous and a long one steps down and wraps, which is where the scale
contrast in these frames comes from and why a new topic does not need a new
layout.

**The measure is 72% on a reel.** Two reasons pulling the same way: a reel
player stacks its action column down the right-hand side, so type running to
the right margin sits under buttons; and a narrower measure means more lines
at a larger size, which fills a 1920px canvas that otherwise reads as three
words floating in a lot of paper. The square has no action column over the
artwork, so it keeps its full column.

**Cards are centred in their band, not in the frame.** The band is what holds
the block clear of the caption and account row drawn over the bottom fifth;
centring within it is what stops a short card pooling all its white space at
the top. Anchoring to the band's baseline was tried first and reads worse than
it sounds: a two-word beat at 240px sat in the bottom third with half the
frame empty above it.

**The edition line is segmented, one per card.** A single bar filling over
the whole reel said how far through you were and nothing else. Segmented, and
sized in proportion to each card's length, it also says how many beats there
are and which one is running — so the bar is a picture of the edit rather
than a stopwatch laid over it. Chilli for played, rule for pending.

**The sparkline appears twice.** Small in the masthead, where it is a mark
saying "this is a trend", and large on the closing card, where it is the
subject. The small one fades out as the closing card arrives: two charts on
screen at once is the same thing said twice.

**Captions are burned in, and they are not optional.** Most reels play muted,
so a reel whose argument lives only in the voiceover is a reel nobody hears.
Burned in rather than left to the platform: auto-captions mangle "two crore"
and are not there at all on a download.

One sentence at a time, cut from the voice's own sentence timings rather than
from a guess — so they are in step with the narration by construction, like
everything else here. They sit in the bottom third between the card band and
the footer, on a white block with the brand colour down the left edge. A block
rather than bare type because captions are read at a glance on a small screen,
and the grain and the sparkline both pass behind that band. The brand colour
is the one place in a frame where a brand's own colour appears.

A sentence holds until the next one starts, not for the length the voice
service reports. The gap between two sentences is a pause in the delivery, not
a moment with nothing being said, and a caption that blinks out during a
breath reads as a glitch.

**Indic scripts are where text filtering goes wrong.** Anything that reaches
the voice or the captions is cleaned first — hashtags, URLs and emoji read
aloud as "hash Goa A I" and a minute of letters. The obvious way to write that
filter is `str.isalnum()`, and it is wrong: `isalnum()` is False for every
combining mark, so Devanagari matras and Tamil vowel signs are stripped and
"लोग यह जानना चाहते हैं" becomes "लग यह जनन चहत ह" — not a typo but a
different set of words, spoken aloud and burned into the frame. Combining
marks have to be named by Unicode category. This has now been got wrong twice
in this codebase, once in topic normalisation and once here.

**Paper has tooth.** A flat field at 1080px reads as a screenshot of a text
editor, and it is where banding shows up first under social-platform
compression. The grain is a 160px tile of fixed-seed noise at 4%, multiplied
over everything including the type — baked as a tiled SVG rather than a
full-screen filter, which would be re-evaluated on all 360 frames.

**Motion.** One move: type arrives from just below and settles, line by line
with a three-frame stagger, and leaves the same way. Rules wipe across. The
closing sparkline draws itself in and its end dot lands with a spring —
springs where something arrives, interpolation where something travels.
Nothing zooms, spins, bounces or animates letter by letter. A reel is read in
six seconds on a phone, so the motion has to get out of the way of the
reading.

**The rag is balanced.** Greedy wrapping fills each line to the edge and
leaves the remainder on the last one, which at display sizes gives "Goa has /
an AI / policy" — one full line and two stubs. The box is narrowed until it is
about to need an extra line, which spreads the words evenly. `text-wrap:
balance` would do the same thing but cannot be used here, because each line is
its own element so it can animate separately.

**Leading is a per-script number.** 1.05 in Bricolage, 1.32 in the Noto Indic
faces. Tamil and Devanagari stack marks above and below the base character, so
the Latin value has one line sitting on top of the next.

**Rule position tells you which card you are on.** Chilli above the headline
on the opening card, accent below the line on a beat. That is how the opening
reads as the opening without a label saying so.

**Length is decided by the voiceover.** Every card is narrated on its own, the
audio is measured with ffprobe, and that measurement becomes the card's
length — so the cut rhythm of a reel is the rhythm of the sentences, not a
grid the copy has to fit. A card holds a third of a second past its last
syllable before cutting; without that the edit lands on the final word and
sounds like the file was truncated.

The other order — render to a fixed length, then attach audio — gives you a
choice between a clipped last sentence and a held frame at the end, and both
read as a broken render.

**The card and the voice say the same thing differently.** The card carries
`₹2 crore` because it is read; the voice carries "two crore rupees" because it
is heard, and a text-to-speech voice reads exactly what it is given. Both come
from one model call, so they cannot drift. Hashtags, URLs and emoji are
stripped from anything spoken: read aloud, `#GoaAI` is "hash Goa A I".

**Music is optional and never on top.** The bed is cut to -18 dB and ducked
under the narration by a compressor keyed on the voice, because a flat gain
that sits politely under one sentence will fight the next quieter one. The
pack ships empty — a reel with a clear voice and no music is fine.

## Platforms (step 4)

One row per platform per topic in `trend_sources`, and hashtags stored per
platform rather than pooled. `#AskIndia` means nothing on Instagram and
`#cricketreels` means nothing in a YouTube description, so a merged list is
wrong everywhere it is used. The Desk's per-platform copy buttons only mean
something because the tags were never mixed.

What each platform can actually answer differs more than the symmetry of the
table suggests:

| Platform | Discovers topics | Ranks them | Notes |
| --- | --- | --- | --- |
| Google Trends | yes | yes | only source reporting search volume; rising queries come free with `trending_now` |
| Google News | yes | yes | recency, not velocity |
| YouTube | yes | yes | six charts — the overall one is mostly music and film |
| Reddit | yes | yes | `hot` + `rising`; subreddit map is unverified, see the adapter |
| X | yes | yes | paid per request; credits exhausted, on fixtures |
| Instagram | **no** | **no** | no trending endpoint exists; measures named hashtags only |

### What curation costs, and why the batch is five

Measured 2026-10-28, when both providers ran out at once and the board spent
an evening falling back to source titles.

The curator is the expensive part of the pipeline and neither free tier is
sized for it. Gemini's is 20 generate calls per model per day — the model
chain exists to multiply that — and its embedding endpoint shares the same
quota, so when it goes, clustering degrades to title matching at the same
moment the descriptions do.

Groq as spillover is limited by tokens, not calls. `GROQ_RPM` throttles
requests; the ceiling that actually bites is 8,000 tokens a minute, and
`gpt-oss-120b` is a reasoning model whose output is mostly thinking:

| | tokens |
| --- | --- |
| prompt, 5 clusters | 2,441 |
| output | 5,000 |
| **total, one batch** | **7,441 of an 8,000-token minute** |

So spillover is comfortable for a single post and runs at roughly one batch
a minute for bulk curation — about ten minutes a region. Pacing it properly
(see `groq_output_reserve`) stops the 429s; it cannot make it fast. The fix
for a full re-curation is quota, not tuning.

`CURATE_BATCH_SIZE` is 5 rather than 10 because v3 adds `platform_hashtags`,
`why_trending` and `relevance_to_region` to every cluster, and ten of those
overran Groq's default completion cap. A truncated array is reported as
"Failed to validate JSON. Please adjust your prompt", which reads as a
prompt problem and is a length one.

Practical consequence: a long curate belongs on the Celery queue
(`curate_regions.delay([...])`), not in a foreground shell that an
interruption will kill halfway.

### Instagram runs on demand, never on the cycle

Decided 2026-10-27. `ig_hashtag_search` allows **30 unique hashtags per
Business account per rolling seven days** — not 30 calls, 30 distinct tags —
so measuring a 20-row board once would spend two thirds of a week.

So: `measure()` runs only when a user opens a topic in the Desk, for that
topic's primary curator hashtag plus at most two more. Results cache for
seven days, matching the window the limit is counted over. Until a topic has
been opened the Desk shows **"Instagram: not measured yet"**, which is an
honest third state — distinct from "measured, and it is small". Nothing
measures on the ingest cycle.

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
and any content job hanging off it is stranded.

Rows are therefore matched across runs on `member_keys` — the set of source
items (`source + URL`, or a hash of the keyword where there is no URL) the
topic has ever contained. One shared article is proof two rows are one story;
nothing a model writes can change that. A run where the coverage turned over
completely falls back to centroid cosine above 0.9 — far above the 0.68 used
for grouping, because this decides identity rather than similarity — and
exact title is the last resort. The centroid is kept as a moving average, so
identity drifts with the story instead of snapping to the newest headline.

Where several rows match, earlier runs forked one story: they are merged into
the one with the largest overlap, which takes their content jobs, their member
keys and the longer velocity history. A row carrying a post that matches
nothing keeps its row at rank 0 and logs a warning — it is never silently
replaced by a parallel row.

Measured on the live Goa board: with no member keys, 15 of a 28-row board
landed on existing rows. With them, 31 of 35 did, 19 forked rows were folded
away, and the topics carrying a generated post went from 3 of 8 rows on the
board to 5 of 5.
