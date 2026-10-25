#!/usr/bin/env python3
"""Photo-exact asset builder (v5).

Differences vs v3:
  * removal mask is the EXACT hand swath (measured width + 3.5 px margin) instead of a
    wide geometric hint that also swallowed the skeleton;
  * all red pixels inside the dial are removed (the chrono hand has a long red tail);
  * the damaged area is repaired with *angular linear interpolation* about the relevant
    centre, which continues the radial skeleton instead of smearing it;
  * the printed date digit is erased so WatchMaker can draw a live date.
"""
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get("WATCH_SRC", os.path.join(HERE, "source", "cbu2010-ft6267.jpg"))
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/out/assets"
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 2.6

CX, CY = 290.6, 535.4
CASE_R = 286.0

HANDS = {
    "minute": dict(axis=59.0, r_in=-26.0, r_out=204.0, w_near=11.0, w_far=8.0),
    "hour":   dict(axis=329.0, r_in=-24.0, r_out=147.0, w_near=12.5, w_far=9.5),
    "chrono": dict(axis=223.0, r_in=-66.0, r_out=224.0, w_near=7.5, w_far=5.0),
}
REGS = [(186.0, 535.5, 75.0), (398.5, 535.5, 75.0), (292.0, 641.0, 70.0)]

DATE_GLYPH = (281.0, 677.0, 298.0, 706.0)   # x0,y0,x1,y1 of the printed "8"


def hand_poly(cx, cy, axis_deg, r_in, r_out, half_w, s=1.0, half_w_far=None):
    if half_w_far is None:
        half_w_far = half_w
    th = math.radians(axis_deg - 90.0)
    ux, uy = math.cos(th), math.sin(th)
    px, py = -uy, ux
    a = (cx + ux * r_in * s - px * half_w * s, cy - uy * r_in * s - py * half_w * s)
    b = (cx + ux * r_out * s - px * half_w_far * s, cy + uy * r_out * s - py * half_w_far * s)
    c = (cx + ux * r_out * s + px * half_w_far * s, cy + uy * r_out * s + py * half_w_far * s)
    d = (cx + ux * r_in * s + px * half_w * s, cy - uy * r_in * s + py * half_w * s)
    return np.array([a, b, c, d], np.int32)


def hand_mask(h, w, cx, cy, margin=3.5):
    """Exact swath of every hand, sized from the measurements (+margin)."""
    m = np.zeros((h, w), np.uint8)
    for cfg in HANDS.values():
        wn = max(cfg["w_near"], cfg["w_far"]) / 2.0 + margin
        wf = min(cfg["w_near"], cfg["w_far"]) / 2.0 + margin
        if cfg["axis"] == 223.0:          # chrono: long thin tail
            wn = 4.0 + margin
            wf = 2.5 + margin
        cv2.fillPoly(m, [hand_poly(cx, cy, cfg["axis"], cfg["r_in"] + 2, cfg["r_out"] - 3,
                                   wn, SCALE, wf)], 255)
    for sx, sy, sr in REGS:
        cv2.fillPoly(m, [hand_poly(sx * SCALE, sy * SCALE, 0.0, -10, sr - 3,
                                   4.6 + margin, SCALE, 3.0 + margin)], 255)
    cv2.circle(m, (int(cx), int(cy)), int(17 * SCALE), 255, -1)
    # round the tips off
    for cfg in HANDS.values():
        th = math.radians(cfg["axis"] - 90.0)
        tip = (int(cx + math.cos(th) * (cfg["r_out"] - 4) * SCALE),
               int(cy + math.sin(th) * (cfg["r_out"] - 4) * SCALE))
        cv2.circle(m, tip, int((cfg["w_far"] / 2.0 + margin) * SCALE), 255, -1)
    return m


def red_mask(a, cx, cy):
    f = a.astype(np.float32)
    R, G, B = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    h, w = R.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rr = np.hypot(xx - cx, yy - cy)
    red = (R > 55) & (R - G > 16) & (R - B > 12) & (rr < 240 * SCALE)
    m = red.astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return cv2.dilate(m, np.ones((5, 5), np.uint8))


def polar_lerp(img, mask, cx, cy, r0, r1, srcmask=None, n=4096, rstep=0.6):
    """Fill masked pixels by blending the two nearest valid angles at the same radius.

    `srcmask` marks pixels that may not be used as a source (the anti-aliased rim of the
    removed hand); only `mask` pixels are written.
    """
    if srcmask is None:
        srcmask = mask
    h, w = img.shape[:2]
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    radii = np.arange(r0, r1, rstep)
    idx = np.arange(n)
    for r in radii:
        xs = np.clip((cx + r * np.cos(ang)).astype(int), 0, w - 1)
        ys = np.clip((cy + r * np.sin(ang)).astype(int), 0, h - 1)
        write = mask[ys, xs] != 0
        if not write.any():
            continue
        bad = srcmask[ys, xs] != 0
        if bad.all():
            continue
        v = img[ys, xs].astype(np.float32)
        good = ~bad
        gg = np.concatenate([good, good])
        vv = np.concatenate([v, v], axis=0)
        pos = np.where(gg, np.arange(2 * n), -1)
        prev = np.maximum.accumulate(pos)
        pos2 = np.where(gg, np.arange(2 * n), 2 * n + 5)
        nxt = np.minimum.accumulate(pos2[::-1])[::-1]
        blk = np.arange(n, 2 * n)
        pv = prev[blk]
        nx = np.minimum(nxt[blk], 2 * n - 1)
        dp = (blk - pv).astype(np.float32)
        dn = (nx - blk).astype(np.float32)
        tot = np.maximum(dp + dn, 1e-6)
        wgt = (dp / tot)[:, None]
        val = vv[pv % n] * (1.0 - wgt) + vv[nx % n] * wgt
        img[ys[write], xs[write]] = np.clip(val[write], 0, 255).astype(np.uint8)
        mask[ys[write], xs[write]] = 0
    return img


