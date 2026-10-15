#!/usr/bin/env python3
"""Branded image generator for Ground Level News (Pillow).
- Category placeholder cards: python scripts/brand.py  -> static/img/brand/cat-<key>.webp (+ -sm)
- og_card(): 1200x630 share cards, used by build.py with a content-hash cache."""
import pathlib, hashlib
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT = ROOT/"assets/Outfit.ttf"
NAVY, RED, WHITE = (0x0B,0x1A,0x33), (0xD7,0x14,0x1A), (255,255,255)
CAT_COLORS = {"us":"#2b59ff","world":"#0088ff","politics":"#d6003a","business":"#ff8a00","markets":"#00a86b",
              "tech":"#6c4cff","science":"#00a3b4","sports":"#ff5a1f","local":"#ff2d55","pr":"#D7141A"}
CAT_LABELS = {"us":"U.S.","world":"World","politics":"Politics","business":"Business","markets":"Markets","tech":"Tech",
              "science":"Science","sports":"Sports","local":"Local","pr":"Press Release"}

def font(size, weight="Bold"):
    f = ImageFont.truetype(str(FONT), size)
    try: f.set_variation_by_name(weight)
    except Exception: pass
    return f

_LOGO = None
def logo():
    global _LOGO
    if _LOGO is None:
        im = Image.open(ROOT/"assets/logo-src.png").convert("RGBA").crop((81, 84, 1463, 835))  # drop the tiny URL line
        _LOGO = im.crop(im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox())
    return _LOGO

def _hex(c): c = c.lstrip("#"); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
def _mix(a, b, t): return tuple(round(x + (y - x) * t) for x, y in zip(a, b))

