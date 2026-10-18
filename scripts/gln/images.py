"""Photo registry, photo matching and image markup. Owned by UI.

Matching: content/images.yaml keywords are indexed once as token n-grams (dict lookup, same weights and the same
"keyword or keyword+s" plural tolerance as the old per-keyword regex scan). Scores are memoised per item id.
Repetition guard: a module-level `recent` deque (reset per page by the renderers via reset_recent()) steers an
item to an equal-score alternative when its first choice was just used, and to the branded category card
instead of an unrelated photo on the 3rd+ reuse of a pool (non-keyword) pick.
"""
import re, hashlib, yaml, collections
from urllib.parse import urlsplit
from .config import ROOT
from .text import esc
try:
    from PIL import Image as _PIL
except Exception:
    _PIL = None

# ---------- registry ----------
IMG_CFG = {}
def load_images():
    f = ROOT/"content/images.yaml"
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}
_DIMS = {}
def dims(src):
    """(w,h) of a local static image, read with Pillow; None if unknown."""
    if src in _DIMS: return _DIMS[src]
    d = None
    f = ROOT/"static"/src.lstrip("/")
    if _PIL and not src.startswith("http") and f.exists():
        try:
            with _PIL.open(f) as im: d = im.size
        except Exception: d = None
    _DIMS[src] = d; return d
def _imgs(): return IMG_CFG.get("images") or {}
def cat_img(cat):
    """Branded category card for a section/topic key (registry entry, else the generated /img/brand/cat-<key>.webp)."""
    imgs = _imgs(); cm = IMG_CFG.get("category_images") or {}
    key = cm.get(cat)
    if key and key in imgs: return imgs[key]
    f = ROOT/"static"/"img"/"brand"/f"cat-{cat}.webp"
    if f.exists():
        sm = f"/img/brand/cat-{cat}-sm.webp" if (f.parent/f"cat-{cat}-sm.webp").exists() else None
        return {"src": f"/img/brand/cat-{cat}.webp", "sm": sm, "alt": "", "credit": "Ground Level News", "brand": True}
    return imgs.get(cm.get("us")) if cm.get("us") in imgs else None

# ---------- keyword index ----------
_TOK = re.compile(r"[a-z0-9]+")
def _tok(s): return _TOK.findall((s or "").lower())
_KW, _KW_MAXN = None, 1
def _kw_index():
    """{token-tuple: [(image key, weight)]} built once from the registry keywords."""
    global _KW, _KW_MAXN
    if _KW is None:
        _KW = {}
        for key, im in _imgs().items():
            for kw in im.get("keywords") or []:
                toks = tuple(_tok(str(kw)))
                if not toks: continue
                _KW.setdefault(toks, []).append((key, len(str(kw))))
                _KW_MAXN = max(_KW_MAXN, len(toks))
    return _KW
def _bucket(cat): return sorted(k for k, im in _imgs().items() if cat in (im.get("buckets") or []))
def _scores(text, cat):
    """{image key: score} for keyword hits in text; each keyword counts once (like the old regex search)."""
    kw = _kw_index(); imgs = _imgs(); toks = _tok(text); hit = set(); score = {}
    n_tok = len(toks)
    for i in range(n_tok):
        for n in range(1, min(_KW_MAXN, n_tok - i) + 1):
            g = tuple(toks[i:i + n]); last = g[-1]
            forms = [g] + ([g[:-1] + (last[:-1],)] if len(last) > 1 and last.endswith("s") else [])   # "stocks" hits "stocks" and "stock"
            for f in forms:
                for key, w in kw.get(f, ()):
                    if (key, f) in hit: continue                                                   # each keyword counts once per text
                    hit.add((key, f))
                    bk = imgs[key].get("buckets") or []
                    score[key] = score.get(key, 0) + w + (6 if cat in bk or (cat == "pr" and "local" in bk) else 0)
    return score
def _candidates(text, cat):
    """(ordered list of equal-best image keys, matched: bool). Pool picks are the category bucket."""
    score = _scores(text, cat)
    if score:
        best = max(score.values()); return sorted(k for k, v in score.items() if v == best), True
    return _bucket(cat), False

# ---------- repetition guard ----------
recent = collections.deque(maxlen=12)
def reset_recent():
    """Call at the start of each page so the guard only looks at what this page has shown."""
    recent.clear()
def _seed(seed): return int(hashlib.sha1(str(seed).encode()).hexdigest(), 16)
def _choose(top, matched, cat, seed, avoid=None, require_match=False):
    imgs = _imgs()
    if not top:
        return None if require_match else cat_img(cat)
    if require_match and not matched: return None
    h = _seed(seed); n = len(top)
    order = [top[(h + i) % n] for i in range(n)]
    avoid = set(avoid or ())
    def used(k): return imgs[k]["src"] in avoid or imgs[k]["src"] in recent
    pick = next((k for k in order if not used(k)), None)
    if pick is None:
        pick = order[0]
        # 3rd+ reuse of a non-keyword (pool) photo: a branded card is an honest placeholder, an unrelated photo is a claim
        if not matched and recent.count(imgs[pick]["src"]) >= 2: return cat_img(cat)
    im = imgs[pick]
    recent.append(im["src"])
    return im
def pick_img(text, cat, seed, avoid=None, require_match=False):
    """Best photo for a text: a keyword match, else a stable pick from the category pool (or None when
    require_match), else the branded category card. `avoid`: set of image srcs already used nearby."""
    top, matched = _candidates(text, cat)
    return _choose(top, matched, cat, seed, avoid, require_match)
def match_score(text, cat):
    """Highest keyword score for a text (0 = no keyword hit); for ranking and 'photo only if matched' rules."""
    s = _scores(text, cat); return max(s.values()) if s else 0

