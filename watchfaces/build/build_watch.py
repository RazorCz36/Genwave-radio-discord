#!/usr/bin/env python3
"""Assemble the final WatchMaker .watch package for the
TAG Heuer Carrera Chronograph x Porsche 963 (CBU2010.FT6267).

Pipeline
  1. plate5.py extracts a hand-free dial plate + hand sprites from the photo
     (input: source/cbu2010-ft6267.jpg, override with $WATCH_SRC)
  2. this script trims/masks them to the 512-unit WatchMaker canvas
  3. watch.xml is generated with live time / chrono / date bindings
  4. everything is zipped into  Carrera_Porsche963.watch
"""
import math
import os
import shutil
import subprocess
import sys
import zipfile
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("WATCH_WORK", "/tmp/out/final")
DELIVER = os.path.dirname(HERE)          # .../watchfaces

SCALE = 2.6
# WatchMaker on the wrist drops any bitmap whose pixel size differs from the
# layer's declared width/height (the desktop editor silently rescales, the watch
# does not), so every asset is authored at exactly the size written into the XML.
PLATE_PX = 512
CX, CY = 290.6, 535.4
CASE_R = 286.0
CROP_FRAC = 0.695        # of the case radius: just inside the big marker ring, so the
                         # face keeps its own fine minute track and nothing else
DIAL_R = CASE_R * CROP_FRAC   # plate5 crops here, so 512 units span this radius
UI = 0.82 / CROP_FRAC    # text/offset scale against the previous 0.82 crop

# WatchMaker canvas is 512 x 512; the case circle (r = 256) fills it.
U_PER_CROP_PX = 512.0 / (DIAL_R * 2 * SCALE)

# hand geometry (source-photo pixels) -------------------------------------------------
HANDS = {
    "minute": dict(axis=59.0, r_in=-26.0, r_out=204.0, w_near=11.0, w_far=8.0),
    "hour":   dict(axis=329.0, r_in=-24.0, r_out=147.0, w_near=12.5, w_far=9.5),
    "chrono": dict(axis=223.0, r_in=-44.0, r_out=224.0, w_near=7.5, w_far=5.0),
}
REGS = [(186.0, 535.5, 75.0), (398.5, 535.5, 75.0), (292.0, 641.0, 70.0)]
# date aperture centre (source px) -> units relative to the dial centre
DATE_CX, DATE_CY = 291.5, 691.5
DATE_U = ((DATE_CX - CX) / DIAL_R * 256.0, (DATE_CY - CY) / DIAL_R * 256.0)
DATE_FONT = "sairasemibold"   # WFF-safe resource name (lowercase)
DATE_SIZE = 22        # two digits must still fit the narrow aperture

# register centres in units, relative to the dial centre
REG_UNITS = [((x - CX) / DIAL_R * 256.0, (y - CY) / DIAL_R * 256.0) for x, y, _ in REGS]


def run(cmd):
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- plate
def make_plate():
    """Square RGBA plate: case circle exactly fills the canvas, transparent outside."""
    src = Image.open(os.path.join(WORK, "plate_crop.png")).convert("RGB")
    n = src.size[0]
    px = PLATE_PX
    src = src.resize((px, px), Image.LANCZOS)
    a = np.asarray(src).astype(np.uint8)

    yy, xx = np.mgrid[0:px, 0:px].astype(np.float32)
    c = (px - 1) / 2.0
    r = np.hypot(xx - c, yy - c)
    edge = px / 2.0
    alpha = np.clip((edge - r) / 1.6, 0, 1) * 255.0

    # Opaque RGB, saved as JPEG.
    # Two suspects were left for the Watch Face Format conversion dropping every
    # bitmap in this face but carrying the probe face's picture: the transparent
    # alpha channel (the probe image was opaque) and the file size (the probe was
    # 9 KB, this plate 362 KB).  An opaque 512 px JPEG removes both at once; the
    # round screen clips the corners anyway.
    a = a.copy()
    a[alpha < 128] = 0
    Image.fromarray(a, "RGB").save(os.path.join(WORK, "images", "dial.jpg"),
                                   quality=92, subsampling=0)

    return px



