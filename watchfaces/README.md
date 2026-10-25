# TAG Heuer Carrera Chronograph × Porsche 963 — WatchMaker face

`Carrera_Porsche963.watch` is a ready-to-import WatchMaker watch face built from a
photograph of the **CBU2010.FT6267** (Carrera Chronograph x Porsche 963).

![preview](preview.jpg)

Three moments of the live face (`mockup.jpg`) — hands, chrono registers and date all
driven by the tags in the table below:

![mockup](mockup.jpg)

## Import

1. Copy `Carrera_Porsche963.watch` to your phone.
2. Open **WatchMaker**, tap **+ → Import** (or *My Watches → ⋮ → Import*) and pick the file.
3. Save it as your watch face, then send it to the watch as usual.

WatchMaker Studio can open the same file on desktop (*File → Import .watch*).

## What is live

| Element | Binding |
| --- | --- |
| Hour / minute hands | `{drh}` / `{drm}` |
| Central red chronograph seconds | `{drss}` (smooth) |
| 9 o'clock dial | **battery** — `{blp}` (e.g. `87%`) |
| 3 o'clock dial | **steps** — `{ssc}` |
| 6 o'clock dial | **weather** — `{wtd}` (e.g. `12°C`) |
| Date aperture | `{dd}` in a bundled Saira SemiBold |

**Dial only, no bezel.** The plate is cropped at 0.82 of the case radius, so the carbon
tachymeter bezel and its `PORSCHE 400 / 300 / 240 …` print are gone and the dial itself
fills the screen (the whole face scales up by 286/234 ≈ 1.22). All unit constants derive
from `DIAL_R`, so hands, registers and the date move with the crop automatically.

**Registers are repainted, then re-printed.** Each sub-dial interior is wiped to a clean
black disc (0.97 of its radius) and a regular 60-tick scale is drawn back procedurally —
the photo's own scale sat under the removed register hands and carried a bright "erased
hand" blade across the top of every ring. The 6 o'clock ring skips the ticks that would
cross the date aperture.

The tick scale is pushed out to the rim so each caption has clear black under it, and the
readouts are sized to still fit if WatchMaker draws text larger than the nominal
`text_size` (`TEXT_SCALE=1.35 python3 mockup.py out.jpg` renders that pessimistic case).

**Hands are drawn, not cut out of the photo.** The first hand sprites were cut from the
photograph along a straight swath, so each sprite kept an opaque, flat-edged rectangle
around the blade. Whenever the minute hand swept over the 3 o'clock register that
rectangle landed across it as a pale grey bar under the STEPS caption — the "erased hand"
in the bug reports. The real Carrera hands are openworked: two polished rails with a dark
centre and a pointed lume tip, and a hollow centre cannot be reproduced by pasting a
rectangle. `build_watch.py` therefore draws them in the photo's measured geometry
(`HANDS`): silhouette, bevel gradient, dark centre facet, lume tip, hub and dark rim, at
three-times supersampling, then sizes every sprite to exactly the layer width it is
declared with. Nothing but the hand itself has any alpha, so a hand can pass over a
register without disturbing it.

The printed scales inside the three small dials are **erased in the plate itself**
(the interiors are repainted as clean black discs with matched grain), so each readout
sits on plain black in the centre of its ring — no overlay disc is used. The 6 o'clock
repaint deliberately stops short of the date aperture so the printed cream window and
its black frame survive.

**One plate, one mode.** Wear OS 6 (One UI 8) no longer runs legacy WatchMaker faces: the
phone app converts a `.watch` to Google's **Watch Face Format (WFF)** on *send to watch*.
The converter is lossy and a bright/dim pair of plates doubles the work it has to do, so
the face ships a single `dial.png` with `display="bd"` and lets the platform render ambient
itself. Assets are plain, lowercase, extension-bearing resource names (`dial.png`,
`hand_hour.png`, `hand_second.png`, `fonts/sairasemibold.ttf`) because WFF resource names
must match `[a-z0-9_]+` — the old `.img1.png` dot-names are exactly the kind of thing that
gets dropped in conversion.