def flat_fill(img, mask, cx, cy, r0, r1, pct=30, n=2048, rstep=0.6):
    """Fill a mostly-flat black subdial interior with a per-radius dark percentile."""
    h, w = img.shape[:2]
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    for r in np.arange(r0, r1, rstep):
        xs = np.clip((cx + r * np.cos(ang)).astype(int), 0, w - 1)
        ys = np.clip((cy + r * np.sin(ang)).astype(int), 0, h - 1)
        write = mask[ys, xs] != 0
        if not write.any():
            continue
        good = ~write
        if good.sum() < 8:
            continue
        val = np.percentile(img[ys[good], xs[good]], pct, axis=0)
        img[ys[write], xs[write]] = np.clip(val, 0, 255).astype(np.uint8)
        mask[ys[write], xs[write]] = 0
    return img


def erase_date(img):
    """Rebuild the cream date plate without the printed day number.

    Measured from the photo: the aperture plate is bright over x 277..305, y 672..707;
    the printed digit occupies x 284..299, y 677..706. Sample the clean plate strips
    either side of the digit and blend across it.
    """
    f = img.astype(np.float32)
    xs_fill = (int(284 * SCALE), int(299 * SCALE))
    ys_fill = (int(677 * SCALE), int(706 * SCALE))
    lcol = (int(278 * SCALE), int(282 * SCALE))
    rcol = (int(301 * SCALE), int(305 * SCALE))
    for y in range(ys_fill[0], ys_fill[1] + 1):
        l = np.median(f[y, lcol[0]:lcol[1]], axis=0)
        r = np.median(f[y, rcol[0]:rcol[1]], axis=0)
        row = f[y, xs_fill[0]:xs_fill[1] + 1]
        t = np.linspace(0, 1, row.shape[0])[:, None]
        f[y, xs_fill[0]:xs_fill[1] + 1] = l[None, :] * (1 - t) + r[None, :] * t
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[ys_fill[0]:ys_fill[1] + 1, xs_fill[0]:xs_fill[1] + 1] = 255
    return np.clip(f, 0, 255).astype(np.uint8), mask


