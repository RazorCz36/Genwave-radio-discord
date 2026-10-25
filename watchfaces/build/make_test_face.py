#!/usr/bin/env python3
"""Build a 2-layer probe face (WatchFaceTest.watch).

Purpose: decide whether the Wear OS 6 / Watch Face Format conversion on the
phone can carry *any* bitmap into a face.  If the test face shows the picture,
image layers work and the fault is inside the big face's package.  If it shows
only the text, the converter is dropping every image and no .watch file can fix
that from our side.
"""
import os
import zipfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVER = os.path.dirname(HERE)
WORK = "/tmp/out/testface"

xml = """<?xml version="1.0" encoding="utf-8"?>
<Watch name="Image Test" description="Probe face: one image layer plus one text layer." features="12h Time,Analog,Digital" shape="R" author="Arena Agent" web_link="" bg_color="000000" ucolor_default="ffffff" ind_loc="bc" ind_bg="Y" hotword_loc="bc" hotword_bg="N">
    <Layer name="picture" type="image" x="0" y="0" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" path="picture.png" width="512" height="512" color="ffffff" display="bd"/>
    <Layer name="clock" type="text" x="0" y="0" gyro="0" rotation="0" skew_x="0" skew_y="0" opacity="100" alignment="cc" text="{dh23}:{dm}" text_size="54" anim_scale_x="100" anim_scale_y="100" transform="n" color="ffffff" color_dim="ffffff" display="bd"/>
</Watch>
"""


def picture():
    px = 512
    im = Image.new("RGB", (px, px), (0, 0, 0))
    d = ImageDraw.Draw(im)
    # concentric rings so it is obvious whether the bitmap or only its centre shows
    for r, c in ((248, (0, 122, 255)), (232, (255, 255, 0)), (216, (0, 200, 90))):
        d.ellipse([px / 2 - r, px / 2 - r, px / 2 + r, px / 2 + r], outline=c, width=10)
    for i in range(0, px, 32):
        d.line([(0, i), (px, i)], fill=(40, 40, 40), width=1)
        d.line([(i, 0), (i, px)], fill=(40, 40, 40), width=1)
    d.rectangle([0, 0, px - 1, px - 1], outline=(255, 40, 40), width=8)
    return im


def main():
    os.makedirs(os.path.join(WORK, "images"), exist_ok=True)
    picture().save(os.path.join(WORK, "images", "picture.png"))
    with open(os.path.join(WORK, "watch.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    out = os.path.join(DELIVER, "WatchFaceTest.watch")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.write(os.path.join(WORK, "watch.xml"), "watch.xml")
        z.write(os.path.join(WORK, "images", "picture.png"), "images/picture.png")
    print("wrote", out, os.path.getsize(out), "B")


if __name__ == "__main__":
    main()
