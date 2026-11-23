"""
Genera los sprites y runas estaticas del toggle de tema (styles/assets/runes/)
a partir de design/runes/. Requiere: pip install pillow numpy
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "design", "runes")
OUT = os.path.join(ROOT, "styles", "assets", "runes")

DISK_PX = 100
BLACK_LEVEL = 14  # el fondo de los GIF no es transparente
KEY_RANGE = 90
EDGE_FADE = 10


def load_gif(path):
    im = Image.open(path)
    frames, delays = [], []
    for fr in ImageSequence.Iterator(im):
        frames.append(np.asarray(fr.convert("RGB"), dtype=np.float32))
        delays.append(fr.info.get("duration", 100))
    return frames, delays


def load_png(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)


def disk_geometry(rgb, alpha=None):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    fill = (b - g > 15) & (b > 28) & (np.maximum(np.maximum(r, g), b) < 110)
    if alpha is not None:
        fill &= alpha > 200
    h, w = fill.shape
    m = Image.fromarray((fill * 255).astype(np.uint8)).convert("L")
    pad = Image.new("L", (w + 2, h + 2), 0)
    pad.paste(m, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    outside = np.asarray(pad)[1:-1, 1:-1] == 128
    solid = ~outside
    ys, xs = np.nonzero(fill)
    cx, cy = xs.mean(), ys.mean()
    r_eq = np.sqrt(fill.sum() / np.pi)
    for _ in range(3):
        yy, xx = np.mgrid[0:h, 0:w]
        near = solid & ((xx - cx) ** 2 + (yy - cy) ** 2 < (1.15 * r_eq) ** 2)
        ys, xs = np.nonzero(near)
        cx, cy = xs.mean(), ys.mean()
        r_eq = np.sqrt(near.sum() / np.pi)
    return cx + 0.5, cy + 0.5, r_eq


def key_frame(rgb, center, radius):
    h, w, _ = rgb.shape
    c = np.clip(rgb - BLACK_LEVEL, 0, None) * (255.0 / (255 - BLACK_LEVEL))
    m = c.max(axis=2)
    a_lum = np.clip(m / KEY_RANGE, 0, 1)
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt((xx + 0.5 - center[0]) ** 2 + (yy + 0.5 - center[1]) ** 2)
    a_disk = np.clip(radius - d + 0.5, 0, 1)
    ex = np.minimum(xx + 0.5, w - xx - 0.5)
    ey = np.minimum(yy + 0.5, h - yy - 0.5)
    edge = np.clip(np.minimum(ex, ey) / EDGE_FADE, 0, 1)
    a = np.maximum(a_lum, a_disk) * edge
    prem = c * (1 - a_disk[..., None]) + rgb * a_disk[..., None]
    prem = np.minimum(prem, 255 * a[..., None]) * edge[..., None]
    return np.dstack([prem, a * 255])


def png_premul(rgba):
    a = rgba[..., 3:4] / 255.0
    return np.dstack([rgba[..., :3] * a, rgba[..., 3]])


def warp(prem, src_anchor, s, offset, out_size, k, out_center):
    # P_ref = out_center + offset + s * (P_src - src_anchor)
    W, H = out_size
    SS = 2
    e = k * s
    src = prem
    h, w, _ = src.shape
    fx = fy = 1.0
    target = e * SS
    if target < 1:
        nw, nh = max(1, round(w * target)), max(1, round(h * target))
        fx, fy = nw / w, nh / h
        chans = [Image.fromarray(src[..., i].astype(np.float32), "F").resize((nw, nh), Image.LANCZOS)
                 for i in range(4)]
        src = np.dstack([np.asarray(ch, dtype=np.float32) for ch in chans])
    a_x = 1.0 / (SS * k * s) * fx
    c_x = (src_anchor[0] + ((-W / 2) / k - offset[0]) / s) * fx
    a_y = 1.0 / (SS * k * s) * fy
    c_y = (src_anchor[1] + ((-H / 2) / k - offset[1]) / s) * fy
    out = []
    for i in range(4):
        ch = Image.fromarray(np.ascontiguousarray(src[..., i]).astype(np.float32), "F")
        t = ch.transform((W * SS, H * SS), Image.AFFINE, (a_x, 0, c_x, 0, a_y, c_y), Image.BICUBIC)
        t = t.resize((W, H), Image.LANCZOS)
        out.append(np.asarray(t, dtype=np.float32))
    res = np.dstack(out)
    res[..., 3] = np.clip(res[..., 3], 0, 255)
    res[..., :3] = np.clip(res[..., :3], 0, res[..., 3:4])
    return res


def to_image(prem):
    a = prem[..., 3:4]
    rgb = np.where(a > 0, prem[..., :3] * 255.0 / np.maximum(a, 1e-6), 0)
    arr = np.dstack([np.clip(rgb, 0, 255), a]).round().astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def fit(src_prem, src_anchor, s0, ref_prem, ref_size, C):
    W, H = ref_size

    def err(p):
        s, ox, oy = p
        w_ = warp(src_prem, src_anchor, s, (ox, oy), (W, H), 1.0, C)
        return float(np.abs(w_[..., :3] - ref_prem[..., :3]).mean())

    p = [s0, 0.0, 0.0]
    steps = [0.03 * s0, 2.0, 2.0]
    best = err(p)
    while max(steps[1], steps[2]) > 0.06 or steps[0] > 0.0004 * s0:
        improved = False
        for i in range(3):
            for sign in (1, -1):
                q = list(p)
                q[i] += sign * steps[i]
                e = err(q)
                if e < best:
                    best, p, improved = e, q, True
        if not improved:
            steps = [x / 2 for x in steps]
    return p, best


def main():
    a_frames, a_delays = load_gif(os.path.join(SRC, "rune-ingwaz-to-sowilo.gif"))
    b_frames, b_delays = load_gif(os.path.join(SRC, "rune-sowilo-to-ingwaz.gif"))
    ingwaz = load_png(os.path.join(SRC, "rune-ingwaz-dark.png"))
    sowilo = load_png(os.path.join(SRC, "rune-sowilo-light.png"))

    ga = [disk_geometry(a_frames[0]), disk_geometry(a_frames[-1])]
    gb = [disk_geometry(b_frames[0]), disk_geometry(b_frames[-1])]
    CA = (np.mean([g[0] for g in ga]), np.mean([g[1] for g in ga]))
    rA = np.mean([g[2] for g in ga])
    CB = (np.mean([g[0] for g in gb]), np.mean([g[1] for g in gb]))
    rB = np.mean([g[2] for g in gb])
    gi = disk_geometry(ingwaz[..., :3], ingwaz[..., 3])
    gs = disk_geometry(sowilo[..., :3], sowilo[..., 3])
    print("disk A", CA, rA, "disk B", CB, rB, "png ingwaz", gi, "png sowilo", gs)

    win = int(round(2 * 1.3 * rA))
    ref_size = (win, win)
    C = CA

    def ref_of(frame):
        return warp(key_frame(frame, CA, rA), CA, 1.0, (0, 0), ref_size, 1.0, C)

    refA0, refA29 = ref_of(a_frames[0]), ref_of(a_frames[-1])

    # alinear todo contra el GIF Ingwaz -> Sowilo
    pb1, e1 = fit(key_frame(b_frames[-1], CB, rB), CB, rA / rB, refA0, ref_size, C)
    pb2, e2 = fit(key_frame(b_frames[0], CB, rB), CB, rA / rB, refA29, ref_size, C)
    pB = [(x + y) / 2 for x, y in zip(pb1, pb2)]
    print("fit B->A", pb1, e1, pb2, e2, "->", pB)

    pI, eI = fit(png_premul(ingwaz), gi[:2], rA / gi[2], refA0, ref_size, C)
    pS, eS = fit(png_premul(sowilo), gs[:2], rA / gs[2], refA29, ref_size, C)
    print("fit ingwaz", pI, eI, "fit sowilo", pS, eS)

    k = DISK_PX / (2 * rA)
    big = (int(4 * rA), int(4 * rA))
    ext_x = ext_y = 0.0
    keyedA = [key_frame(f, CA, rA) for f in a_frames]
    keyedB = [key_frame(f, CB, rB) for f in b_frames]
    for kf, anchor, p in [(x, CA, (1.0, 0, 0)) for x in keyedA] + [(x, CB, pB) for x in keyedB]:
        w_ = warp(kf, anchor, p[0], (p[1], p[2]), big, 1.0, C)
        ys, xs = np.nonzero(w_[..., 3] > 6)
        if len(xs):
            ext_x = max(ext_x, np.abs(xs + 0.5 - big[0] / 2).max())
            ext_y = max(ext_y, np.abs(ys + 0.5 - big[1] / 2).max())
    margin = 4
    W = int(np.ceil(2 * ext_x * k)) + 2 * margin
    H = int(np.ceil(2 * ext_y * k)) + 2 * margin
    W += W % 2
    H += H % 2
    print("frame", W, H, "k", k)

    os.makedirs(OUT, exist_ok=True)

    def sprite(keyed, anchor, p, name):
        frames = [warp(kf, anchor, p[0], (p[1], p[2]), (W, H), k, C) for kf in keyed]
        sheet = Image.new("RGBA", (W * len(frames), H))
        for i, fr in enumerate(frames):
            sheet.paste(to_image(fr), (i * W, 0))
        sheet.save(os.path.join(OUT, name), "WEBP", quality=85, alpha_quality=100, method=6)
        return frames

    fa = sprite(keyedA, CA, (1.0, 0, 0), "rune-ingwaz-to-sowilo.webp")
    fb = sprite(keyedB, CB, pB, "rune-sowilo-to-ingwaz.webp")

    st_i = warp(png_premul(ingwaz), gi[:2], pI[0], (pI[1], pI[2]), (W, H), k, C)
    st_s = warp(png_premul(sowilo), gs[:2], pS[0], (pS[1], pS[2]), (W, H), k, C)
    to_image(st_i).save(os.path.join(OUT, "rune-ingwaz.png"), optimize=True)
    to_image(st_s).save(os.path.join(OUT, "rune-sowilo.png"), optimize=True)

    def diff(x, y):
        return float(np.abs(x[..., :3] - y[..., :3]).mean())

    report = {
        "frameWidth": W,
        "frameHeight": H,
        "frames": {"ingwazToSowilo": len(a_frames), "sowiloToIngwaz": len(b_frames)},
        "durationMs": {"ingwazToSowilo": int(sum(a_delays)), "sowiloToIngwaz": int(sum(b_delays))},
        "seamDiff": {
            "ingwaz_vs_A0": diff(st_i, fa[0]), "sowilo_vs_A29": diff(st_s, fa[-1]),
            "sowilo_vs_B0": diff(st_s, fb[0]), "ingwaz_vs_B29": diff(st_i, fb[-1]),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())
