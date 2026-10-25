#!/usr/bin/env python3
"""Render the packaged .watch exactly like WatchMaker would, for previews/mockups.

Reads watch.xml + images/ + fonts/ straight out of the .watch file, evaluates the
tag expressions for a given state and composites the layers in order.

    python3 render_face.py out.png --time 10:09 --chrono 0:07 --date 8 --size 512
"""
import argparse
import math
import os
import re
import sys
import tempfile

TEXT_SCALE = float(os.environ.get("TEXT_SCALE", "1.0"))  # WatchMaker draws text a touch larger
import zipfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont


def unpack(watch_path):
    d = tempfile.mkdtemp(prefix="watch_")
    with zipfile.ZipFile(watch_path) as z:
        z.extractall(d)
    return d


def _arith(e):
    if not re.fullmatch(r"[0-9eE+\-*/().%\s]+", e):
        raise ValueError(f"cannot evaluate expression: {e!r}")
    return float(eval(e, {"__builtins__": {}}, {}))


def eval_expr(expr, tags):
    """Evaluate the small subset of Lua expressions used by the face."""
    e = expr
    for k, v in tags.items():
        e = e.replace("{" + k + "}", "(" + repr(float(v)) + ")")
    m = re.fullmatch(r"\s*(.+?)\s+and\s+(.+?)\s+or\s+(.+?)\s*", e)
    if m:
        return _arith(m.group(2)) if _arith(m.group(1)) else _arith(m.group(3))
    return _arith(e)


def render(watch_path, size=512, hh=10, mm=9, ss=0.0, swh=0, swm=0, sws=0.0,
           day=8, bright=True, blp="87%", ssc="6420", wtd="12\u00b0C"):
    root_dir = unpack(watch_path)
    root = ET.parse(os.path.join(root_dir, "watch.xml")).getroot()

    tags = {
        "drh": (hh % 12) * 30 + mm * 0.5,
        "drm": mm * 6 + ss * 0.1,
        "drs": ss * 6,
        "drss": ss * 6,
        "swh": swh, "swm": swm, "sws": sws,
        "dd": day,
        "abright": 1 if bright else 0,
    }
    texts = {"{dd}": str(day), "{blp}": blp, "{ssc}": ssc, "{wtd}": wtd,
             "{dh}": str(hh), "{dh23}": str(hh), "{dh12}": str(hh % 12 or 12),
             "{dm}": f"{mm:02d}", "{dss}": "00"}
    k = size / 512.0
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 255))

    for layer in root:
        typ = layer.get("type")
        disp = layer.get("display", "bd")
        if bright and "b" not in disp:
            continue
        if (not bright) and "d" not in disp:
            continue
        x = float(eval_expr(layer.get("x", "0"), tags)) * k
        y = float(eval_expr(layer.get("y", "0"), tags)) * k
        cx, cy = size / 2 + x, size / 2 + y

        if typ == "image":
            src = Image.open(os.path.join(root_dir, "images", layer.get("path"))).convert("RGBA")
            w = int(round(float(layer.get("width")) * k))
            src = src.resize((w, w), Image.LANCZOS)
            rot = eval_expr(layer.get("rotation", "0"), tags)
            if rot % 360:
                src = src.rotate(-rot, resample=Image.BICUBIC, expand=False)
            op = float(eval_expr(layer.get("opacity", "100"), tags)) / 100.0
            if op < 1.0:
                src.putalpha(src.getchannel("A").point(lambda v: int(v * op)))
            canvas.alpha_composite(src, (int(round(cx - w / 2)), int(round(cy - w / 2))))

        elif typ == "shape":
            w = float(layer.get("width", "0")) * k
            h = float(layer.get("height", "0")) * k
            col = layer.get("color", "000000")
            rgb = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
            op = float(layer.get("opacity", "100")) / 100.0
            lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            ImageDraw.Draw(lay).ellipse([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2],
                                        fill=rgb + (int(255 * op),))
            canvas.alpha_composite(lay)

        elif typ == "text":
            txt = layer.get("text", "")
            for k2, v2 in texts.items():
                txt = txt.replace(k2, v2)
            fname = layer.get("font")
            fpath = os.path.join(root_dir, "fonts", fname + ".ttf") if fname else ""
            fsize = int(round(float(layer.get("text_size", "20")) * k * TEXT_SCALE))
            font = ImageFont.truetype(fpath, fsize) if os.path.exists(fpath) else ImageFont.load_default()
            col = layer.get("color", "ffffff")
            rgb = tuple(int(col[i:i + 2], 16) for i in (0, 2, 4))
            d = ImageDraw.Draw(canvas)
            d.text((cx, cy), txt, font=font, fill=rgb + (255,), anchor="mm")

    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--watch", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "..", "Carrera_Porsche963.watch"))
    ap.add_argument("--time", default="10:09")
    ap.add_argument("--chrono", default="0:00")
    ap.add_argument("--date", type=int, default=8)
    ap.add_argument("--size", type=int, default=512)
    a = ap.parse_args()

    hh, mm = [int(v) for v in a.time.split(":")]
    c = [float(v) for v in a.chrono.split(":")]
    im = render(a.watch, size=a.size, hh=hh, mm=mm, ss=0.0,
                swh=int(c[0]), swm=int(c[1]), sws=(c[1] % 1) * 60, day=a.date)
    im.convert("RGB").save(a.out, quality=95)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
