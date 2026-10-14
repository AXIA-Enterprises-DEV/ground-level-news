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

def background(w, h):
    im = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(im, "RGBA")
    step = max(18, w // 60)
    for x in range(-h, w, step):                       # subtle diagonal texture
        d.line([(x, h), (x + h, 0)], fill=(255, 255, 255, 10), width=max(1, w // 800))
    for i, y in enumerate(range(int(h * .78), h, max(6, h // 60))):   # ticker lines
        d.line([(0, y), (w, y)], fill=(255, 255, 255, 14 - min(12, i)), width=1)
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

def placeholder(cat, w=1600, h=900):
    im = background(w, h).convert("RGBA"); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, int(w * .012), h], fill=RED)                       # red accent bar
    c = chip(int(h * .36)); im.alpha_composite(c, ((w - c.width) // 2, int(h * .22)))
    f = font(int(h * .06), "ExtraBold"); t = CAT_LABELS[cat].upper()
    bb = d.textbbox((0, 0), t, font=f); tw = bb[2] - bb[0] + int(h * .06 * 1.6)
    pill(d, ((w - tw) // 2, int(h * .66)), CAT_LABELS[cat], CAT_COLORS[cat], int(h * .06))
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

def og_card(title, cat, out):
    W, H = 1200, 630
    im = background(W, H).convert("RGBA"); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 14, H], fill=RED)
    c = chip(96); im.alpha_composite(c, (W - c.width - 48, 44))
    pill(d, (64, 64), CAT_LABELS.get(cat, cat), CAT_COLORS.get(cat, "#D7141A"), 24)
    for size, ml in [(64, 3), (54, 4), (46, 5)]:
        f = font(size, "Bold"); lines = wrap(d, title, f, W - 128, ml)
        if not lines[-1].endswith("…") or size == 46: break
    y = 190; lh = int(size * 1.14)
    y = 190 + max(0, (ml * lh - len(lines) * lh) // 3)
    for ln in lines: d.text((64, y), ln, font=f, fill=WHITE); y += lh
    d.rectangle([64, H - 92, 64 + 90, H - 86], fill=RED)
    d.text((64, H - 72), "groundlevelnews.com", font=font(28, "SemiBold"), fill=(220, 226, 240))
    im.convert("RGB").save(out, quality=84, optimize=True)

def og_cached(title, cat, out, cache_dir):
    key = hashlib.sha1(f"v1|{cat}|{title}".encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{key}.jpg"
    if not cf.exists(): og_card(title, cat, cf)
    out.parent.mkdir(parents=True, exist_ok=True)
    import shutil; shutil.copyfile(cf, out)

if __name__ == "__main__":
    o = ROOT/"static/img/brand"; o.mkdir(parents=True, exist_ok=True)
    for k in CAT_COLORS:
        im = placeholder(k); im.save(o/f"cat-{k}.webp", quality=82, method=6)
        im.resize((640, 360), Image.LANCZOS).save(o/f"cat-{k}-sm.webp", quality=80, method=6)
    W, H = 1200, 630                                     # branded default og.png
    im = background(W, H).convert("RGBA"); d = ImageDraw.Draw(im); d.rectangle([0, 0, 14, H], fill=RED)
    c = chip(380); im.alpha_composite(c, ((W - c.width) // 2, 70))
    f = font(30, "SemiBold"); t = "News from the ground up  ·  groundlevelnews.com"
    d.text(((W - d.textlength(t, font=f)) // 2, 500), t, font=f, fill=(220, 226, 240))
    im.convert("RGB").save(ROOT/"static/og.png", optimize=True)
    print("ok")