def extract_hand(img, cx, cy, axis_deg, r_in, r_out, w_near, w_far, kind):
    """Cut a hand out of the photo.

    The silhouette is taken from the measured geometry (a solid swath), not from a
    luminance threshold: the hands are polished metal with dark sides, so thresholding
    leaves only a thin bright ridge and the hand renders as a wireframe on the watch.
    The hub is replaced with a synthetic steel boss so the neighbouring hands, which
    overlap there in the photo, do not leave rotating slivers.
    """
    span = int(max(abs(r_in), r_out) * SCALE) + 40
    px, py = cx * SCALE, cy * SCALE
    rot = cv2.getRotationMatrix2D((px, py), axis_deg, 1.0)
    big = cv2.warpAffine(img, rot, (img.shape[1], img.shape[0]),
                         flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    crop = big[int(py) - span:int(py) + span, int(px) - span:int(px) + span].copy()
    ch, cw = crop.shape[:2]
    ccx, ccy = cw // 2, ch // 2

    poly = np.array([
        (ccx - w_near / 2 * SCALE, ccy - r_in * SCALE),
        (ccx - w_far / 2 * SCALE, ccy - (r_out - 2) * SCALE),
        (ccx + w_far / 2 * SCALE, ccy - (r_out - 2) * SCALE),
        (ccx + w_near / 2 * SCALE, ccy - r_in * SCALE),
    ], np.int32)
    shape_mask = np.zeros((ch, cw), np.uint8)
    cv2.fillPoly(shape_mask, [poly], 255)
    cv2.circle(shape_mask, (ccx, int(ccy - (r_out - 3) * SCALE)), int(w_far / 2 * SCALE), 255, -1)
    cv2.circle(shape_mask, (ccx, ccy), int(14 * SCALE), 255, -1)

    # pull the silhouette in by ~1 sprite px so the anti-aliased dial edge is not carried
    alpha = cv2.erode(shape_mask, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.9)
    alpha = np.clip((alpha.astype(np.float32) - 20.0) * (255.0 / 215.0), 0, 255).astype(np.uint8)

    # extend the clean part of the shaft inwards: near the pivot the other hands cross
    # this one in the photo, so copy the row at r = 45 px down to the hub
    clean_r = int(45 * SCALE)
    spr = crop.copy()
    row_at = crop[ccy - clean_r].copy()
    solid = shape_mask > 0
    for yy in range(ccy - clean_r + 1, ccy + int(30 * SCALE) + 1):
        m = solid[yy]
        spr[yy][m] = row_at[m]
    crop = spr

    # synthetic polished hub
    hub = int(14 * SCALE)
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    rr = np.hypot(xx - ccx, yy - ccy)
    t = np.clip(rr / hub, 0, 1)[..., None]
    inner = np.array([206, 210, 214], np.float32)
    outer = np.array([104, 109, 114], np.float32)
    boss = inner * (1 - t) + outer * t
    ring = (rr > hub * 0.90) & (rr <= hub)
    boss[ring] = np.array([58, 61, 65], np.float32)
    pin = rr < hub * 0.16
    boss[pin] = np.array([40, 42, 46], np.float32)

    rgb = crop.astype(np.float32)
    hub_zone = rr <= hub
    rgb[hub_zone] = boss[hub_zone]

    rgba = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), alpha]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def main():
    os.makedirs(OUT, exist_ok=True)
    img = Image.open(SRC).convert("RGB")
    img = img.resize((int(img.width * SCALE), int(img.height * SCALE)), Image.LANCZOS)
    a = np.asarray(img).astype(np.uint8)
    h, w, _ = a.shape
    cx, cy = CX * SCALE, CY * SCALE
    case_r = CASE_R * SCALE

    # ---------- sprites
    for name, key, kind in [("hand_minute.png", "minute", "steel"),
                            ("hand_hour.png", "hour", "steel"),
                            ("hand_chrono.png", "chrono", "red")]:
        cfg = HANDS[key]
        im = extract_hand(a, CX, CY, cfg["axis"], cfg["r_in"], cfg["r_out"],
                          cfg["w_near"], cfg["w_far"], kind)
        im.save(os.path.join(OUT, name))
        print(name, im.size)

    for name, (sx, sy, sr), kind in [("reg_hand_red.png", REGS[0], "red"),
                                     ("reg_hand_red2.png", REGS[1], "red"),
                                     ("reg_hand_steel.png", REGS[2], "steel")]:
        im = extract_hand(a, sx, sy, 0.0, -8.0, sr * 0.93, 4.6, 3.0, kind)
        im.save(os.path.join(OUT, name))
        print(name, im.size)

    dx0 = int((CX - 24) * SCALE); dx1 = int((CX + 24) * SCALE)
    dy0 = int((CY + 74) * SCALE); dy1 = int((CY + 124) * SCALE)
    Image.fromarray(a[dy0:dy1, dx0:dx1]).save(os.path.join(OUT, "date_window.png"))

    # ---------- mask
    mask = hand_mask(h, w, cx, cy)
    mask = cv2.bitwise_or(mask, red_mask(a, cx, cy))
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    Image.fromarray(mask).save(os.path.join(OUT, "mask.png"))

    # ---------- repair
    m = mask.copy()
    src = cv2.dilate(mask, np.ones((7, 7), np.uint8))     # never sample the hand rim
    work = a.copy()
    for sx, sy, sr in REGS:
        work = flat_fill(work, m, sx * SCALE, sy * SCALE, 0.0, (sr - 9) * SCALE)
    for sx, sy, sr in REGS:
        work = polar_lerp(work, m, sx * SCALE, sy * SCALE, 0.0, (sr + 3) * SCALE, src)
    work = polar_lerp(work, m, cx, cy, 24 * SCALE, 246 * SCALE, src)

    if m.any():
        bgr = cv2.cvtColor(work, cv2.COLOR_RGB2BGR)
        md = cv2.dilate(m, np.ones((3, 3), np.uint8))
        bgr = cv2.inpaint(bgr, md, 4, cv2.INPAINT_TELEA)
        work = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    work, dm = erase_date(work)
    grain_mask = cv2.bitwise_or(mask, dm)

    rng = np.random.default_rng(7)
    grain = rng.normal(0, 2.0, (h, w, 1)).repeat(3, axis=2)
    soft = cv2.GaussianBlur(work, (0, 0), 1.0).astype(np.float32)
    wm = cv2.GaussianBlur(grain_mask.astype(np.float32), (0, 0), 1.4)[..., None] / 255.0
    out = work.astype(np.float32) * (1 - wm) + (soft + grain) * wm
    out = np.clip(out, 0, 255).astype(np.uint8)

    Image.fromarray(out).save(os.path.join(OUT, "plate_full.png"))
    size = int(round(case_r * 2))
    x0 = int(round(cx - case_r)); y0 = int(round(cy - case_r))
    crop = out[y0:y0 + size, x0:x0 + size]
    Image.fromarray(crop).save(os.path.join(OUT, "plate_crop.png"))
    print("plate", crop.shape, "scale", SCALE)


if __name__ == "__main__":
    main()