LOCAL_RX = re.compile(r"\b(nevada|las vegas|laughlin|bullhead|mohave|mojave|kingman|havasu|arizona|clark county|mesquite|boulder city|lake mead|hoover dam|colorado river|needles|fort mohave|reno)\b", re.I)
_CAND = {}
def story_img(it, require_match=False):
    """Photo for an aggregated item (memoised candidates per id). require_match=True returns None when no keyword hit."""
    key = it.get("id") or it.get("slug") or it.get("title")
    c = _CAND.get(key)
    if c is None:
        text = (it.get("title") or "") + " " + (it.get("summary") or "")[:160]
        # only use the local photo pool when the story names the region
        cat = "local" if it.get("local") and LOCAL_RX.search(text) else (it.get("cat") or "us")
        c = _CAND[key] = (_candidates(text, cat), cat)
    (top, matched), cat = c
    return _choose(top, matched, cat, key, None, require_match)
def has_photo(it):
    """True when a keyword-matched photo exists for the item (no side effects on the guard)."""
    key = it.get("id") or it.get("slug") or it.get("title")
    c = _CAND.get(key)
    if c is None: story_img(it, require_match=True); c = _CAND.get(key)
    return bool(c and c[0][1])
def pr_img(p):
    """Front-matter image for a press release, else a photo matched on area/topic/title."""
    if p.get("image"):
        if "_im" not in p:
            src = p["image"]; sm = p.get("image_sm")
            if not sm and src.startswith("/") and (ROOT/"static"/(src.rsplit(".", 1)[0] + "-sm." + src.rsplit(".", 1)[-1]).lstrip("/")).exists():
                sm = src.rsplit(".", 1)[0] + "-sm." + src.rsplit(".", 1)[-1]
            p["_im"] = {"src": src, "sm": sm, "alt": p.get("image_alt") or p.get("title"), "credit": p.get("image_credit"),
                        "license": p.get("image_license"), "license_url": p.get("image_license_url"),
                        "source": p.get("image_source"), "label": p.get("image_label") or "File photo"}
        return p["_im"]
    return pick_img(" ".join(str(p.get(k) or "") for k in ("area", "topic", "title", "summary")), "pr", p["slug"])

# ---------- markup ----------
def _srcset(im):
    sm, src = im.get("sm"), im.get("src")
    if not sm or sm == src: return ""
    w = (dims(src) or (1600, 0))[0]
    return f' srcset="{esc(sm)} 640w, {esc(src)} {w}w"'
def img_tag(im, cls="", lazy=True, sizes="100vw", small=False, alt=None, fetchpriority=None):
    """<img> with width/height, srcset (sm + full) when a -sm variant exists, lazy/eager loading. alt=None keeps
    the registry alt; pass "" for decorative card thumbs (the credit lives on the article page)."""
    if not im: return ""
    srcset = _srcset(im)
    src = im["sm"] if small and im.get("sm") else im["src"]
    d = dims(src); wh = f' width="{d[0]}" height="{d[1]}"' if d else ""
    a = im.get("alt") if alt is None else alt
    load = ' loading="lazy"' if lazy else (f' fetchpriority="{fetchpriority or "high"}"')
    cls_attr = f' class="{cls}"' if cls else ""
    return f'<img{cls_attr} src="{esc(src)}"{srcset}{f" sizes={chr(34)}{esc(sizes)}{chr(34)}" if srcset else ""} alt="{esc(a)}"{wh}{load} decoding="async">'
def thumb(im, sizes="(max-width:640px) 100vw, (max-width:1024px) 50vw, 400px", lazy=True, cls="thumb", alt=""):
    """Card thumbnail wrapper; data-label renders the 'File photo'/'Illustration' chip over the image."""
    if not im: return ""
    lbl = "" if im.get("brand") or not im.get("label") else f' data-label="{esc(im["label"])}"'
    return f'<div class="{cls}"{lbl}>{img_tag(im, "", lazy, sizes, True, alt)}</div>'
_HOSTS = {"commons.wikimedia.org": "Wikimedia Commons", "flickr.com": "Flickr", "unsplash.com": "Unsplash", "pexels.com": "Pexels",
          "rawpixel.com": "rawpixel", "loc.gov": "Library of Congress", "nasa.gov": "NASA", "huggingface.co": "Hugging Face", "pixabay.com": "Pixabay"}
def host_name(url):
    try: h = urlsplit(url).netloc.lower()
    except Exception: return "Original file"
    h = h[4:] if h.startswith("www.") else h
    for k, v in _HOSTS.items():
        if h == k or h.endswith("." + k): return v
    return h or "Original file"
_NT = '<span class="vh"> (opens in new tab)</span>'
def credit(im):
    if not im or im.get("brand"): return ""
    lic = esc(im.get("license") or "")
    if im.get("license_url") and lic: lic = f'<a href="{esc(im["license_url"])}" rel="license noopener" target="_blank">{lic}{_NT}</a>'
    src = f' · <a href="{esc(im["source"])}" rel="noopener" target="_blank">{esc(host_name(im["source"]))}{_NT}</a>' if im.get("source") else ""
    return f'<span class="lbl">{esc(im.get("label") or "File photo")}</span> {esc(im.get("credit") or "")}{" · " + lic if lic else ""}{src}'
def figure(im, lazy=True, note="", cls="fig", sizes="(max-width:800px) 100vw, 760px"):
    if not im: return ""
    if im.get("brand"): return f'<figure class="{cls}">{img_tag(im, "", lazy, sizes)}</figure>'
    return f'<figure class="{cls}">{img_tag(im, "", lazy, sizes)}<figcaption>{note}{credit(im)}</figcaption></figure>'
