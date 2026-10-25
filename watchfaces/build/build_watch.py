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
from PIL import Image

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

# WatchMaker canvas is 512 x 512; the case circle (r = 256) fills it.
U_PER_CROP_PX = 512.0 / (CASE_R * 2 * SCALE)

# hand geometry (source-photo pixels) -------------------------------------------------
HANDS = {
    "minute": dict(axis=59.0, r_in=-26.0, r_out=204.0, w_near=11.0, w_far=8.0),
    "hour":   dict(axis=329.0, r_in=-24.0, r_out=147.0, w_near=12.5, w_far=9.5),
    "chrono": dict(axis=223.0, r_in=-44.0, r_out=224.0, w_near=7.5, w_far=5.0),
}
REGS = [(186.0, 535.5, 75.0), (398.5, 535.5, 75.0), (292.0, 641.0, 70.0)]
# date aperture centre (source px) -> units relative to the dial centre
DATE_CX, DATE_CY = 291.5, 691.5
DATE_U = ((DATE_CX - CX) / CASE_R * 256.0, (DATE_CY - CY) / CASE_R * 256.0)
DATE_FONT = "SairaSemiBold"
DATE_SIZE = 20

# register centres in units, relative to the dial centre
REG_UNITS = [((x - CX) / CASE_R * 256.0, (y - CY) / CASE_R * 256.0) for x, y, _ in REGS]


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

    rgba = np.dstack([a, alpha.astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(os.path.join(WORK, "images", ".img1.png"))

    # ambient plate: the watch dims everything in dim mode, so ship a lifted copy
    f = a.astype(np.float32) / 255.0
    dim = np.clip((f ** 0.55) * 255.0, 0, 255).astype(np.uint8)
    dim_im = Image.fromarray(np.dstack([dim, alpha.astype(np.uint8)]), "RGBA")
    dim_im.save(os.path.join(WORK, "images", ".img2.png"))
    return px


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
        return side * (0.93 * r_out) / CASE_R * 256.0 / ext
    if kind == "reg2":
        side, ext = SPRITE["reg_hand_red2.png"]
        return side * (0.93 * r_out) / CASE_R * 256.0 / ext
    if kind == "regb":
        side, ext = SPRITE["reg_hand_steel.png"]
        return side * (0.93 * r_out) / CASE_R * 256.0 / ext
    side, ext = SPRITE[SPRITE_NAME[kind]]
    return side * (HANDS[kind]["r_out"] / CASE_R * 256.0) / ext


SPRITE_NAME = {"hour": "hand_hour.png", "minute": "hand_minute.png",
               "chrono": "hand_chrono.png"}


def fit_hands():
    """Resample every hand sprite so its pixel size equals its declared layer size.

    The sprite is square with the pivot at its centre. Drawing it as a layer of
    width W gives a scale of W/side, so the visible tip sits at extent*W/side;
    we want that to equal the measured radius, which fixes W. Once W is known the
    bitmap is resampled to exactly W px, so declaration and texture agree.
    """
    for kind, img in (("hour", ".img3.png"), ("minute", ".img4.png"),
                      ("chrono", ".img5.png")):
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
    lines.append(img_layer("dial", ".img1.png", 512, opacity="100", extra='').replace(
        'display="bd"', 'display="b"'))
    lines.append(img_layer("dial dim", ".img2.png", 512, opacity="100").replace(
        'display="bd"', 'display="d"'))

    # sub-dial readouts: battery / steps / weather replace the chrono registers.
    # A soft black disc knocks the printed 1-12 / 5-30 scales back so the numbers read.
    for cap, tag, _sample, cu, size_cap, size_val in READOUTS:
        x, y = REG_UNITS[cu]
        lines.append(text_layer(f"{cap.lower()} value", x, y + 7, tag, size_val,
                                "f4f6f8", "c9ced3"))
        lines.append(text_layer(f"{cap.lower()} label", x, y - 19, cap, size_cap,
                                "9aa0a6", "7c8288"))

    # date window (dynamic)
    lines.append(text_layer("date", DATE_U[0], DATE_U[1], "{dd}", DATE_SIZE,
                            "101215", "101215"))

    # hands last so they pass over the dial printing
    lines.append(img_layer("hour hand", ".img3.png", int(round(layer_w("hour"))), rot="{drh}"))
    lines.append(img_layer("minute hand", ".img4.png", int(round(layer_w("minute"))), rot="{drm}"))
    lines.append(img_layer("chrono seconds", ".img5.png", int(round(layer_w("chrono"))), rot="{drss}"))

    lines.append('</Watch>')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- preview
READOUTS = [
    # caption, tag, sample value (preview only), register index, caption size, value size
    ("BATTERY", "{blp}", "87%", 0, 9, 24),
    ("STEPS", "{ssc}", "6420", 1, 9, 22),
    ("WEATHER", "{wtd}", "12\u00b0C", 2, 8, 21),
]


def compose_preview(plate, hand_alpha=1.0):
    """Composite the face the way WatchMaker does, from the packaged assets."""
    from PIL import ImageDraw, ImageFont
    W = 512
    bg = Image.open(os.path.join(WORK, "images", plate)).convert("RGBA").resize(
        (W, W), Image.LANCZOS)
    base = Image.new("RGBA", (W, W), (0, 0, 0, 255))
    base.alpha_composite(bg)

    # sub-dial readouts under the hands, same geometry as the layers
    d = ImageDraw.Draw(base)
    font_path = os.path.join(WORK, "fonts", "SairaSemiBold.ttf")
    for cap, _tag, val, cu, size_cap, size_val in READOUTS:
        x, y = REG_UNITS[cu]
        px = W / 2 + x * W / 512.0
        f_cap = ImageFont.truetype(font_path, size_cap)
        f_val = ImageFont.truetype(font_path, size_val)
        d.text((px, W / 2 + (y + 7) * W / 512.0), val, font=f_val,
               fill=(0xf4, 0xf6, 0xf8), anchor="mm")
        d.text((px, W / 2 + (y - 19) * W / 512.0), cap, font=f_cap,
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

    place(".img3.png", layer_w("hour"), 300)
    place(".img4.png", layer_w("minute"), 60)
    place(".img5.png", layer_w("chrono"), 42)
    return base


def make_preview():
    """Bright preview + an ambient preview that mirrors what the watch shows in dim mode."""
    bright = compose_preview(".img1.png", 1.0)
    bright.convert("RGB").save(os.path.join(WORK, "preview.jpg"), quality=92)

    # ambient: lifted plate, hands at 80 %, then the system dimming on top
    dim = compose_preview(".img2.png", 0.80).convert("RGB").point(lambda v: int(v * 0.62))
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
                os.path.join(WORK, "fonts", "SairaSemiBold.ttf"))
    make_plate()

    print("[3/6] trimming hand sprites")
    for stale in (".img6.png", ".img7.png", ".img8.png"):
        f = os.path.join(WORK, "images", stale)
        if os.path.exists(f):
            os.remove(f)
    for src, dst in [("hand_hour.png", ".img3.png"), ("hand_minute.png", ".img4.png"),
                     ("hand_chrono.png", ".img5.png")]:
        SPRITE[src] = trim_hand(os.path.join(WORK, src), os.path.join(WORK, "images", dst))
        print("   ", src, SPRITE[src])

    print("[3b/6] matching sprite pixel sizes to their declared layer sizes")
    fit_hands()

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