def background(w, h, accent=None):
    """Deep navy with a soft glow of the category color and faint contour lines ("ground level")."""
    import math
    acc = _hex(accent) if accent else RED
    im = Image.new("RGB", (w, h), NAVY)
    glow = Image.new("L", (w, h), 0); gd = ImageDraw.Draw(glow)
    for i in range(40):                                             # radial glow, top-right
        r = int(max(w, h) * (1.05 - i / 40)); gd.ellipse([w * .9 - r, -h * .25 - r, w * .9 + r, -h * .25 + r], fill=int(6 + i * 3.4))
    im = Image.composite(Image.new("RGB", (w, h), _mix(NAVY, acc, .55)), im, glow)
    d = ImageDraw.Draw(im, "RGBA")
    lw = max(1, w // 700)
    for k in range(9):                                              # contour lines across the lower half
        y0 = h * (.48 + k * .065); amp = h * (.03 + .006 * k); ph = k * .7
        pts = [(x, y0 + amp * math.sin(x / w * 2.4 * math.pi + ph) + amp * .5 * math.sin(x / w * 5.1 * math.pi - ph)) for x in range(0, w + 8, 8)]
        d.line(pts, fill=(255, 255, 255, 20 + k * 3), width=lw)
    return im

def chip(target_h, pad_ratio=.16):
    lg = logo(); lh = int(target_h * (1 - 2 * pad_ratio)); lw = round(lg.width * lh / lg.height)
    pad = int(target_h * pad_ratio)
    c = Image.new("RGBA", (lw + 2 * pad, lh + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(c).rounded_rectangle([0, 0, c.width - 1, c.height - 1], radius=int(target_h * .18), fill=WHITE)
    c.alpha_composite(lg.resize((lw, lh), Image.LANCZOS), (pad, pad))
    return c

def pill(d, xy, text, color, size):
    f = font(size, "ExtraBold"); t = text.upper()
    bb = d.textbbox((0, 0), t, font=f); tw, th = bb[2] - bb[0], bb[3] - bb[1]
    px, py = int(size * .8), int(size * .45)
    x, y = xy
    d.rounded_rectangle([x, y, x + tw + 2 * px, y + th + 2 * py], radius=(th + 2 * py) // 2, fill=color)
    d.text((x + px - bb[0], y + py - bb[1]), t, font=f, fill=WHITE)
    return x + tw + 2 * px, y + th + 2 * py

def kicker(d, xy, size):
    """Small red rule + letterspaced GROUND LEVEL NEWS."""
    x, y = xy; f = font(size, "Bold")
    d.rectangle([x, y + size * .38, x + size * 2.2, y + size * .62], fill=RED)
    x += int(size * 3); t = "GROUND LEVEL NEWS"
    for ch in t:
        d.text((x, y), ch, font=f, fill=(225, 230, 242)); x += d.textlength(ch, font=f) + size * .22

def placeholder(cat, w=1600, h=900):
    col = CAT_COLORS[cat]
    im = background(w, h, col).convert("RGBA"); d = ImageDraw.Draw(im)
    m = int(w * .07)
    c = chip(int(h * .17)); im.alpha_composite(c, (m, m))
    kicker(d, (m, int(h * .56)), int(h * .034))
    f = font(int(h * .19), "ExtraBold"); t = CAT_LABELS[cat]
    while d.textlength(t, font=f) > w - 2 * m: f = font(int(f.size * .9), "ExtraBold")
    d.text((m - int(f.size * .04), int(h * .62)), t, font=f, fill=WHITE)
    d.rectangle([0, h - int(h * .022), w, h], fill=_hex(col))        # category color base strip
    return im.convert("RGB")

def wrap(d, text, f, maxw, maxlines):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=f) <= maxw: cur = t
        else:
            lines.append(cur); cur = wd
            if len(lines) == maxlines: break
    if len(lines) < maxlines and cur: lines.append(cur)
    elif cur and len(lines) == maxlines:
        while d.textlength(lines[-1] + "…", font=f) > maxw and " " in lines[-1]: lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines

def _cover(photo, W, H):
    im = Image.open(photo).convert("RGB"); r = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 3
    return im.crop((x, y, x + W, y + H))

def og_card(title, cat, out, photo=None, credit=None):
    W, H = 1200, 630
    col = CAT_COLORS.get(cat, "#D7141A")
    if photo:
        im = _cover(photo, W, H).convert("RGBA")
        shade = Image.new("L", (W, H)); sd = ImageDraw.Draw(shade)
        for y in range(H):                                          # darken toward the bottom for legible text
            sd.line([(0, y), (W, y)], fill=int(70 + 175 * (y / H) ** 1.4))
        im = Image.composite(Image.new("RGBA", (W, H), NAVY + (255,)), im, shade)
    else:
        im = background(W, H, col).convert("RGBA")
    d = ImageDraw.Draw(im)
    c = chip(84); im.alpha_composite(c, (56, 48))
    sizes = [(66, 3), (56, 3), (48, 4)]
    for size, ml in sizes:
        f = font(size, "Bold"); lines = wrap(d, title, f, W - 112, ml)
        if not lines[-1].endswith("…") or size == sizes[-1][0]: break
    lh = int(size * 1.12); y = H - 96 - len(lines) * lh
    _, ph = pill(d, (56, y - 62), CAT_LABELS.get(cat, cat), col, 22)
    for ln in lines: d.text((56, y), ln, font=f, fill=WHITE); y += lh
    d.rectangle([0, H - 10, W, H], fill=_hex(col))
    d.text((56, H - 62), "groundlevelnews.com", font=font(24, "SemiBold"), fill=(220, 226, 240))
    if photo and credit:
        cf = font(16, "Medium"); t = f"Photo: {credit}"[:90]
        d.text((W - 56 - d.textlength(t, font=cf), H - 56), t, font=cf, fill=(200, 206, 222))
    im.convert("RGB").save(out, quality=84, optimize=True)

def og_cached(title, cat, out, cache_dir, photo=None, credit=None):
    key = hashlib.sha1(f"v2|{cat}|{title}|{photo}|{credit}".encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{key}.jpg"
    if not cf.exists(): og_card(title, cat, cf, photo, credit)
    out.parent.mkdir(parents=True, exist_ok=True)
    import shutil; shutil.copyfile(cf, out)

if __name__ == "__main__":
    o = ROOT/"static/img/brand"; o.mkdir(parents=True, exist_ok=True)
    for k in CAT_COLORS:
        im = placeholder(k); im.save(o/f"cat-{k}.webp", quality=82, method=6)
        im.resize((640, 360), Image.LANCZOS).save(o/f"cat-{k}-sm.webp", quality=80, method=6)
    W, H = 1200, 630                                     # branded default og.png
    im = background(W, H).convert("RGBA"); d = ImageDraw.Draw(im)
    c = chip(300); im.alpha_composite(c, ((W - c.width) // 2, 96))
    f = font(30, "SemiBold"); t = "News from the ground up  ·  groundlevelnews.com"
    d.text(((W - d.textlength(t, font=f)) // 2, 470), t, font=f, fill=(220, 226, 240))
    d.rectangle([0, H - 10, W, H], fill=RED)
    im.convert("RGB").save(ROOT/"static/og.png", optimize=True)
    print("ok")