**The plate is an opaque JPEG.** A first probe face — 512 px, opaque RGB PNG, one image
and one text layer — converted and displayed perfectly on a Galaxy Watch 6 Classic, while
this face's RGBA PNG plate and hand sprites vanished. So the conversion handles at least
one image; the question is which property it chokes on. `dial.jpg` is therefore fully
opaque (corners blacked out, the round screen clips them) and 512 px at ~97 KB.

`WatchFaceTest.watch` narrows that down in one send:

| Mark | Layer | Property under test |
| --- | --- | --- |
| background | the real 362 KB RGBA plate, 512 px | survives at all? |
| **A** | RGB PNG, 120 px | control |
| **B** | RGBA PNG with transparency | alpha channel |
| **D** | RGBA PNG, `rotation="{drm}"` | rotating image layers |
| **E** | JPEG, 120 px | file format |
| **F** | text, bundled font | font-backed text |

Whatever stays black is the property the converter destroys.

**Asset sizes are locked to the XML.** Store faces do declare sizes that differ from the
bitmap, but matching them costs nothing and removes one variable. The plate is 512 px and
declared 512; each hand sprite is 346 / 472 / 508 px and declared at exactly that width.
`build_watch.py` asserts this: every `path=` bitmap matches its declaration.

The same reason killed `opacity="{abright} and 100 or 80"` on hands and date — this build
resolves the expression to nothing and hides the layer, so all opacities are plain `100`.

`mockup.jpg` is a front-on render of the packaged face in a drawn case; `times.jpg` shows
the same package at three different times and dates (the hands, the chrono sweep and the
date all come from the live tags, nothing is baked in).

Swapping a readout is one edit in `build_watch.py` (`READOUTS`): e.g. `{pblp}` for the
phone battery, `{stsc}` for the step target, `{wct}` for the weather description.

## How it was made

The dial is **the original photograph**, not a redraw: every hand was cut out as an
RGBA sprite, the plate behind it was reconstructed, and the printed date digit was
erased so a real date can be drawn over the cream plate.

* `build/plate5.py` — builds the exact swath of every hand from the measured geometry,
  fills it by angular interpolation around the dial centre and around each sub-dial
  centre (so the skeleton bridges continue *around* the removed hand instead of being
  smeared across it), flattens the black register interiors with a per-radius percentile,
  adds matched grain, erases the printed day digit from the cream plate, and cuts the
  sprites with their pivot centred.
* `build/build_watch.py` — draws the three hand sprites in that geometry, crops the plate
  to the dial, writes `watch.xml`, renders `preview.jpg` / `preview_dim.jpg` and zips the
  `.watch`.

Render a still of the packaged face, or a device mockup:

```bash
python3 render_face.py out.png --time 22:47 --date 25 --chrono 1:42 --size 640
python3 mockup.py mockup.jpg
```

Rebuild (needs `opencv-python`, `numpy`, `Pillow`):

```bash
cd watchfaces/build
python3 build_watch.py            # writes ../Carrera_Porsche963.watch
```

`source/cbu2010-ft6267.jpg` is the reference photo; override with `$WATCH_SRC`, and
`$WATCH_WORK` to change the scratch directory (default `/tmp/out/final`).

## Known deviations from the photo

* The date window shows today's date in Saira SemiBold (text size 20) instead of the
  printed "8", so two-digit days fit the narrow aperture.
* The three chronograph registers became battery / steps / weather readouts, as asked.
* The hands are drawn in the photo's silhouette (two rails, dark openworked centre,
  pointed lume tip) rather than traced pixel by pixel, because the photo only shows them
  in one pose.
* The sliver of dial that sat under each hand was reconstructed; the dynamic hands
  cover those areas again in normal use.
* Hands are drawn at the photo's exact axes in `preview.jpg` only as a still pose.
