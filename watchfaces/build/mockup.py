#!/usr/bin/env python3
"""Composite the face into a drawn round smartwatch, for previews."""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from render_face import render  # noqa: E402

WATCH = os.path.join(HERE, "..", "Carrera_Porsche963.watch")


def vgrad(size, top, bottom):
    w, h = size
    t = np.linspace(0, 1, h)[:, None, None]
    a = np.array(top, np.float32)[None, None, :]
    b = np.array(bottom, np.float32)[None, None, :]
    arr = (a * (1 - t) + b * t).repeat(w, axis=1)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


def radial(size, inner, outer, r0=0.0, r1=1.0):
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    r = np.hypot(xx - cx, yy - cy) / (min(w, h) / 2)
    t = np.clip((r - r0) / max(r1 - r0, 1e-6), 0, 1)[..., None]
    a = np.array(inner, np.float32)[None, None, :]
    b = np.array(outer, np.float32)[None, None, :]
    arr = a * (1 - t) + b * t
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


def brushed(size, base, seed=3):
    """Metallic ring texture: fine concentric streaks."""
    w, h = size
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    r = np.hypot(xx - cx, yy - cy)
    streak = rng.normal(0, 6.0, h + 2)
    tex = np.interp(r, np.arange(h + 2), streak)
    shade = np.array(base, np.float32)[None, None, :] + tex[..., None]
    return Image.fromarray(np.clip(shade, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def compose(face, size=1400, screen_frac=0.855, label=None):
    S = size
    canvas = vgrad((S, int(S * 1.28)), (26, 28, 32), (12, 13, 15))
    W, H = canvas.size
    cx, cy = W // 2, int(H * 0.5)

    # ---- strap
    strap_w = int(S * 0.30)
    sg = vgrad((strap_w, H), (44, 46, 50), (30, 32, 35))
    sg = sg.copy()
    m = rounded_mask((strap_w, H), strap_w // 5)
    canvas.paste(sg, (cx - strap_w // 2, 0), m)
    d = ImageDraw.Draw(canvas)
    for yy in range(0, H, 46):
        d.line([(cx - strap_w // 2 + 14, yy), (cx + strap_w // 2 - 14, yy)],
               fill=(38, 40, 44, 255), width=2)

    # ---- case shadow
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).ellipse([cx - int(S * 0.33), cy - int(S * 0.33),
                                cx + int(S * 0.33), cy + int(S * 0.33)], fill=170)
    sh = sh.filter(ImageFilter.GaussianBlur(S * 0.03))
    canvas.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), sh)

    # ---- case body (brushed titanium)
    R = int(S * 0.335)
    body = brushed((2 * R, 2 * R), (150, 154, 160))
    mask = Image.new("L", (2 * R, 2 * R), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * R - 1, 2 * R - 1], fill=255)
    canvas.paste(body, (cx - R, cy - R), mask)
    d = ImageDraw.Draw(canvas)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(96, 100, 106, 255), width=max(2, S // 320))
    d.ellipse([cx - R + 6, cy - R + 6, cx + R - 6, cy + R - 6], outline=(206, 210, 216, 110),
              width=max(1, S // 640))

    # ---- crown
    cw, ch = int(S * 0.045), int(S * 0.085)
    crown = vgrad((cw, ch), (176, 180, 186), (110, 114, 120))
    cm = rounded_mask((cw, ch), cw // 3)
    canvas.paste(crown, (cx + R - cw // 3, cy - ch // 2), cm)

    # ---- dark bezel inside the case
    br = int(R * 0.975)
    d.ellipse([cx - br, cy - br, cx + br, cy + br], fill=(14, 15, 17, 255))
    d.ellipse([cx - br, cy - br, cx + br, cy + br], outline=(70, 74, 80, 255), width=max(2, S // 400))

    # ---- screen with the face
    sr = int(R * screen_frac)
    face_px = int(sr * 2 * 1.0)
    im = render(WATCH, size=face_px, hh=face["hh"], mm=face["mm"], ss=face.get("ss", 0.0),
                swh=face.get("swh", 0), swm=face.get("swm", 0), sws=face.get("sws", 0.0),
                day=face.get("day", 8), bright=face.get("bright", True),
                blp=face.get("blp", "87%"), ssc=face.get("ssc", "6420"),
                wtd=face.get("wtd", "12°C")).convert("RGBA")
    smask = Image.new("L", (face_px, face_px), 0)
    ImageDraw.Draw(smask).ellipse([0, 0, face_px - 1, face_px - 1], fill=255)
    smask = smask.filter(ImageFilter.GaussianBlur(1.2))
    canvas.paste(im, (cx - sr, cy - sr), smask)

    # ---- inner shadow around the glass
    ish = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(ish).ellipse([cx - sr, cy - sr, cx + sr, cy + sr], fill=(0, 0, 0, 120))
    ish = ish.filter(ImageFilter.GaussianBlur(S * 0.012))
    ish.putalpha(ish.getchannel("A").point(lambda v: int(v * 0.35)))
    canvas.alpha_composite(ish)
    ImageDraw.Draw(canvas).ellipse([cx - sr, cy - sr, cx + sr, cy + sr],
                                   outline=(58, 62, 68, 255), width=max(2, S // 500))

    # ---- glass reflection
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    gd.ellipse([cx - sr * 0.92, cy - sr * 1.02, cx + sr * 0.15, cy - sr * 0.05],
               fill=(255, 255, 255, 16))
    gl = gl.filter(ImageFilter.GaussianBlur(S * 0.02))
    canvas.alpha_composite(gl)

    if label:
        d = ImageDraw.Draw(canvas)
        try:
            f = ImageFont.truetype(os.path.join(HERE, "fonts", "SairaSemi.ttf"), int(S * 0.045))
        except Exception:
            f = None
        d.text((cx, cy + R + int(S * 0.055)), label, font=f, fill=(186, 190, 197, 255),
               anchor="mm")
    return canvas


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/wm/mock.png"
    states = [
        (dict(hh=10, mm=9, ss=41, day=25, swh=0, swm=18, sws=0.0, blp="80%", ssc="4315"),
         "10:09  ·  25  ·  chrono 18 min"),
        (dict(hh=22, mm=47, ss=12, day=25, swh=1, swm=42, sws=0.0, blp="64%", ssc="9870"),
         "22:47  ·  25  ·  chrono 1 h 42 min"),
        (dict(hh=3, mm=8, ss=3, day=3, swh=0, swm=7, sws=0.0, blp="52%", ssc="1204", wtd="7°C"),
         "03:08  ·  3  ·  chrono 7 min"),
    ]
    hero = compose(states[0][0], size=1500, label=states[0][1])
    hero.convert("RGB").save(out, quality=94)
    print("wrote", out, hero.size)

    shots = [compose(f, size=1000, label=lab) for f, lab in states]
    pad = 26
    tw = sum(s.width for s in shots) + pad * (len(shots) + 1)
    th = max(s.height for s in shots) + pad * 2
    strip = Image.new("RGBA", (tw, th), (10, 11, 13, 255))
    x = pad
    for s in shots:
        strip.alpha_composite(s, (x, pad + (th - pad * 2 - s.height) // 2))
        x += s.width + pad
    strip_out = os.path.join(os.path.dirname(out), "times.jpg")
    strip.convert("RGB").save(strip_out, quality=94)
    print("wrote", strip_out, strip.size)


if __name__ == "__main__":
    main()
