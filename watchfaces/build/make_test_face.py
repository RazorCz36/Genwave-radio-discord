#!/usr/bin/env python3
"""Build the diagnostic probe face (WatchFaceTest.watch).

Every quadrant carries one variable, so a single photo of the watch tells us
which property the Wear OS 6 / Watch Face Format conversion destroys:

  background  the real 362 KB RGBA dial, 512 px .... does it survive at all?
  A  RGB PNG, 120 px ................ control, must always show
  B  RGBA PNG with transparency ..... does the alpha channel survive?
  D  RGBA PNG with rotation {drm} ... do rotating image layers survive?
  E  JPEG, 120 px ................... is JPEG a safe format?
  F  text layer with bundled font ... does a font-backed text layer survive?

A quadrant that stays black is the failing property.
"""
import os
import zipfile

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVER = os.path.dirname(HERE)
WORK = "/tmp/out/testface"
BIG_PLATE = "/tmp/out/v24/images/dial.png"      # the 362 KB RGBA plate
FONT_SRC = os.path.join(HERE, "fonts", "SairaSemi.ttf")

XML = """<?xml version="1.0" encoding="utf-8"?>
<Watch name="Image Test" description="Probe: RGB / alpha / size / rotation / JPEG / font." features="12h Time,Analog,Digital" shape="R" author="Arena Agent" web_link="" bg_color="000000" ucolor_default="ffffff" ind_loc="bc" ind_bg="Y" hotword_loc="bc" hotword_bg="N">
    <Layer name="background" type="image" x="0" y="0" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" path="c_big.png" width="512" height="512" color="ffffff" display="bd"/>
    <Layer name="a rgb" type="image" x="-128" y="-128" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" path="a_rgb.png" width="120" height="120" color="ffffff" display="bd"/>
    <Layer name="b alpha" type="image" x="0" y="-128" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" path="b_alpha.png" width="120" height="120" color="ffffff" display="bd"/>
    <Layer name="d rotating" type="image" x="-128" y="128" gyro="0" rotation="{drm}" skew_x="0" skew_y="0" opacity="100" alignment="cc" path="d_rot.png" width="150" height="150" color="ffffff" display="bd"/>
    <Layer name="e jpeg" type="image" x="0" y="128" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" path="e_jpg.jpg" width="120" height="120" color="ffffff" display="bd"/>
    <Layer name="f text" type="text" x="128" y="128" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" text="F" text_size="46" anim_scale_x="100" anim_scale_y="100" font="sairasemibold" transform="n" color="ffffff" color_dim="ffffff" display="bd"/>
    <Layer name="clock" type="text" x="0" y="0" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" text="{dh23}:{dm}" text_size="40" anim_scale_x="100" anim_scale_y="100" font="sairasemibold" transform="n" color="8090ff" color_dim="8090ff" display="bd"/>
</Watch>
"""


def label(im, text, box):
    d = ImageDraw.Draw(im)
    d.rectangle(box, fill=(255, 255, 255))
    try:
        f = ImageFont.truetype(FONT_SRC, 16)
    except OSError:
        f = ImageFont.load_default()
    d.text(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), text, font=f,
           fill=(0, 0, 0), anchor="mm")
    return im


def banner(im, text, height=78):
    """Big readable label band across the top of a 512 px tile."""
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width - 1, height], fill=(255, 255, 255))
    d.rectangle([0, 0, im.width - 1, im.height - 1], outline=(255, 40, 40), width=10)
    try:
        f = ImageFont.truetype(FONT_SRC, 56)
    except OSError:
        f = ImageFont.load_default()
    d.text((im.width / 2, height / 2), text, font=f, fill=(0, 0, 0), anchor="mm")
    return im


def flat(colour, size=120, text=""):
    im = Image.new("RGB", (size, size), colour)
    ImageDraw.Draw(im).rectangle([6, 6, size - 7, size - 7], outline=(255, 255, 255), width=3)
    return label(im, text, (0, 0, size - 1, 24)) if text else im


def alpha_tile(size=120):
    """Transparent background, only a bright diamond is opaque."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon([(size / 2, 14), (size - 14, size / 2), (size / 2, size - 14), (14, size / 2)],
              fill=(0, 200, 255, 255))
    return label(im, "B ALPHA", (0, 0, size - 1, 24))


def arrow(size=150):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # long thin hand pointing up, so rotation is obvious
    d.rectangle([size / 2 - 6, 10, size / 2 + 6, size - 12], fill=(255, 60, 60, 255))
    d.ellipse([size / 2 - 12, size / 2 - 12, size / 2 + 12, size / 2 + 12], fill=(255, 255, 255, 255))
    return label(im, "D ROT", (size / 2 - 44, size - 26, size / 2 + 44, size - 2))


def main():
    os.makedirs(os.path.join(WORK, "images"), exist_ok=True)
    os.makedirs(os.path.join(WORK, "fonts"), exist_ok=True)

    flat((0, 130, 90), text="A RGB").save(os.path.join(WORK, "images", "a_rgb.png"))
    alpha_tile().save(os.path.join(WORK, "images", "b_alpha.png"))
    arrow().save(os.path.join(WORK, "images", "d_rot.png"))

    # the very same 362 KB RGBA bitmap the real face shipped as its dial
    plate = Image.open(BIG_PLATE).convert("RGBA")
    plate.save(os.path.join(WORK, "images", "c_big.png"))
    banner(plate.convert("RGB").resize((120, 120), Image.LANCZOS).copy(), "E JPG", height=26).save(
        os.path.join(WORK, "images", "e_jpg.jpg"), quality=92)

    import shutil
    shutil.copy(FONT_SRC, os.path.join(WORK, "fonts", "sairasemibold.ttf"))

    with open(os.path.join(WORK, "watch.xml"), "w", encoding="utf-8") as f:
        f.write(XML)

    out = os.path.join(DELIVER, "WatchFaceTest.watch")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(os.path.join(WORK, "watch.xml"), "watch.xml")
        for name in ("a_rgb.png", "b_alpha.png", "c_big.png", "d_rot.png", "e_jpg.jpg"):
            z.write(os.path.join(WORK, "images", name), f"images/{name}")
        z.write(os.path.join(WORK, "fonts", "sairasemibold.ttf"), "fonts/sairasemibold.ttf")
    print("wrote", out, os.path.getsize(out), "B")
    for name in ("a_rgb.png", "b_alpha.png", "c_big.png", "d_rot.png", "e_jpg.jpg"):
        print("   ", name, os.path.getsize(os.path.join(WORK, "images", name)) // 1024, "KiB")


if __name__ == "__main__":
    main()
