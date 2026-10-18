"""Photo registry, photo matching and image markup."""
import re, hashlib, yaml
from .config import ROOT
from .text import esc
try:
    from PIL import Image as _PIL
except Exception:
    _PIL = None

# ---------- images ----------
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
def cat_img(cat):
    imgs = IMG_CFG.get("images") or {}
    key = (IMG_CFG.get("category_images") or {}).get(cat) or (IMG_CFG.get("category_images") or {}).get("us")
    return imgs.get(key)
_KW = None
def _kw_index():
    """[(compiled keyword regex, weight, image key)] from the registry, built once."""
    global _KW
    if _KW is None:
        _KW = []
        for key, im in (IMG_CFG.get("images") or {}).items():
            for kw in im.get("keywords") or []:
                _KW.append((re.compile(r"\b" + re.escape(str(kw).lower()) + r"s?\b"), len(str(kw)), key))
    return _KW
def _bucket(cat):
    imgs = IMG_CFG.get("images") or {}
    return [k for k, im in imgs.items() if cat in (im.get("buckets") or [])]
def pick_img(text, cat, seed):
    """Best real photo for a story: a keyword match in the text, else a stable pick from the
    category's photo pool, else the branded category card."""
    imgs = IMG_CFG.get("images") or {}
    t = (text or "").lower()
    score = {}
    for rx, w, key in _kw_index():
        bk = imgs[key].get("buckets") or []
        if rx.search(t): score[key] = score.get(key, 0) + w + (6 if cat in bk or (cat == "pr" and "local" in bk) else 0)
    h = int(hashlib.sha1(str(seed).encode()).hexdigest(), 16)
    if score:
        best = max(score.values()); top = sorted(k for k, v in score.items() if v == best)
        return imgs[top[h % len(top)]]
    pool = sorted(_bucket(cat))
    return imgs[pool[h % len(pool)]] if pool else cat_img(cat)
LOCAL_RX = re.compile(r"\b(nevada|las vegas|henderson|laughlin|bullhead|mohave|kingman|havasu|arizona|clark county|mesquite|boulder city|lake mead|hoover dam|colorado river|reno)\b", re.I)
def story_img(it):
    text = it["title"] + " " + it.get("summary", "")[:160]
    # The feed tags some non-local stories "local"; only use the local photo pool when the story names the region.
    cat = "local" if it.get("local") and LOCAL_RX.search(text) else it["cat"]
    return pick_img(text, cat, it["id"])
def pr_img(p):
    """Front-matter image for a press release, else a photo matched on area/topic/title."""
    if p.get("image"):
        return {"src": p["image"], "sm": p.get("image_sm"), "alt": p.get("image_alt") or p.get("title"), "credit": p.get("image_credit"),
                "license": p.get("image_license"), "license_url": p.get("image_license_url"),
                "source": p.get("image_source"), "label": p.get("image_label") or "File photo"}
    return pick_img(" ".join(str(p.get(k) or "") for k in ("area", "topic", "title", "summary")), "pr", p["slug"])
def img_tag(im, cls="", lazy=True, sizes="100vw", small=False):
    if not im: return ""
    if small and im.get("sm"): im = {**im, "src": im["sm"]}
    d = dims(im["src"]); wh = f' width="{d[0]}" height="{d[1]}"' if d else ""
    return f'<img class="{cls}" src="{esc(im["src"])}" alt="{esc(im.get("alt"))}"{wh}{" loading=\"lazy\"" if lazy else " fetchpriority=\"high\""} decoding="async" sizes="{sizes}">'
def credit(im):
    if not im or im.get("brand"): return ""
    lic = esc(im.get("license") or "")
    if im.get("license_url") and lic: lic = f'<a href="{esc(im["license_url"])}" rel="license noopener" target="_blank">{lic}</a>'
    src = f' · <a href="{esc(im["source"])}" rel="noopener" target="_blank">Source</a>' if im.get("source") else ""
    return f'<span class="lbl">{esc(im.get("label") or "File photo")}</span> {esc(im.get("credit") or "")}{" · " + lic if lic else ""}{src}'
def figure(im, lazy=True, note=""):
    if not im: return ""
    if im.get("brand"): return f'<figure class="fig">{img_tag(im, "", lazy, "(max-width:900px) 100vw, 860px")}</figure>'
    return f'<figure class="fig">{img_tag(im, "", lazy, "(max-width:900px) 100vw, 860px")}<figcaption>{note}{credit(im)}</figcaption></figure>'