# ---------------------------------------------------------------- hand sprites
def _steel_gradient(size, stops):
    """Horizontal polish bevel: dark edge, bright centre, dark edge."""
    from PIL import ImageDraw as _D
    g = Image.new("RGB", (size, 1))
    d = _D.Draw(g)
    for x in range(size):
        t = x / max(size - 1, 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(t1 - t0, 1e-6)
                col = tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
                d.point((x, 0), fill=col)
                break
    return g.resize((size, size))


STEEL = [(0.00, (58, 62, 67)), (0.10, (138, 145, 152)), (0.26, (216, 222, 228)),
         (0.46, (240, 244, 248)), (0.56, (198, 204, 210)), (0.78, (156, 163, 170)),
         (0.90, (184, 190, 196)), (1.00, (52, 57, 62))]
RED = [(0.00, (118, 8, 14)), (0.20, (198, 28, 34)), (0.50, (247, 66, 66)),
       (0.74, (200, 26, 32)), (1.00, (104, 6, 12))]


def make_hand(path, length, tail, w_near, w_far, stops, hub_r=0.0, hub_stops=None,
              facet=0.0, facet_col=(18, 20, 23), tip=0.0):
    """Draw one complete hand pointing up with its pivot in the middle.

    The photo-derived sprites could not be cut out cleanly (the hands are skeleton
    rails over a busy dial), so a solid hand is drawn in their measured geometry.
    """
    from PIL import ImageDraw as _D
    SS = 3
    side = int(2 * math.ceil(max(length, tail) + hub_r + 3))
    S = side * SS
    c = S / 2.0
    L = length * SS
    WN, WF = w_near * SS, w_far * SS
    y0 = c + 2.0 * SS

    def blade(scale_w):
        n, f = WN * scale_w, WF * scale_w
        nose = c - L + max(WF * 0.9, 2.0 * SS)
        return [(c - n / 2, c - 0.14 * L), (c - f / 2, nose),
                (c, c - L), (c + f / 2, nose), (c + n / 2, c - 0.14 * L),
                (c + n / 2, y0), (c - n / 2, y0)]

    mask = Image.new("L", (S, S), 0)
    d = _D.Draw(mask)
    d.polygon(blade(1.0), fill=255)
    if tail > 2:
        t = tail * SS
        d.polygon([(c - WN * 0.38, c), (c - WN * 0.22, c + t),
                   (c + WN * 0.22, c + t), (c + WN * 0.38, c)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(SS * 0.30))

    edge = mask.filter(ImageFilter.MaxFilter(2 * int(SS * 0.55) + 1))
    sprite = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sprite.paste(Image.new("RGBA", (S, S), (10, 11, 13, 255)), (0, 0),
                 edge.point(lambda v: int(v * 0.85)))
    sprite.paste(_steel_gradient(S, stops), (0, 0), mask)

    if facet > 0:
        fm = Image.new("L", (S, S), 0)
        _D.Draw(fm).polygon(blade(facet), fill=255)
        fm = fm.filter(ImageFilter.GaussianBlur(SS * 0.28))
        fm = fm.point(lambda v: int(v * 0.92))
        sprite.paste(Image.new("RGBA", (S, S), facet_col + (255,)), (0, 0), fm)

    if tip > 0:                              # lume-tipped point, like the photo
        tm = Image.new("L", (S, S), 0)
        _D.Draw(tm).polygon(blade(tip), fill=255)
        tm = tm.filter(ImageFilter.GaussianBlur(SS * 0.26))
        cut = c - L + 0.14 * L                # only the far end of the blade
        arr = np.asarray(tm).copy()
        arr[:int(cut)] = 0
        tm = Image.fromarray(arr, "L")
        sprite.paste(Image.new("RGBA", (S, S), (247, 249, 251, 255)), (0, 0), tm)

    if hub_r > 0:
        hr = hub_r * SS
        hm = Image.new("L", (S, S), 0)
        _D.Draw(hm).ellipse([c - hr, c - hr, c + hr, c + hr], fill=255)
        hm = hm.filter(ImageFilter.GaussianBlur(SS * 0.22))
        hub = _steel_gradient(int(2 * hr), hub_stops or STEEL).resize((S, S))
        sprite.paste(hub, (0, 0), hm)
        ring = Image.new("L", (S, S), 0)
        _D.Draw(ring).ellipse([c - hr, c - hr, c + hr, c + hr],
                              outline=255, width=max(1, int(SS * 1.1)))
        sprite.paste(Image.new("RGBA", (S, S), (48, 52, 56, 255)), (0, 0),
                     ring.point(lambda v: int(v * 0.55)))

    sprite = sprite.resize((side, side), Image.LANCZOS)
    sprite.save(path)
    return side


def build_hands():
    """Hand geometry straight from the photo, expressed in canvas units."""
    k = 512.0 / (2.0 * DIAL_R)
    out = []
    for name, kind in (("hand_hour.png", "hour"), ("hand_minute.png", "minute"),
                       ("hand_second.png", "chrono")):
        h = HANDS[kind]
        red = kind == "chrono"
        r_out = min(h["r_out"], DIAL_R * (0.88 if red else 0.90))
        side = make_hand(os.path.join(WORK, "images", name),
                         length=r_out * k, tail=abs(h["r_in"]) * k,
                         w_near=h["w_near"] * k * (0.58 if red else 1.22),
                         w_far=h["w_far"] * k * (0.58 if red else 1.22),
                         stops=RED if red else STEEL,
                         hub_r=(6.0 if red else 9.5),
                         hub_stops=[(0.0, (118, 123, 128)), (0.42, (236, 241, 245)),
                                    (0.60, (206, 212, 218)), (1.0, (104, 109, 114))],
                         facet=0.0 if red else 0.70,
                         tip=0.0 if red else 0.34)
        out.append((name, side))
    return out


# ---------------------------------------------------------------- hands
def trim_hand(path, out_path):
    """Crop a hand sprite to its alpha bbox, keep the pivot centred.

    Returns (side, extent): `side` is the square crop size in sprite pixels and
    `extent` the distance from the pivot to the furthest opaque pixel. WatchMaker
    needs the layer width such that `extent` lands exactly on the measured hand
    length, so width = side * r_out_units / extent.
    """
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)
    n = a.shape[0]
    c = n / 2.0
    alpha = a[:, :, 3]
    ys, xs = np.nonzero(alpha > 8)
    if len(xs) == 0:
        im.save(out_path)
        return n, c
    ex = max(abs(xs.min() - c), abs(xs.max() - c))
    ey = max(abs(ys.min() - c), abs(ys.max() - c))
    half = int(math.ceil(max(ex, ey) + 2))
    x0 = int(round(c - half)); y0 = int(round(c - half))
    box = (max(x0, 0), max(y0, 0), min(x0 + half * 2, n), min(y0 + half * 2, n))
    crop = im.crop(box)
    # keep the pivot exactly centred (pad if the crop was clipped)
    side = max(crop.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(crop, ((side - crop.size[0]) // 2, (side - crop.size[1]) // 2))
    canvas.save(out_path)
    extent = max(abs(xs.min() - c), abs(xs.max() - c), abs(ys.min() - c), abs(ys.max() - c))
    return side, float(extent)


SPRITE = {}          # sprite name -> (side px, alpha extent px)
HAND_LAYER = {}      # hand kind -> declared layer size in 512-units (== sprite px)


def layer_w(kind, r_out=None):
    """Layer width in 512-units that puts the sprite tip exactly at the measured radius."""
    if kind in HAND_LAYER:
        return float(HAND_LAYER[kind])
    if kind == "reg":
        side, ext = SPRITE["reg_hand_red.png"]
        return side * (0.93 * r_out) / DIAL_R * 256.0 / ext
    if kind == "reg2":
        side, ext = SPRITE["reg_hand_red2.png"]
        return side * (0.93 * r_out) / DIAL_R * 256.0 / ext
    if kind == "regb":
        side, ext = SPRITE["reg_hand_steel.png"]
        return side * (0.93 * r_out) / DIAL_R * 256.0 / ext
    side, ext = SPRITE[SPRITE_NAME[kind]]
    return side * (HANDS[kind]["r_out"] / DIAL_R * 256.0) / ext


SPRITE_NAME = {"hour": "hand_hour.png", "minute": "hand_minute.png",
               "chrono": "hand_chrono.png"}


def fit_hands():
    """Resample every hand sprite so its pixel size equals its declared layer size.

    The sprite is square with the pivot at its centre. Drawing it as a layer of
    width W gives a scale of W/side, so the visible tip sits at extent*W/side;
    we want that to equal the measured radius, which fixes W. Once W is known the
    bitmap is resampled to exactly W px, so declaration and texture agree.
    """
    for kind, img in (("hour", "hand_hour.png"), ("minute", "hand_minute.png"),
                      ("chrono", "hand_second.png")):
        name = SPRITE_NAME[kind]
        target = int(round(layer_w(kind)))
        side, ext = SPRITE[name]
        path = os.path.join(WORK, "images", img)
        im = Image.open(path).convert("RGBA").resize((target, target), Image.LANCZOS)
        im.save(path)
        SPRITE[name] = (target, ext * target / side)
        HAND_LAYER[kind] = target
        print(f"    {img}: {side}px -> {target}px (layer width {target})")


# ---------------------------------------------------------------- xml
def text_layer(name, x, y, text, size, color, color_dim, opacity="100", extra=""):
    return (f'    <Layer name="{escape(name)}" type="text" x="{x:.2f}" y="{y:.2f}" gyro="0" '
            f'rotation="0" skew_x="0" skew_y="0" opacity="{opacity}" alignment="cc" '
            f'text="{escape(text)}" text_size="{size}" anim_scale_x="100" anim_scale_y="100" '
            f'font="{DATE_FONT}" transform="n" color="{color}" color_dim="{color_dim}" '
            f'display="bd"{extra}/>')


def shape_layer(name, x, y, w, h, color, opacity):
    return (f'    <Layer name="{escape(name)}" type="shape" x="{x:.2f}" y="{y:.2f}" gyro="0" '
            f'rotation="0" skew_x="0" skew_y="0" opacity="{opacity}" alignment="cc" '
            f'shape="Circle" width="{w:.1f}" height="{h:.1f}" color="{color}" display="bd"/>')


def watch_xml():
    def img_layer(name, path, size, rot="0", opacity="100", extra=""):
        return (f'    <Layer name="{escape(name)}" type="image" x="0" y="0" gyro="0" '
                f'rotation="{rot}" skew_x="0" skew_y="0" opacity="{opacity}" alignment="cc" '
                f'path="{path}" width="{size}" height="{size}" color="ffffff" display="bd"{extra}/>')

    # hand layer sizes in units (image spans 2*S units around the pivot)
    def span_units(r_in, r_out):
        return abs(max(abs(r_in), r_out)) / CASE_R * 256.0 * 2.0 * 1.0

    lines = []
    lines.append('<?xml version="1.0" encoding="utf-8"?>')
    lines.append(
        '<Watch name="Carrera x Porsche 963" '
        'description="TAG Heuer Carrera Chronograph x Porsche 963 (CBU2010.FT6267). '
        'Photo-faithful dial, carbon tachymeter bezel, live chronograph and date." '
        'features="12h Time,Analog,Date,Smooth Seconds,Battery Level,Step Counter,Weather" '
        'shape="R" author="Arena Agent" web_link="" bg_color="000000" '
        'ucolor_default="ffffff" ind_loc="bc" ind_bg="Y" hotword_loc="bc" hotword_bg="N">')

    # background plate: bright version for bright mode, lifted version for ambient
    lines.append(img_layer("dial", "dial.jpg", 512, opacity="100"))

    # sub-dial readouts: battery / steps / weather replace the chrono registers.
    # A soft black disc knocks the printed 1-12 / 5-30 scales back so the numbers read.
    for cap, tag, _sample, cu, size_cap, size_val in READOUTS:
        x, y = REG_UNITS[cu]
        lines.append(text_layer(f"{cap.lower()} value", x, y + 10 * UI, tag,
                                int(round(size_val * UI)), "f4f6f8", "c9ced3"))
        lines.append(text_layer(f"{cap.lower()} label", x, y - 26 * UI, cap,
                                int(round(size_cap * UI)), "9aa0a6", "7c8288"))

    # date window (dynamic)
    lines.append(text_layer("date", DATE_U[0], DATE_U[1], "{dd}", DATE_SIZE,
                            "101215", "101215"))

    # hands last so they pass over the dial printing
    lines.append(img_layer("hour hand", "hand_hour.png", int(round(layer_w("hour"))), rot="{drh}"))
    lines.append(img_layer("minute hand", "hand_minute.png", int(round(layer_w("minute"))), rot="{drm}"))
    lines.append(img_layer("chrono seconds", "hand_second.png", int(round(layer_w("chrono"))), rot="{drss}"))

    lines.append('</Watch>')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- preview
READOUTS = [
    # caption, tag, sample value (preview only), register index, caption size, value size
    ("BATTERY", "{blp}", "87%", 0, 9, 24),
    ("STEPS", "{ssc}", "6420", 1, 9, 22),
    ("WEATHER", "{wtd}", "12\u00b0C", 2, 9, 21),
]


def compose_preview(plate, hand_alpha=1.0):
    """Composite the face the way WatchMaker does, from the packaged assets."""
    from PIL import ImageDraw, ImageFont
    W = 512
    bg = Image.open(os.path.join(WORK, "images", plate)).convert("RGBA").resize(
        (W, W), Image.LANCZOS)
    flat = Image.new("RGBA", (W, W), (0, 0, 0, 255))
    flat.alpha_composite(bg)
    bg = flat
    base = Image.new("RGBA", (W, W), (0, 0, 0, 255))
    base.alpha_composite(bg)

    # sub-dial readouts under the hands, same geometry as the layers
    d = ImageDraw.Draw(base)
    font_path = os.path.join(WORK, "fonts", "sairasemibold.ttf")
    for cap, _tag, val, cu, size_cap, size_val in READOUTS:
        x, y = REG_UNITS[cu]
        px = W / 2 + x * W / 512.0
        f_cap = ImageFont.truetype(font_path, int(round(size_cap * UI)))
        f_val = ImageFont.truetype(font_path, int(round(size_val * UI)))
        d.text((px, W / 2 + (y + 10 * UI) * W / 512.0), val, font=f_val,
               fill=(0xf4, 0xf6, 0xf8), anchor="mm")
        d.text((px, W / 2 + (y - 26 * UI) * W / 512.0), cap, font=f_cap,
               fill=(0x9a, 0xa0, 0xa6), anchor="mm")

    # date
    f = ImageFont.truetype(font_path, DATE_SIZE)
    d.text((W / 2 + DATE_U[0] * W / 512.0, W / 2 + DATE_U[1] * W / 512.0), "8",
           font=f, fill=(0x10, 0x12, 0x15), anchor="mm")

    # hands
    def place(path, size, angle):
        im = Image.open(os.path.join(WORK, "images", path)).convert("RGBA")
        s = max(1, int(round(size * W / 512.0)))
        im = im.resize((s, s), Image.LANCZOS)
        if hand_alpha < 1.0:
            a = im.getchannel("A").point(lambda v: int(v * hand_alpha))
            im.putalpha(a)
        im = im.rotate(-angle, resample=Image.BICUBIC, expand=False)
        layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        layer.paste(im, ((W - s) // 2, (W - s) // 2), im)
        base.alpha_composite(layer)

    place("hand_hour.png", layer_w("hour"), 300)
    place("hand_minute.png", layer_w("minute"), 60)
    place("hand_second.png", layer_w("chrono"), 42)
    return base


def make_preview():
    """Bright preview + an ambient preview that mirrors what the watch shows in dim mode."""
    bright = compose_preview("dial.jpg", 1.0)
    bright.convert("RGB").save(os.path.join(WORK, "preview.jpg"), quality=92)

    # ambient: lifted plate, hands at 80 %, then the system dimming on top
    dim = compose_preview("dial.jpg", 1.0).convert("RGB").point(lambda v: int(v * 0.62))
    dim.save(os.path.join(WORK, "preview_dim.jpg"), quality=92)


# ---------------------------------------------------------------- package
def verify_package(path):
    """Fail the build if any declared layer size disagrees with its bitmap."""
    import io
    import re
    with zipfile.ZipFile(path) as z:
        xml = z.read("watch.xml").decode()
        bad = []
        for tag in re.findall(r"<Layer[^>]*type=\"image\"[^>]*/>", xml):
            src = re.search(r'path="([^"]+)"', tag).group(1)
            w = float(re.search(r'width="([\d.]+)"', tag).group(1))
            h = float(re.search(r'height="([\d.]+)"', tag).group(1))
            size = Image.open(io.BytesIO(z.read(f"images/{src}"))).size
            if size != (w, h):
                bad.append((src, size, (w, h)))
            print(f"    {src:11s} {size[0]:4d}x{size[1]:<4d} declared {w:.0f}x{h:.0f}")
        if "{abright}" in xml:
            bad.append(("{abright}", "expression", "bare opacity"))
    if bad:
        raise SystemExit(f"layer/bitmap mismatch: {bad}")
    print("    all image layers match their declarations")


def package():
    out = os.path.join(DELIVER, "Carrera_Porsche963.watch")
    os.makedirs(DELIVER, exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(os.path.join(WORK, "watch.xml"), "watch.xml")
        for f in sorted(os.listdir(os.path.join(WORK, "images"))):
            z.write(os.path.join(WORK, "images", f), f"images/{f}")
        fdir = os.path.join(WORK, "fonts")
        for f in sorted(os.listdir(fdir)):
            z.write(os.path.join(fdir, f), f"fonts/{f}")
        z.write(os.path.join(WORK, "preview.jpg"), "preview.jpg")
        z.write(os.path.join(WORK, "preview_dim.jpg"), "preview_dim.jpg")
    return out


def main():
    os.makedirs(os.path.join(WORK, "images"), exist_ok=True)
    os.makedirs(DELIVER, exist_ok=True)

    print("[1/6] extracting plate and hand sprites from the photo")
    run([sys.executable, os.path.join(HERE, "plate5.py"), WORK, str(SCALE)])

    print("[2/6] building plate layers + bundled font")
    os.makedirs(os.path.join(WORK, "fonts"), exist_ok=True)
    shutil.copy(os.path.join(HERE, "fonts", "SairaSemi.ttf"),
                os.path.join(WORK, "fonts", "sairasemibold.ttf"))
    make_plate()

    print("[3/6] trimming hand sprites")
    for stale in (".img1.png", ".img2.png", ".img3.png", ".img4.png", ".img5.png",
                  ".img6.png", ".img7.png", ".img8.png", "dial.png"):
        f = os.path.join(WORK, "images", stale)
        if os.path.exists(f):
            os.remove(f)
    for name, side in build_hands():
        HAND_LAYER[name.replace("hand_", "").replace(".png", "")] = side
        if name == "hand_second.png":
            HAND_LAYER["chrono"] = side
        print("   ", name, side, "px")

    print("[3b/6] hand sprites drawn at their declared layer size")

    print("[4/6] writing watch.xml")
    with open(os.path.join(WORK, "watch.xml"), "w", encoding="utf-8") as f:
        f.write(watch_xml())

    print("[5/6] rendering previews")
    make_preview()

    print("[6/6] packaging .watch")
    out = package()

    print("[6b/6] verifying layer sizes against the packaged bitmaps")
    verify_package(out)
    print("done ->", out, os.path.getsize(out) // 1024, "KiB")


if __name__ == "__main__":
    main()
