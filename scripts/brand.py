#!/usr/bin/env python3
"""Brand image generator for Ground Level News (Pillow only, no numpy).

    python scripts/brand.py

regenerates, from assets/logo-src.png and the Outfit / Plus Jakarta Sans fonts:
  - logo variants      assets/logo-{full,reverse,mark}.png and static/img/logo*.{png,webp}
                       (full = light backgrounds, reverse = white knockout for dark backgrounds / photos,
                        mark = the globe alone), the header logo at 1x and 2x and static/img/logo.png (297x180)
  - icons              static/favicon-32.png, favicon.ico (16/32/48), apple-touch-icon.png, icon-512.png,
                       static/img/brand/avatar.png (1024, social profiles)
  - category cards     static/img/brand/cat-<key>.webp (1600x900) and cat-<key>-sm.webp (640x360) for every key
                       in CAT_COLORS; placeholder(cat, w, h) also accepts unknown keys (label from the key)
  - default share card static/og.png (1200x630)

build.py uses og_cached()/og_card() for per-story 1200x630 share cards and placeholder() for section art.
"""
import pathlib, hashlib, math, shutil
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS, STATIC = ROOT / "assets", ROOT / "static"
IMG, BRAND = STATIC / "img", STATIC / "img" / "brand"
FONT, FONT_BODY = ASSETS / "Outfit.ttf", ASSETS / "PlusJakartaSans.ttf"

NAVY, NAVY_DEEP, RED, WHITE, PAPER = (0x0B, 0x1A, 0x33), (0x06, 0x0F, 0x20), (0xD7, 0x14, 0x1A), (255, 255, 255), (0xF7, 0xF5, 0xF0)
INK_SOFT, INK_MUTED = (214, 220, 234), (160, 171, 194)        # light text on navy: secondary / tertiary
SITE_HOST, TAGLINE = "groundlevelnews.com", "News from the ground up."

CAT_COLORS = {"us": "#2b59ff", "world": "#0088ff", "politics": "#d6003a", "business": "#ff8a00", "markets": "#00a86b",
              "tech": "#6c4cff", "science": "#00a3b4", "sports": "#ff5a1f", "local": "#ff2d55", "pr": "#D7141A",
              # ready for new sections
              "economy": "#e0b422", "health": "#2ec27e", "energy": "#ffb020", "realestate": "#c77dff", "smallbiz": "#ff7a59",
              "entertainment": "#e84cff", "weather": "#38bdf8", "education": "#60a5fa", "crime": "#b3261e", "opinion": "#94a3b8"}
CAT_LABELS = {"us": "U.S.", "world": "World", "politics": "Politics", "business": "Business", "markets": "Markets", "tech": "Tech",
              "science": "Science", "sports": "Sports", "local": "Local", "pr": "Press Release",
              "economy": "Economy", "health": "Health", "energy": "Energy", "realestate": "Real Estate", "smallbiz": "Small Business",
              "entertainment": "Entertainment", "weather": "Weather", "education": "Education", "crime": "Crime", "opinion": "Opinion"}
DEFAULT_COLOR = "#D7141A"
GHOST = True                      # ghosted globe on category cards

def cat_color(cat): return CAT_COLORS.get(cat, DEFAULT_COLOR)
def cat_label(cat): return CAT_LABELS.get(cat) or str(cat).replace("-", " ").replace("_", " ").title()

# ---------------------------------------------------------------- helpers
def _hex(c): c = c.lstrip("#"); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
def _mix(a, b, t): return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
def _lum(c): return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

_FONTS = {}
def font(size, weight="Bold", body=False):
    """Outfit (headings) or Plus Jakarta Sans (body=True) at a named weight of the variable font."""
    size = max(1, int(size)); key = (size, weight, body)
    if key not in _FONTS:
        f = ImageFont.truetype(str(FONT_BODY if body else FONT), size)
        try: f.set_variation_by_name(weight)
        except Exception: pass
        _FONTS[key] = f
    return _FONTS[key]

def tracked(d, xy, text, f, fill, tracking=0.0):
    """Draw text with letterspacing (tracking in em). Returns the end x."""
    x, y = xy; step = f.size * tracking
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill); x += d.textlength(ch, font=f) + step
    return x - step
