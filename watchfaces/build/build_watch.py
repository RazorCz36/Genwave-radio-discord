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
    px = 2048
    src = src.resize((px, px), Image.LANCZOS)
    a = np.asarray(src).astype(np.uint8)

    yy, xx = np.mgrid[0:px, 0:px].astype(np.float32)
    c = (px - 1) / 2.0
    r = np.hypot(xx - c, yy - c)
    edge = px / 2.0
    alpha = np.clip((edge - r) / 1.6, 0, 1) * 255.0

    rgba = np.dstack([a, alpha.astype(np.uint8)])
    Image.fromarray(rgba, "RGBA").save(os.path.join(WORK, "images", ".img1.png"))
    # no separate dim plate: WatchMaker's ambient mode dims the same layer
    stale = os.path.join(WORK, "images", ".img2.png")
    if os.path.exists(stale):
        os.remove(stale)
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
    out_px = min(1400, max(240, side))
    canvas = canvas.resize((out_px, out_px), Image.LANCZOS)
    canvas.save(out_path)
    extent = max(abs(xs.min() - c), abs(xs.max() - c), abs(ys.min() - c), abs(ys.max() - c))
    return side, float(extent)


SPRITE = {}          # sprite name -> (side px, alpha extent px)


def layer_w(kind, r_out=None):
    """Layer width in 512-units that puts the sprite tip exactly at the measured radius."""
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


# ---------------------------------------------------------------- xml
def watch_xml():
    def img_layer(name, path, size, rot="0", opacity='{abright} and 100 or 55', extra=""):
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
        'features="12h Time,Analog,Date,Smooth Seconds,Stopwatch" '
        'shape="R" author="Arena Agent" web_link="" bg_color="000000" '
        'ucolor_default="ffffff" ind_loc="bc" ind_bg="Y" hotword_loc="bc" hotword_bg="N">')

    # background plate
    lines.append(img_layer("dial", ".img1.png", 512, opacity="100"))

    # hands: hour, minute, chrono seconds
    h = HANDS
    lines.append(img_layer("hour hand", ".img3.png", round(layer_w("hour"), 1), rot="{drh}"))
    lines.append(img_layer("minute hand", ".img4.png", round(layer_w("minute"), 1), rot="{drm}"))
    lines.append(img_layer("chrono seconds", ".img5.png", round(layer_w("chrono"), 1), rot="{drss}"))

    # register hands — positions come straight from the photo
    lx, ly = REG_UNITS[0]
    rx, ry = REG_UNITS[1]
    bx, by = REG_UNITS[2]
    for name, path, x, y, size, rot in [
        ("chrono hours", ".img6.png", lx, ly, layer_w("reg", 75.0), "({swh}%12)*30 + {swm}*0.5"),
        ("chrono minutes", ".img7.png", rx, ry, layer_w("reg2", 75.0), "({swm}%30)*12 + {sws}*0.2"),
        ("seconds", ".img8.png", bx, by, layer_w("regb", 70.0), "{drss}"),
    ]:
        lines.append(
            f'    <Layer name="{escape(name)}" type="image" x="{x:.2f}" y="{y:.2f}" gyro="0" '
            f'rotation="{rot}" skew_x="0" skew_y="0" opacity="{{abright}} and 100 or 55" '
            f'alignment="cc" path="{path}" width="{size:.1f}" height="{size:.1f}" '
            f'color="ffffff" display="bd"/>')

    # date window (dynamic)
    lines.append(
        f'    <Layer name="date" type="text" x="{DATE_U[0]:.1f}" y="{DATE_U[1]:.1f}" gyro="0" '
        f'rotation="0" skew_x="0" skew_y="0" opacity="{{abright}} and 100 or 75" '
        f'alignment="cc" text="{{dd}}" text_size="{DATE_SIZE}" anim_scale_x="100" '
        f'anim_scale_y="100" font="{DATE_FONT}" transform="n" color="101215" '
        f'color_dim="101215" display="bd"/>')

    lines.append('</Watch>')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- preview
def make_preview():
    """Render an 11:10 style preview from the assets."""
    W = 512
    bg = Image.open(os.path.join(WORK, "images", ".img1.png")).convert("RGBA").resize((W, W), Image.LANCZOS)
    base = Image.new("RGBA", (W, W), (0, 0, 0, 255))
    base.alpha_composite(bg)

    def place(path, size, angle):
        im = Image.open(path).convert("RGBA")
        s = max(1, int(round(size * W / 512.0)))
        im = im.resize((s, s), Image.LANCZOS)
        im = im.rotate(-angle, resample=Image.BICUBIC, expand=False)
        layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        layer.paste(im, ((W - s) // 2, (W - s) // 2), im)
        base.alpha_composite(layer)

    place(os.path.join(WORK, "images", ".img3.png"), layer_w("hour"), 300)
    place(os.path.join(WORK, "images", ".img4.png"), layer_w("minute"), 60)
    place(os.path.join(WORK, "images", ".img5.png"), layer_w("chrono"), 42)

    for path, (x, y), size, ang in [
        (".img6.png", REG_UNITS[0], layer_w("reg", 75.0), 0),
        (".img7.png", REG_UNITS[1], layer_w("reg2", 75.0), 0),
        (".img8.png", REG_UNITS[2], layer_w("regb", 70.0), 0),
    ]:
        im = Image.open(os.path.join(WORK, "images", path)).convert("RGBA")
        s = max(1, int(round(size * W / 512.0)))
        im = im.resize((s, s), Image.LANCZOS)
        if ang:
            im = im.rotate(-ang, resample=Image.BICUBIC, expand=False)
        cx = int(W / 2 + x * W / 512.0)
        cy = int(W / 2 + y * W / 512.0)
        tmp = Image.new("RGBA", (W, W), (0, 0, 0, 0))
        tmp.paste(im, (cx - s // 2, cy - s // 2), im)
        base.alpha_composite(tmp)

    # live date, drawn exactly like the text layer
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(base)
    f = ImageFont.truetype(os.path.join(WORK, "fonts", "SairaSemiBold.ttf"), DATE_SIZE)
    cx = W / 2 + DATE_U[0] * W / 512.0
    cy = W / 2 + DATE_U[1] * W / 512.0
    d.text((cx, cy), "8", font=f, fill=(0x10, 0x12, 0x15), anchor="mm", embedded_color=False)

    base.convert("RGB").save(os.path.join(WORK, "preview.jpg"), quality=92)
    dim = base.convert("RGB").point(lambda v: int(v * 0.55))
    dim.save(os.path.join(WORK, "preview_dim.jpg"), quality=92)


# ---------------------------------------------------------------- package
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
    for src, dst in [("hand_hour.png", ".img3.png"), ("hand_minute.png", ".img4.png"),
                     ("hand_chrono.png", ".img5.png"), ("reg_hand_red.png", ".img6.png"),
                     ("reg_hand_red2.png", ".img7.png"), ("reg_hand_steel.png", ".img8.png")]:
        SPRITE[src] = trim_hand(os.path.join(WORK, src), os.path.join(WORK, "images", dst))
        print("   ", src, SPRITE[src])

    print("[4/6] writing watch.xml")
    with open(os.path.join(WORK, "watch.xml"), "w", encoding="utf-8") as f:
        f.write(watch_xml())

    print("[5/6] rendering previews")
    make_preview()

    print("[6/6] packaging .watch")
    out = package()
    print("done ->", out, os.path.getsize(out) // 1024, "KiB")


if __name__ == "__main__":
    main()
