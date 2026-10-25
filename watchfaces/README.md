# TAG Heuer Carrera Chronograph × Porsche 963 — WatchMaker face

`Carrera_Porsche963.watch` is a ready-to-import WatchMaker watch face built from a
photograph of the **CBU2010.FT6267** (Carrera Chronograph x Porsche 963).

![preview](preview.jpg)

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
| 9 o'clock register — elapsed chrono **hours** (12 h) | `({swh}%12)*30 + {swm}*0.5` |
| 3 o'clock register — elapsed chrono **minutes** (30 min) | `({swm}%30)*12 + {sws}*0.2` |
| 6 o'clock register — running seconds | `{drss}` |
| Date aperture | text layer `{dd}`, Saira SemiBold, bundled |

Hands drop to 55 % opacity in ambient mode; the dial is a single full-resolution
image, dimmed by the system in dim mode.

## How it was made

The dial is **the original photograph**, not a redraw: every hand was cut out as an
RGBA sprite, the plate behind it was reconstructed, and the printed date digit was
erased so a real date can be drawn over the cream plate.

* `build/plate5.py` — measures the hand swaths, removes them (angular interpolation
  around the dial centre / sub-dial centres, flattens the black sub-dial interiors with
  a per-radius percentile, Telea in-paint for leftovers), erases the printed day digit,
  and cuts the hand sprites with the pivot centred.
* `build/build_watch.py` — trims the sprites, makes the 2048² circular plate,
  writes `watch.xml`, renders `preview.jpg` / `preview_dim.jpg` and zips the `.watch`.

Rebuild (needs `opencv-python`, `numpy`, `Pillow`):

```bash
cd watchfaces/build
python3 build_watch.py            # writes ../Carrera_Porsche963.watch
```

`source/cbu2010-ft6267.jpg` is the reference photo; override with `$WATCH_SRC`, and
`$WATCH_WORK` to change the scratch directory (default `/tmp/out/final`).

## Known deviations from the photo

* The date window shows today's date in Saira SemiBold (~20 units) instead of the
  printed "8", which was ~25 % larger but static.
* The sliver of dial that sat under each hand was reconstructed; the dynamic hands
  cover those areas again in normal use.
* Hands are drawn at the photo's exact axes in `preview.jpg` only as a still pose.