def tracked_width(d, text, f, tracking=0.0):
    return sum(d.textlength(ch, font=f) for ch in text) + f.size * tracking * (len(text) - 1)

def fit(im, w=None, h=None):
    """Resize preserving aspect ratio to a width or a height (LANCZOS)."""
    if h and not w: w = round(im.width * h / im.height)
    elif w and not h: h = round(im.height * w / im.width)
    return im.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)

def sharpen(im, percent=55, radius=.7): return im.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=1))

def shadowed(im, blur=10, opacity=.55, offset=(0, 3), pad=None):
    """Return `im` over a soft dark drop shadow (legibility over photographs)."""
    pad = pad or blur * 3
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", im.size, NAVY_DEEP + (int(255 * opacity),)), (pad + offset[0], pad + offset[1]), im.getchannel("A"))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out.alpha_composite(sh); out.alpha_composite(im, (pad, pad))
    return out, pad

def radial(w, h, cx, cy, r, inner=255, outer=0, power=1.6):
    """Smooth radial 'L' mask (built small, resized) centred at (cx, cy) in pixels."""
    s = 8; sw, sh = max(2, w // s), max(2, h // s)
    m = Image.new("L", (sw, sh), outer); px = m.load()
    for y in range(sh):
        for x in range(sw):
            dd = math.hypot((x * s - cx) / r, (y * s - cy) / r)
            if dd < 1: px[x, y] = round(outer + (inner - outer) * (1 - dd) ** power)
    return m.resize((w, h), Image.BICUBIC)

def vgradient(w, h, stops):
    """Vertical 'L' gradient from (position 0..1, value 0..255) stops."""
    g = Image.new("L", (1, h)); px = g.load()
    for y in range(h):
        t = y / max(1, h - 1)
        for (p0, v0), (p1, v1) in zip(stops, stops[1:]):
            if t <= p1:
                u = 0 if p1 == p0 else (t - p0) / (p1 - p0); px[0, y] = round(v0 + (v1 - v0) * u); break
        else: px[0, y] = stops[-1][1]
    return g.resize((w, h))

# ---------------------------------------------------------------- logo variants
SRC_CROP = (81, 84, 1463, 841)      # source artwork without the small URL line underneath
WORDMARK_Y = 516 - SRC_CROP[1]      # first row of "GROUND LEVEL" (an empty band separates it from the horizon swoosh)
GLOBE = (757 - SRC_CROP[0], 447 - SRC_CROP[1], 362, 509 - SRC_CROP[1])  # centre x, centre y, radius, horizon cut-off row
_CACHE = {}

def logo():
    """Full-colour logo, tight crop, transparent (for light backgrounds)."""
    if "full" not in _CACHE:
        im = Image.open(ASSETS / "logo-src.png").convert("RGBA").crop(SRC_CROP)
        _CACHE["full"] = im.crop(im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())
    return _CACHE["full"]

def logo_reverse():
    """Knockout logo for dark backgrounds: navy wordmark pixels become white (alpha preserved, so anti-aliased
    edges stay clean); the red LEVEL and rules and the globe are left untouched."""
    if "reverse" not in _CACHE:
        im = logo(); r, g, b, a = im.split()
        redness = ImageChops.subtract(r, ImageChops.lighter(g, b)).point(lambda v: min(255, max(0, (v - 24) * 5)))   # 0 navy … 255 red
        region = Image.new("L", im.size, 0); ImageDraw.Draw(region).rectangle([0, WORDMARK_Y, im.width, im.height], fill=255)
        knock = ImageChops.multiply(region, ImageChops.invert(redness))                 # where to paint white
        rgb = Image.composite(Image.new("RGB", im.size, WHITE), im.convert("RGB"), knock)
        out = rgb.convert("RGBA"); out.putalpha(a)
        _CACHE["reverse"] = out
    return _CACHE["reverse"]

def logo_mark(size=1024, bg=None, scale=.78, dy=.0):
    """The globe alone (rising over its horizon), centred in a square. bg=None keeps it transparent."""
    key = ("mark", size, bg, scale, dy)
    if key not in _CACHE:
        if "globe" not in _CACHE:
            im = logo(); cx, cy, r, cut = GLOBE
            box = (cx - r, cy - r, cx + r, cy + r)
            mask = Image.new("L", im.size, 0); md = ImageDraw.Draw(mask)
            md.ellipse(box, fill=255); md.rectangle([0, cut, im.width, im.height], fill=0)
            g = im.copy(); g.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
            _CACHE["globe"] = g.crop(box)                                             # square, globe centred
        g = _CACHE["globe"]
        canvas = Image.new("RGBA", (size, size), (bg + (255,)) if bg else (0, 0, 0, 0))
        s = int(size * scale); gi = g.resize((s, s), Image.LANCZOS)
        # the visible part is the top ~60% of the disc: shift down so its optical mass is centred
        vis_h = s * (GLOBE[3] - (GLOBE[1] - GLOBE[2])) / (2 * GLOBE[2])
        y = round((size - vis_h) / 2 + size * dy)
        canvas.alpha_composite(gi, ((size - s) // 2, y))
        _CACHE[key] = canvas
    return _CACHE[key]

# ---------------------------------------------------------------- backgrounds
def contours(w, h, alpha=16, lines=11, origin=(.62, .50)):
    """'Ground level' motif: fine concentric contour lines, anti-aliased (drawn at 2x), fading toward the top-left."""
    W, H = w * 2, h * 2
    m = Image.new("L", (W, H), 0); d = ImageDraw.Draw(m)
    ox, oy = W * origin[0], H * origin[1]
    for k in range(lines):
        base = H * (.11 + k * .085); pts = []
        for i in range(0, 361, 3):
            a = math.radians(i)
            rr = base * (1 + .11 * math.sin(3 * a + k * .9) + .06 * math.sin(7 * a - k * 1.7) + .035 * math.sin(11 * a + k))
            pts.append((ox + rr * 1.55 * math.cos(a), oy + rr * .78 * math.sin(a)))
        d.line(pts + pts[:1], fill=255, width=2)
    m = m.resize((w, h), Image.LANCZOS)
    fade = Image.linear_gradient("L").rotate(90, expand=True).resize((w, h))            # dark left → light right
    fade = ImageChops.multiply(fade, vgradient(w, h, [(0, 40), (.45, 170), (1, 255)]))
    return ImageChops.multiply(m, fade.point(lambda v: int(v * alpha / 255)))

def background(w, h, accent=None, texture=True, contour_alpha=22, ghost=False):
    """Deep navy ground: soft vertical falloff, a restrained wash of the accent colour top-right, faint contours
    and, optionally, a large ghosted globe rising from the bottom edge (the 'ground level')."""
    acc = _hex(accent) if accent else RED
    im = Image.composite(Image.new("RGB", (w, h), NAVY_DEEP), Image.new("RGB", (w, h), NAVY), vgradient(w, h, [(0, 0), (.55, 60), (1, 255)]))
    wash = radial(w, h, w * .96, h * .02, max(w, h) * .9, inner=255, outer=0, power=2.4).point(lambda v: v * .16)
    im = Image.composite(Image.new("RGB", (w, h), _mix(NAVY, acc, .6)), im, wash)
    if texture:
        im = Image.composite(Image.new("RGB", (w, h), (170, 190, 230)), im, contours(w, h, alpha=contour_alpha))
    if ghost:
        # ghosted globe: its own luminance drives the alpha, so the continents glow faintly and the oceans stay navy
        g = logo_mark(round(h * 1.6)); lum = g.convert("L").point(lambda v: round(min(255, v * 1.15)))
        a = ImageChops.multiply(ImageChops.multiply(g.getchannel("A"), lum), Image.new("L", g.size, 30))
        a = ImageChops.multiply(a, vgradient(g.width, g.height, [(0, 255), (.5, 255), (1, 40)]))
        layer = Image.new("RGBA", g.size, (200, 212, 238, 0)); layer.putalpha(a)
        im = im.convert("RGBA"); im.alpha_composite(layer, (round(w * .56), round(h - g.height * .79))); im = im.convert("RGB")
    return im

# ---------------------------------------------------------------- typographic pieces
def pill(d, xy, text, color, size):
    """Rounded label in the category colour; white or navy text depending on the colour's luminance."""
    f = font(size, "ExtraBold"); t = text.upper()
    tw = tracked_width(d, t, f, .08); asc, desc = f.getmetrics(); th = asc
    px, py = round(size * .75), round(size * .42)
    x, y = xy; hgt = th + 2 * py
    d.rounded_rectangle([x, y, x + tw + 2 * px, y + hgt], radius=hgt // 2, fill=color)
    ink = WHITE if _lum(_hex(color) if isinstance(color, str) else color) < 150 else NAVY
    tracked(d, (x + px, y + py - round(size * .12)), t, f, ink, .08)
    return x + tw + 2 * px, y + hgt

def kicker(d, xy, size, color=RED, text="GROUND LEVEL NEWS", fill=INK_SOFT):
    """Short rule in the accent colour + letterspaced small caps."""
    x, y = xy; f = font(size, "SemiBold")
    rule_w, rule_h = round(size * 2.4), max(2, round(size * .16))
    d.rectangle([x, y + size * .52 - rule_h / 2, x + rule_w, y + size * .52 + rule_h / 2], fill=color)
    return tracked(d, (x + rule_w + round(size * .9), y), text, f, fill, .3)

def wrap(d, text, f, maxw, maxlines):
    """Greedy word wrap; the last allowed line gets a proper ellipsis (never a dangling word or a mid-word cut)."""
    words, lines, cur = text.split(), [], ""
    for i, wd in enumerate(words):
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=f) <= maxw: cur = t; continue
        if not cur:                                                             # single word wider than the line
            while len(wd) > 1 and d.textlength(wd + "…", font=f) > maxw: wd = wd[:-1]
            t, cur = wd + "…", ""
            lines.append(t)
        else:
            lines.append(cur); cur = wd
        if len(lines) == maxlines:
            rest = " ".join(words[i:]) if cur else " ".join(words[i + 1:])
            if rest or cur:
                last = lines[-1].rstrip(" ,;:–-")
                while d.textlength(last + "…", font=f) > maxw and " " in last: last = last.rsplit(" ", 1)[0].rstrip(" ,;:–-")
                lines[-1] = last + "…"
            return lines
    if cur: lines.append(cur)
    return lines

def headline(d, text, maxw, maxh, sizes=(64, 56, 48, 42), weight="Bold", maxlines=3, leading=1.1):
    """Pick the largest size whose wrapped block fits maxw x maxh; prefer no ellipsis."""
    best = None
    for size in sizes:
        f = font(size, weight); lines = wrap(d, text, f, maxw, maxlines); lh = round(size * leading)
        if len(lines) * lh <= maxh:
            best = (f, lines, lh)
            if not lines[-1].endswith("…"): return best
    return best or (f, lines, lh)

# ---------------------------------------------------------------- category cards
def placeholder(cat, w=1600, h=900):
    """Branded section card for any key: navy ground, reverse logo, kicker, section name, accent rule and strip."""
    col = cat_color(cat); label = cat_label(cat)
    im = background(w, h, col, ghost=GHOST).convert("RGBA"); d = ImageDraw.Draw(im)
    m = round(h * .09)                                                               # 81px at 900
    lg = fit(logo_reverse(), h=round(h * .26)); im.alpha_composite(lg, (m, m - round(h * .01)))
    strip = max(6, round(h * .013))
    d.rectangle([0, h - strip, w, h], fill=_hex(col))                                # category colour base strip
    # kicker + section name, bottom-left; a vertical accent rule binds them
    f = font(h * .225, "ExtraBold")
    while tracked_width(d, label, f, -.02) > w - 2 * m - h * .05: f = font(f.size * .92, "ExtraBold")
    asc, desc = f.getmetrics(); bb = d.textbbox((0, 0), label, font=f)
    base_y = h - m - strip - bb[3]                                                   # section name bottom at the margin
    ksize = h * .04; k_y = base_y + bb[1] - round(ksize * 1.9)
    rule_w = max(4, round(h * .009)); d.rectangle([m, k_y + ksize * .12, m + rule_w, base_y + bb[3]], fill=_hex(col))
    tx = m + rule_w + round(h * .035)
    kicker(d, (tx, k_y), ksize, _hex(col))
    tracked(d, (tx - bb[0], base_y), label, f, WHITE, -.02)
    return im.convert("RGB")

# ---------------------------------------------------------------- share cards
def _cover(photo, W, H):
    im = Image.open(photo).convert("RGB"); r = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 3
    return im.crop((x, y, x + W, y + H))

def _fmt_date(date):
    if not date: return ""
    if hasattr(date, "strftime"): return date.strftime("%b %-d, %Y")
    s = str(date)[:10]
    try:
        import datetime; return datetime.date.fromisoformat(s).strftime("%b %-d, %Y")
    except Exception: return str(date)

def og_card(title, cat, out, photo=None, credit=None, source=None, date=None, kicker=None):
    """1200x630 share card. Photo full-bleed under a navy gradient, or the branded ground when there is none.
    `source` (publisher) and `date` appear beside the section pill; `kicker` replaces the section label."""
    W, H, M = 1200, 630, 56
    col = cat_color(cat)
    if photo:
        im = _cover(photo, W, H).convert("RGBA")
        im = Image.composite(Image.new("RGBA", (W, H), NAVY + (255,)), im, Image.new("L", (W, H), 28))        # unify tone
        im = Image.composite(Image.new("RGBA", (W, H), NAVY_DEEP + (255,)), im, vgradient(W, H, [(0, 0), (.3, 0), (.62, 150), (1, 238)]))
        im = Image.composite(Image.new("RGBA", (W, H), NAVY_DEEP + (255,)), im, vgradient(W, H, [(0, 120), (.36, 0), (1, 0)]))
    else:
        im = background(W, H, col).convert("RGBA")
    d = ImageDraw.Draw(im)
    lg = fit(logo_reverse(), h=92)
    if photo:
        sh, pad = shadowed(lg, blur=9, opacity=.5); im.alpha_composite(sh, (M - pad, M - 8 - pad))
    else: im.alpha_composite(lg, (M, M - 8))
    logo_bottom = M - 8 + lg.height
    # bottom bar: hairline, domain, credit
    strip = 8
    d.rectangle([0, H - strip, W, H], fill=_hex(col))
    bar_f = font(21, "SemiBold"); bar_y = H - M - 4
    d.line([(M, bar_y - 20), (W - M, bar_y - 20)], fill=(255, 255, 255, 46), width=1)
    d.text((M, bar_y - 2), SITE_HOST, font=bar_f, fill=INK_SOFT, anchor="ls")
    if photo and credit:
        cf = font(14, "Medium", body=True); t = f"Photo: {credit}"
        while d.textlength(t, font=cf) > W * .5 and len(t) > 12: t = t[:-2].rstrip() + "…"
        d.text((W - M, bar_y - 3), t, font=cf, fill=INK_MUTED, anchor="rs")
    # meta + headline block, bottom-anchored above the bar
    text_bottom = bar_y - 20 - 26
    f, lines, lh = headline(d, title, W - 2 * M, text_bottom - (logo_bottom + 110), sizes=(62, 56, 50, 44, 38))
    asc, desc = f.getmetrics()
    block_h = (len(lines) - 1) * lh + asc + round(desc * .3)
    y0 = text_bottom - block_h
    pill_h = 42; pill_y = y0 - 22 - pill_h
    px, _ = pill(d, (M, pill_y), kicker or cat_label(cat), col, 19)
    meta = " · ".join(x for x in (source, _fmt_date(date)) if x)
    if meta:
        mf = font(20, "SemiBold"); mx = px + 18
        while d.textlength(meta, font=mf) > W - M - mx and len(meta) > 8: meta = meta[:-2].rstrip() + "…"
        d.text((mx, pill_y + pill_h / 2 + 1), meta, font=mf, fill=INK_SOFT, anchor="lm")
    y = y0
    for ln in lines:
        d.text((M - 2, y + asc), ln, font=f, fill=WHITE, anchor="ls"); y += lh
    rgb = im.convert("RGB")
    for q in (82, 74, 66, 58):                                                       # keep share cards under ~150KB
        rgb.save(out, quality=q, optimize=True, progressive=True)
        if pathlib.Path(out).stat().st_size <= 150_000: break

def og_cached(title, cat, out, cache_dir, photo=None, credit=None, source=None, date=None, kicker=None):
    key = hashlib.sha1(f"v3|{cat}|{title}|{photo}|{credit}|{source}|{date}|{kicker}".encode()).hexdigest()[:16]
    cache_dir = pathlib.Path(cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    cf = cache_dir / f"{key}.jpg"
    if not cf.exists(): og_card(title, cat, cf, photo, credit, source, date, kicker)
    out = pathlib.Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cf, out)

def og_default(out):
    """Default share image: the reverse logo large, the tagline and the domain."""
    W, H = 1200, 630
    im = background(W, H).convert("RGBA"); d = ImageDraw.Draw(im)
    lg = fit(logo_reverse(), h=272); im.alpha_composite(lg, ((W - lg.width) // 2, 92))
    f = font(36, "Medium"); d.text((W / 2, 448), TAGLINE, font=f, fill=WHITE, anchor="mm")
    f2 = font(19, "SemiBold"); t = SITE_HOST.upper(); tw = tracked_width(d, t, f2, .28)
    x0 = (W - tw) / 2; y = 500
    tracked(d, (x0, y), t, f2, INK_MUTED, .28)
    d.rectangle([x0 - 90, y + 12, x0 - 26, y + 14], fill=RED); d.rectangle([x0 + tw + 26, y + 12, x0 + tw + 90, y + 14], fill=RED)
    d.rectangle([0, H - 8, W, H], fill=RED)
    im.convert("RGB").save(out, optimize=True)

# ---------------------------------------------------------------- icons
def icon(size, scale=.8, radius=0.0, dy=0.0, bg=NAVY):
    """Globe mark on a navy square; radius is the corner radius as a fraction of size (0 = square)."""
    s = 4 if size < 128 else 1                                                      # supersample small icons
    im = logo_mark(size * s, bg=bg, scale=scale, dy=dy)
    if radius:
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width - 1, im.height - 1], radius=round(im.width * radius), fill=255)
        im.putalpha(mask)
    return im.resize((size, size), Image.LANCZOS) if s > 1 else im

def write_logos():
    ASSETS.mkdir(exist_ok=True); IMG.mkdir(parents=True, exist_ok=True); BRAND.mkdir(parents=True, exist_ok=True)
    full, rev = logo(), logo_reverse()
    full.save(ASSETS / "logo-full.png", optimize=True); rev.save(ASSETS / "logo-reverse.png", optimize=True)
    logo_mark(1024).save(ASSETS / "logo-mark.png", optimize=True)
    for name, im in (("logo-full", fit(full, w=1200)), ("logo-reverse", fit(rev, w=1200)), ("logo-mark", logo_mark(512))):
        im.save(IMG / f"{name}.png", optimize=True); im.save(IMG / f"{name}.webp", quality=90, method=6, lossless=False)
    # header logo (same box as before) at 1x and 2x, lightly sharpened after the downsample
    for suffix, (w, h) in (("", (191, 104)), ("@2x", (382, 208))):
        hd = sharpen(full.resize((w, h), Image.LANCZOS), 45, .6); hd.save(IMG / f"logo-header{suffix}.webp", quality=92, method=6)
    # static/img/logo.png keeps its 297x180 box (schema.org logo + footer): the tight logo, centred
    box = Image.new("RGBA", (297, 180), (0, 0, 0, 0)); l = sharpen(fit(full, w=297), 40, .6)
    box.alpha_composite(l, (0, (180 - l.height) // 2))
    box.save(IMG / "logo.png", optimize=True); box.save(IMG / "logo.webp", quality=92, method=6)
    # icons
    icon(32, scale=.86, radius=.22).save(STATIC / "favicon-32.png", optimize=True)
    icon(180, scale=.74).save(STATIC / "apple-touch-icon.png", optimize=True)
    icon(512, scale=.62).save(STATIC / "icon-512.png", optimize=True)
    ico = [icon(48, scale=.86, radius=.2), icon(32, scale=.86, radius=.22), icon(16, scale=.92, radius=.2)]
    ico[0].save(STATIC / "favicon.ico", format="ICO", sizes=[(48, 48), (32, 32), (16, 16)], append_images=ico[1:])
    icon(1024, scale=.66).convert("RGB").save(BRAND / "avatar.png", optimize=True)

if __name__ == "__main__":
    write_logos()
    for k in CAT_COLORS:
        im = placeholder(k); im.save(BRAND / f"cat-{k}.webp", quality=82, method=6)
        im.resize((640, 360), Image.LANCZOS).save(BRAND / f"cat-{k}-sm.webp", quality=80, method=6)
    og_default(STATIC / "og.png")
    print("ok")
