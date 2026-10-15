#!/usr/bin/env python3
"""Ground Level News static site builder.
Pulls news-tracker data from its GitHub Pages URL, renders HTML into _site/."""
import os, re, json, html, shutil, hashlib, datetime as dt, pathlib, sys
import requests, yaml, markdown
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    import brand
except Exception as e:
    brand = None; print(f"WARN brand: {e}", file=sys.stderr)
try:
    from PIL import Image as _PIL
except Exception:
    _PIL = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
SRC = os.environ.get("TRACKER_BASE", "https://axia-enterprises-dev.github.io/news-tracker")
SITE = os.environ.get("SITE_URL", "https://groundlevelnews.com").rstrip("/")
from urllib.parse import urlparse
BASE = urlparse(SITE).path.rstrip("/")
NAME = "Ground Level News"
TAG = "News from the ground up."
INDEXNOW_KEY = "5a8308b39ca87422bfd5d4eb53c1c5bb"
CONTACT = os.environ.get("CONTACT_EMAIL", "news@groundlevelnews.com")
# Names that must never appear anywhere on the published site.
BLOCK = re.compile(r"\b(axia|clem)\b", re.I)
NOW = dt.datetime.now(dt.timezone.utc)

CATS = [("us","U.S."),("world","World"),("politics","Politics"),("business","Business"),
        ("markets","Markets"),("tech","Tech"),("science","Science"),("sports","Sports"),("local","Local")]
CAT_NAME = dict(CATS)
LOCAL_PROJECTS = {"nevada","realestate","civic"}
HIDE_CATS = {"filings"}

def esc(s): return html.escape(str(s or ""), quote=True)
def clean(s, n=None):
    s = re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n: s = s[:n].rsplit(" ", 1)[0] + "…"
    return s
def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70] or "story"

# Feed source names are often feed titles; show the publisher instead.
SOURCE_NAMES = {
    "World News, Today World News, Latest International News, World Breaking News, Trending News of World - Times of India": "Times of India",
    "Phys.org - latest science and technology news stories": "Phys.org", "www.theregister.com - Articles": "The Register",
    "Engadget - Technology News & Expert Reviews": "Engadget", "Fortune | FORTUNE": "Fortune", "Forbes - Business": "Forbes",
    "News - Cryptonews": "Cryptonews", "Cointelegraph.com News": "Cointelegraph", "NYT > Technology": "NYT Technology",
    "Money Saving Mom®": "Money Saving Mom", "FT Home": "Financial Times", "Seeking Alpha Market Currents": "Seeking Alpha",
    "MarketWatch Top Stories": "MarketWatch", "CNBC Top News": "CNBC", "Investing.com Stock Market": "Investing.com",
    "Investing.com Economic Indicators": "Investing.com", "START (UMD) Terrorism Research": "START (UMD)",
    "NY Fed Liberty Street Economics": "New York Fed", "All News": "Investing.com",
}
def tidy_source(it):
    """Clean up the source name; Google News items carry the publisher at the end of the title."""
    src = (it.get("source") or "").strip()
    if src.startswith(("Google News", "Top stories - Google News")):
        m = re.match(r"^(.*\S)\s+[-–]\s+([^-–]{2,60})$", it["title"])
        if m: it["title"], src = m.group(1), m.group(2).strip()
        else: src = "Google News"
    elif src.startswith("PR Newswire"): src = "PR Newswire"
    it["source"] = SOURCE_NAMES.get(src, src) or "Wire report"

def get_json(path):
    try:
        r = requests.get(f"{SRC}/{path}", timeout=30); r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"WARN fetch {path}: {e}", file=sys.stderr); return None

def load_items():
    items = {}
    lst = get_json("data/latest.json") or []
    man = get_json("data/manifest.json") or {}
    for day in (man.get("days") or [])[:2]:
        d = get_json(f"data/days/{day}.json")
        if isinstance(d, dict): d = d.get("items", [])
        lst += d or []
    for it in lst:
        if not isinstance(it, dict) or not it.get("title") or not it.get("link"): continue
        if it.get("category") in HIDE_CATS: continue
        if re.search(r"\b(8-K|10-Q|10-K|S-1|424B|Form 4|SC 13)\b", it["title"]): continue
        key = it.get("id") or hashlib.sha1(it["link"].encode()).hexdigest()[:14]
        it["id"] = key
        it["ts"] = int(it.get("ts") or 0)
        it["title"] = clean(it["title"], 200)
        it["summary"] = clean(it.get("summary"), 420)
        tidy_source(it)
        if BLOCK.search(" ".join([it["title"], it["summary"], it["source"], it["link"]])): continue
        if len(re.findall(r"[\u0400-\u04ff\u0600-\u06ff\u3040-\u30ff\u4e00-\u9fff]", it["title"])) > len(it["title"]) * .2: continue  # non-English
        cat = it.get("category") or "us"
        if LOCAL_PROJECTS & set(it.get("projects") or []): it["local"] = True
        it["cat"] = cat if cat in CAT_NAME else "us"
        it["slug"] = f"{slugify(it['title'])}-{key[:6]}"
        items.setdefault(key, it)
    out = sorted(items.values(), key=lambda x: -x["ts"])
    # de-dup near identical titles
    seen, res = set(), []
    for it in out:
        k = re.sub(r"\W", "", it["title"].lower())[:60]
        if k in seen: continue
        seen.add(k); res.append(it)
    return res[:1500], man

def load_prs():
    prs = []
    for p in sorted((ROOT/"content/press-releases").glob("*.md"), reverse=True):
        txt = p.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
        if not m: print(f"WARN bad frontmatter {p.name}", file=sys.stderr); continue
        fm = yaml.safe_load(m.group(1)) or {}
        fm["body"] = markdown.markdown(m.group(2), extensions=["extra"])
        fm["md"] = m.group(2).strip()
        fm["slug"] = p.stem
        fm["date"] = str(fm.get("date", p.stem[:10]))
        prs.append(fm)
    prs.sort(key=lambda x: (bool(x.get("example")), x["date"]), reverse=False)
    real = sorted([x for x in prs if not x.get("example")], key=lambda x: x["date"], reverse=True)
    return real + [x for x in prs if x.get("example")]

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
        if rx.search(t): score[key] = score.get(key, 0) + w + (6 if cat in (imgs[key].get("buckets") or []) else 0)
    h = int(hashlib.sha1(str(seed).encode()).hexdigest(), 16)
    if score:
        best = max(score.values()); top = sorted(k for k, v in score.items() if v >= best - 2)
        return imgs[top[h % len(top)]]
    pool = sorted(_bucket(cat))
    return imgs[pool[h % len(pool)]] if pool else cat_img(cat)
def story_img(it):
    cat = "local" if it.get("local") else it["cat"]
    return pick_img(it["title"] + " " + it.get("summary", "")[:160], cat, it["id"])
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

def ago(ts):
    if not ts: return ""
    s = int(NOW.timestamp()) - ts
    if s < 3600: return f"{max(1, s//60)}m ago"
    if s < 86400: return f"{s//3600}h ago"
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%b %d")

def iso(ts): return dt.datetime.fromtimestamp(ts or NOW.timestamp(), dt.timezone.utc).isoformat()

def page(title, body, desc=TAG, path="/", ticker="", og_type="website", extra_head="", og_img=None, md=None):
    full = f"{esc(title)} | {NAME}" if title != NAME else f"{NAME} | {TAG}"
    url = SITE + path
    canon = SITE + path
    cur = lambda pre: ' aria-current="page"' if path.startswith(pre) else ""
    nav = "".join(f'<a href="/category/{k}/"{cur(f"/category/{k}/")}>{v}</a>' for k, v in CATS) + f'<a href="/press-releases/" class="pr"{cur("/press-releases/")}>Press Releases</a>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{full}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}"><meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}"><meta property="og:type" content="{og_type}">
<meta property="og:image" content="{og_img or SITE + "/og.png"}"><meta property="og:image:alt" content="{NAME}"><meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/png" sizes="512x512" href="/icon-512.png"><link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"><meta name="twitter:image" content="{og_img or SITE + "/og.png"}">
<link rel="alternate" type="application/rss+xml" title="{NAME} RSS" href="/rss.xml"><link rel="alternate" type="application/atom+xml" title="{NAME} Atom" href="/feed.xml">{f'<link rel="alternate" type="text/markdown" href="{md}">' if md else ''}<link rel="help" type="text/plain" href="/llms.txt" title="llms.txt">
<meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(desc)}"><meta name="robots" content="index,follow,max-image-preview:large">
<script type="application/ld+json">{SITE_LD}</script>
<link rel="preload" href="/fonts/outfit.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/fonts/jakarta.woff2" as="font" type="font/woff2" crossorigin>
<link rel="manifest" href="/site.webmanifest"><meta name="color-scheme" content="light"><meta name="format-detection" content="telephone=no">
<link rel="stylesheet" href="/style.css"><script>document.documentElement.classList.add("js")</script>{extra_head}</head><body>
<div class="ticker"><span class="live">LIVE</span><div class="tk-wrap"><div class="tk">{ticker}{ticker}</div></div></div>
<a class="skip" href="#main">Skip to content</a>
<header class="top" id="top"><div class="wrap hdr"><a class="logo" href="/" aria-label="Ground Level News home"><img src="/img/logo-header.webp" alt="Ground Level News" width="191" height="104"></a>
<button class="menu" type="button" aria-controls="site-nav" aria-expanded="false" aria-label="Open menu"><span></span><span></span><span></span></button>
<nav class="nav" id="site-nav" aria-label="Sections">{nav}</nav></div></header>
<main class="wrap" id="main">{body}</main>
<footer class="foot"><div class="wrap">
<div class="fgrid"><div class="fbrand"><a class="flogo" href="/" aria-label="Ground Level News home"><img src="/img/logo.webp" alt="Ground Level News" width="297" height="180" loading="lazy"></a>
<p>{TAG} National headlines from public news feeds, plus local news from Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite and Boulder City. Every story links to its original publisher.</p>
<a class="btn" href="/submit/">Submit a press release</a></div>
<nav aria-label="Sections"><h2>Sections</h2><ul class="cols2">{"".join(f'<li><a href="/category/{k}/">{v}</a></li>' for k, v in CATS)}<li><a href="/press-releases/">Press Releases</a></li></ul></nav>
<nav aria-label="About"><h2>About</h2><ul><li><a href="/about/">About &amp; Sources</a></li><li><a href="/submit/">Submit a Release</a></li><li><a href="/identity/">Brand &amp; Logo</a></li><li><a href="/accessibility/">Accessibility</a></li><li><a href="mailto:{CONTACT}">Contact</a></li></ul></nav>
<nav aria-label="For AI and developers"><h2>For AI &amp; Developers</h2><ul><li><a href="/llm-info/">LLM info</a></li><li><a href="/llms.txt">llms.txt</a></li><li><a href="/llms-full.txt">llms-full.txt</a></li><li><a href="/agents.txt">agents.txt</a></li><li><a href="/ai.txt">ai.txt</a></li><li><a href="/agents.md">Agent guide</a></li></ul></nav>
<nav aria-label="Feeds"><h2>Feeds</h2><ul><li><a href="/rss.xml">RSS</a></li><li><a href="/feed.xml">Atom</a></li><li><a href="/sitemap.xml">Sitemap</a></li><li><a href="/news-sitemap.xml">News sitemap</a></li></ul></nav></div>
<div class="fbar"><p>© {NOW.year} {NAME} · Updated <time datetime="{NOW.strftime('%Y-%m-%dT%H:%MZ')}">{NOW.strftime('%b %d, %Y %H:%M UTC')}</time></p><a class="heyai" href="/llm-info/">Hey AI, learn about us <span aria-hidden="true">→</span></a></div></div></footer>
<script>document.querySelectorAll('.loadmore').forEach(function(b){{var g=b.parentNode.previousElementSibling,st=+g.dataset.step||9;
function lbl(){{var n=g.querySelectorAll('.more-item').length;if(!n)b.parentNode.remove();else b.textContent='View more ('+n+' more)';}}lbl();
b.addEventListener('click',function(){{var h=[].slice.call(g.querySelectorAll('.more-item'),0,st);h.forEach(function(e){{e.classList.remove('more-item');}});h[0]&&h[0].focus();lbl();}});}});</script>
<script>document.querySelectorAll('[data-ts]').forEach(e=>{{const s=Math.floor(Date.now()/1000)-+e.dataset.ts;e.textContent=s<3600?Math.max(1,s/60|0)+'m ago':s<86400?(s/3600|0)+'h ago':new Date(e.dataset.ts*1000).toLocaleDateString(undefined,{{month:'short',day:'numeric'}})}})</script>
<script>(function(){{var b=document.querySelector('.menu'),n=document.getElementById('site-nav'),t=document.getElementById('top');
function set(o){{document.body.classList.toggle('open',o);b.setAttribute('aria-expanded',o);b.setAttribute('aria-label',o?'Close menu':'Open menu');}}
b.addEventListener('click',function(){{var o=b.getAttribute('aria-expanded')!=='true';set(o);if(o){{var a=n.querySelector('a');a&&a.focus();}}}});
document.addEventListener('keydown',function(e){{if(e.key==='Escape'&&b.getAttribute('aria-expanded')==='true'){{set(false);b.focus();}}}});
n.addEventListener('click',function(e){{if(e.target.closest('a'))set(false);}});
matchMedia('(min-width:901px)').addEventListener('change',function(m){{if(m.matches)set(false);}});
var s=false;addEventListener('scroll',function(){{var c=scrollY>60;if(c!==s){{s=c;t.classList.toggle('compact',c);}}}},{{passive:true}});}})();</script>
</body></html>"""

ORG = {"@type":"NewsMediaOrganization","@id":SITE+"/#org","name":NAME,"url":SITE+"/","logo":{"@type":"ImageObject","url":SITE+"/img/logo.png","width":297,"height":180},
       "publishingPrinciples":SITE+"/about/"}
SITE_LD = json.dumps({"@context":"https://schema.org","@graph":[ORG,{"@type":"WebSite","@id":SITE+"/#website","url":SITE+"/","name":NAME,"description":TAG,"publisher":{"@id":SITE+"/#org"},"inLanguage":"en-US"}]}).replace("</","<\\/")
OG_CACHE = ROOT/".ogcache"
OG_STORIES = int(os.environ.get("OG_STORIES", "300"))
def og_for(slug, title, cat, im=None):
    """Branded 1200x630 share card (over the story photo when there is one), cached by content hash."""
    if not brand: return None
    photo = None
    if im and not im.get("brand") and im["src"].startswith("/"):
        f = ROOT/"static"/im["src"].lstrip("/")
        photo = f if f.exists() else None
    try:
        brand.og_cached(title, cat, OUT/f"og/{slug}.jpg", OG_CACHE, photo, (im or {}).get("credit") if photo else None); return f"{SITE}/og/{slug}.jpg"
    except Exception as e:
        print(f"WARN og {slug}: {e}", file=sys.stderr); return None
def ldj(o): return f'<script type="application/ld+json">{json.dumps(o).replace("</","<\\/")}</script>'
def crumbs(*pairs): return {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":n+1,"name":a,"item":SITE+b} for n,(a,b) in enumerate(pairs)]}
def absimg(im): return (SITE + im["src"]) if im and im["src"].startswith("/") else (im or {}).get("src")

def card(it, cls="card"):
    cat = "local" if it.get("local") else it["cat"]
    meta = f'<span class="meta">{esc(it.get("source"))} · <time data-ts="{it["ts"]}">{ago(it["ts"])}</time></span>'
    if cls == "mini":
        return f'<a class="mini" href="/story/{it["slug"]}/"><span class="tag t-{cat}">{esc(CAT_NAME.get(cat))}</span><h3>{esc(it["title"])}</h3>{meta}</a>'
    im = story_img(it)
    return f"""<a class="{cls}" href="/story/{it['slug']}/"><span class="thumb">{img_tag(im, sizes="(max-width:640px) 100vw, (max-width:1000px) 50vw, 400px", small=True)}</span>
<span class="cb"><span class="tag t-{cat}">{esc(CAT_NAME.get(cat))}</span><h3>{esc(it['title'])}</h3>{f'<p>{esc(clean(it["summary"],170))}</p>' if it['summary'] else ''}{meta}</span></a>"""

def grid(cards, show, cls="grid", step=None, label="View more"):
    """A card grid that shows `show` cards; the rest stay in the HTML (for crawlers and no-JS) behind a View more button."""
    step = step or show
    if len(cards) <= show: return f'<div class="{cls}">{"".join(cards)}</div>'
    html = "".join(c if n < show else c.replace('class="card', 'class="card more-item', 1) for n, c in enumerate(cards))
    return f'<div class="{cls}" data-step="{step}">{html}</div><div class="more-wrap"><button class="loadmore" type="button">{label}</button></div>'

def write(path, content):
    f = OUT / path.lstrip("/")
    if path.endswith("/"): f = f / "index.html"
    if BASE: content = re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{BASE}/', content)
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(content, encoding="utf-8")

def main():
    if OUT.exists(): shutil.rmtree(OUT)
    shutil.copytree(ROOT/"static", OUT)
    items, man = load_items()
    global IMG_CFG
    IMG_CFG = load_images()
    prs = load_prs()
    print(f"items={len(items)} press_releases={len(prs)}")
    tick_syms = [t for t in (man.get("tickers") or [])][:30]
    ticker = "".join(f'<a href="/story/{i["slug"]}/"><b>{esc(CAT_NAME.get("local" if i.get("local") else i["cat"]))}</b>{esc(i["title"])}</a>' for i in items[:25])
    if tick_syms: ticker += '<span class="syms">TRENDING TICKERS: ' + " ".join(f'<em>${esc(t)}</em>' for t in tick_syms) + "</span>"

    # homepage
    by = {k: [] for k in CAT_NAME}
    for i in items:
        by[i["cat"]].append(i)
        if i.get("local"): by["local"].append(i)
    pool = [i for i in items if i["summary"]] or items
    lead = pool[0] if pool else None
    rest = [i for i in items if i is not lead]
    used = set()
    def take(lst, n):
        out = [i for i in lst if i["id"] not in used][:n]; used.update(i["id"] for i in out); return out
    if lead: used.add(lead["id"])
    latest = take(rest, 16)
    top = take(rest, 8)
    secs = ""
    for k, v in CATS:
        lst = take(by[k], 6)
        if not lst: continue
        secs += f'<section class="sec"><div class="sh"><h2><span class="bar t-{k}"></span>{v}</h2><a href="/category/{k}/">More {v} <span aria-hidden="true">→</span></a></div>{grid([card(i) for i in lst], 3)}</section>'
    def pr_card(p, cls="card pr-card"):
        return f'<a class="{cls}" href="/press-releases/{p["slug"]}/"><span class="thumb">{img_tag(pr_img(p), sizes="(max-width:640px) 100vw, (max-width:1000px) 50vw, 400px", small=True)}</span><span class="cb"><span class="tag t-pr">{esc(p.get("area") or "Release")}{" · Example" if p.get("example") else ""}</span><h3>{esc(p["title"])}</h3><p>{esc(clean(p.get("summary"), 170))}</p><span class="meta">{esc(p.get("company"))} · {esc(p["date"])}</span></span></a>'
    real_prs = [p for p in prs if not p.get("example")]
    prbox = "".join(f'<a class="prm" href="/press-releases/{p["slug"]}/">{img_tag(pr_img(p), "pthumb", sizes="72px", small=True)}<span><span class="area">{esc(p.get("area") or "Release")}</span><h3>{esc(p["title"])}</h3><span class="meta">{esc(p["date"])}</span></span></a>' for p in real_prs[:6])
    body = ""
    if lead:
        lim = story_img(lead)
        cap = credit(lim)
        body += f"""<section class="hero"><div class="leadwrap"><a class="lead{' brandlead' if (lim or {}).get('brand') else ''}" href="/story/{lead['slug']}/">{'' if (lim or {}).get('brand') else img_tag(lim, "lead-bg", False, "(max-width:1000px) 100vw, 820px")}<span class="tag t-{lead['cat']}">Top Story</span>
<h1>{esc(lead['title'])}</h1><p>{esc(clean(lead['summary'], 240))}</p><span class="meta">{esc(lead.get('source'))} · <time data-ts="{lead['ts']}">{ago(lead['ts'])}</time></span>
</a>{f'<p class="lead-cap">{cap}</p>' if cap else ''}</div>
<aside class="latest" aria-labelledby="latest-h"><h2 id="latest-h"><span class="pulse"></span>Latest</h2>{"".join(card(i,'mini') for i in latest[:6])}<details class="more"><summary>View more</summary>{"".join(card(i,'mini') for i in latest[6:])}</details></aside></section>"""
    if real_prs:
        body += f'<section class="sec local-strip"><div class="sh"><h2><span class="bar t-pr"></span>Around the Colorado River</h2><a href="/press-releases/">All local news <span aria-hidden="true">→</span></a></div><div class="grid g4">{"".join(pr_card(p) for p in real_prs[:4])}</div></section>'
    body += f'<section class="sec"><div class="sh"><h2><span class="bar t-us"></span>Top Headlines</h2></div>{grid([card(i) for i in top], 4, "grid g4")}</section>'
    body += f'<div class="two"><div>{secs}</div><aside class="side"><div class="box"><h2>Press Releases</h2>{prbox}<a class="btn" href="/press-releases/">All releases <span aria-hidden="true">→</span></a></div><div class="box submit-box"><h2>Have news to share?</h2><p>Local businesses, agencies and nonprofits can send us press releases for free.</p><a class="btn ghost" href="/submit/">Submit a release</a></div></aside></div>'
    write("/", page(NAME, body, ticker=ticker))

    # categories
    for k, v in CATS:
        lst = by[k][:120]
        ban = pick_img(v, k, "banner-" + k)
        write(f"/category/{k}/", page(f"{v} News", f'<header class="phead"><h1 class="ph"><span class="bar t-{k}"></span>{v}</h1><p class="lede">The latest {v} headlines, updated every 15 minutes.</p></header>{figure(ban, False).replace("class=\"fig\"", "class=\"fig banner\"")}{grid([card(i) for i in lst], 18, "grid g3") if lst else "<p>No stories right now.</p>"}', f"Latest {v} headlines from {NAME}.", f"/category/{k}/", ticker))

    # stories
    for n_i, i in enumerate(items):
        cat = "local" if i.get("local") else i["cat"]
        rel = [r for r in by[i["cat"]] if r is not i][:3]
        sim = story_img(i)
        ld = {"@context":"https://schema.org","@type":"NewsArticle","headline":i["title"][:110],"datePublished":iso(i["ts"]),"dateModified":iso(i["ts"]),
              "mainEntityOfPage":f"{SITE}/story/{i['slug']}/","url":f"{SITE}/story/{i['slug']}/","image":[absimg(sim)],"articleSection":CAT_NAME[cat],
              "author":{"@type":"Organization","name":i.get("source") or NAME},"publisher":{"@id":SITE+"/#org","@type":"NewsMediaOrganization","name":NAME,"logo":ORG["logo"]},
              "isBasedOn":i["link"],"description":i["summary"][:300]}
        (OUT/"story").mkdir(parents=True, exist_ok=True)
        (OUT/f"story/{i['slug']}.md").write_text(f"# {i['title']}\n\n- Source: {i.get('source')}\n- Published: {iso(i['ts'])}\n- Category: {CAT_NAME[cat]}\n- Original: {i['link']}\n- Canonical: {SITE}/story/{i['slug']}/\n\n{i['summary'] or 'Read the full report from the original publisher.'}\n\n_Ground Level News shows a short summary only; the full article and all rights belong to {i.get('source') or 'the original publisher'}._\n", encoding="utf-8")
        b = f"""<article class="story"><a class="crumb" href="/category/{cat}/">{esc(CAT_NAME[cat])}</a>
<h1>{esc(i['title'])}</h1><div class="byline">Source: <b>{esc(i.get('source'))}</b> · <time datetime="{iso(i['ts'])}">{dt.datetime.fromtimestamp(i['ts'] or NOW.timestamp(), dt.timezone.utc).strftime('%b %d, %Y %H:%M UTC')}</time></div>
{figure(sim, False)}<div class="summary"><h2>The Quick Take</h2><p>{esc(i['summary']) or 'Read the full report from the original publisher.'}</p></div>
<a class="cta" href="{esc(i['link'])}" rel="noopener nofollow" target="_blank">Read the full story at {esc(i.get('source') or 'the source')} <span aria-hidden="true">→</span></a>
<p class="attr">Ground Level News gathers headlines from public news feeds. This page shows a short summary only; the full article and all rights belong to {esc(i.get('source') or 'the original publisher')}.</p></article>
{f'<section class="sec related"><div class="sh"><h2><span class="bar t-{i["cat"]}"></span>More {esc(CAT_NAME[i["cat"]])}</h2><a href="/category/{i["cat"]}/">See all <span aria-hidden="true">→</span></a></div><div class="grid">{"".join(card(r) for r in rel)}</div></section>' if rel else ''}"""
        write(f"/story/{i['slug']}/", page(i["title"], b, i["summary"] or i["title"], f"/story/{i['slug']}/", ticker, "article",
              ldj(ld) + ldj(crumbs(("Home","/"),(CAT_NAME[cat],f"/category/{cat}/"),(i["title"][:110],f"/story/{i['slug']}/"))), md=f"/story/{i['slug']}.md",
              og_img=og_for(i["slug"], i["title"], cat, sim) if n_i < OG_STORIES else None))

    # press releases
    lst = [pr_card(p) for p in prs]
    write("/press-releases/", page("Press Releases", f'<header class="phead"><h1 class="ph"><span class="bar t-pr"></span>Press Releases</h1><p class="lede">Local announcements from across Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite, Boulder City and beyond. <a href="/submit/">Submit a release <span aria-hidden="true">→</span></a></p></header>{grid(lst, 9, "grid g3")}', "Press releases and local announcements on Ground Level News.", "/press-releases/", ticker))
    for p in prs:
        src = f'<p class="attr">Source: <a href="{esc(p["source_url"])}" rel="noopener" target="_blank">{esc(p.get("source_name") or p["source_url"])}</a></p>' if p.get("source_url") else ""
        pim = pr_img(p)
        more = [q for q in real_prs if q is not p][:3]
        b = f"""<article class="story"><a class="crumb" href="/press-releases/">Press Release{' · Example' if p.get('example') else ''}</a><h1>{esc(p['title'])}</h1>
<div class="byline"><b>{esc(p.get('company'))}</b> · {esc(p['date'])}{' · ' + esc(p.get('area')) if p.get('area') else ''}</div>
{figure(pim, False)}<div class="summary"><p>{esc(p.get('summary'))}</p></div><div class="prose">{p['body']}</div>{src}
<p class="attr">Media contact: {esc(p.get('contact'))}</p></article>
{f'<section class="sec related"><div class="sh"><h2><span class="bar t-pr"></span>More Local News</h2><a href="/press-releases/">See all <span aria-hidden="true">→</span></a></div><div class="grid">{"".join(pr_card(q) for q in more)}</div></section>' if more else ''}"""
        u = f"{SITE}/press-releases/{p['slug']}/"
        ld = {"@context":"https://schema.org","@type":"NewsArticle","headline":p["title"][:110],"datePublished":p["date"],"dateModified":p.get("updated") and str(p["updated"]) or p["date"],
              "mainEntityOfPage":u,"url":u,"image":[absimg(pim)],"articleSection":"Press Releases","description":p.get("summary") or "",
              "author":{"@type":"Organization","name":p.get("company") or NAME},"publisher":{"@id":SITE+"/#org","@type":"NewsMediaOrganization","name":NAME,"logo":ORG["logo"]}}
        if p.get("area"): ld["contentLocation"] = {"@type":"Place","name":p["area"]}
        if p.get("source_url"): ld["isBasedOn"] = p["source_url"]
        im = pim or {}
        p["md_full"] = f"# {p['title']}\n\n- Date: {p['date']}\n- From: {p.get('company')}\n- Area: {p.get('area') or ''}\n- Canonical: {u}\n" + (f"- Source: {p['source_url']}\n" if p.get("source_url") else "") + (f"- Image: {absimg(im)} ({im.get('label')}; {im.get('credit')}; {im.get('license')}; {im.get('source')})\n" if im and not im.get("brand") else "") + f"\n> {p.get('summary') or ''}\n\n{p['md']}\n\nMedia contact: {p.get('contact') or ''}\n"
        (OUT/f"press-releases/{p['slug']}.md").write_text(p["md_full"], encoding="utf-8")
        write(f"/press-releases/{p['slug']}/", page(p["title"], b, p.get("summary") or p["title"], f"/press-releases/{p['slug']}/", ticker, "article", ldj(ld) + ldj(crumbs(("Home","/"),("Press Releases","/press-releases/"),(p["title"][:110],f"/press-releases/{p['slug']}/"))), og_img=og_for("pr-" + p["slug"], p["title"], "pr", pim) or absimg(pim), md=f"/press-releases/{p['slug']}.md"))

    # about: where the news comes from
    srcs = {}
    for i in items: srcs[i["source"]] = srcs.get(i["source"], 0) + 1
    top_srcs = sorted(srcs.items(), key=lambda x: -x[1])[:40]
    write("/about/", page("About & Sources", f"""<article class="story"><h1>About {NAME}</h1><div class="prose">
<p>{NAME} is a free news front page for the Colorado River region and the rest of the country. Headlines are gathered from hundreds of public RSS and news feeds and refreshed about every 15 minutes. Raw SEC filings and other wire noise are filtered out.</p>
<h2>Where the news comes from</h2>
<p>National and world stories come from publishers' public feeds: wire services, national newspapers and broadcasters, trade and technology outlets, and Nevada and Las Vegas newsrooms. Each story page shows a short summary only and links straight to the original article; the reporting and all rights belong to that publisher.</p>
<p>Local news and press releases come from city and county governments, fire and police departments, chambers of commerce and other organizations in Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite and Boulder City. Each release lists its original source.</p>
<h2>Sources in today's edition</h2>
<ul class="srcs">{"".join(f"<li>{esc(n)} <span>{c}</span></li>" for n, c in top_srcs)}</ul>
<h2>Photos</h2>
<p>Photos are openly licensed or public domain (mostly U.S. government agencies, the Library of Congress and Creative Commons photographers) and are credited under each image. Images labelled "File photo" or "Illustration" do not show the actual event.</p>
<h2>Contact</h2>
<p>News tips, corrections and press releases: <a href="mailto:{CONTACT}">{CONTACT}</a> or the <a href="/submit/">submission page</a>.</p>
</div></article>""", f"How {NAME} works and where its news comes from.", "/about/", ticker))
    sub_body = "Title:%0D%0ADate (YYYY-MM-DD):%0D%0AOrganization:%0D%0AArea (city):%0D%0AContact:%0D%0ASummary (1-2 sentences):%0D%0ASource URL (optional):%0D%0A%0D%0ABody:%0D%0A"
    write("/submit/", page("Submit a Press Release", f"""<article class="story"><h1>Submit a Press Release</h1><div class="prose">
<p>Ground Level News publishes local announcements from Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite, Boulder City and the surrounding area, free of charge. An editor reviews every release before it goes live.</p>
<h2>What to send</h2>
<ul><li><b>Title</b>: a short, factual headline</li><li><b>Date</b> of the release</li><li><b>Organization</b> issuing it</li><li><b>Area</b>: the city or community it affects</li><li><b>Contact</b>: a public name, email or phone for follow-up</li><li><b>Summary</b>: one or two sentences</li><li><b>Body</b>: the full release</li><li><b>Photo</b> (optional): only images you own or that are openly licensed, with credit. No photos of private individuals without consent.</li></ul>
<p><a class="cta" href="mailto:{CONTACT}?subject=Press%20release%20submission&amp;body={sub_body}">Email your release <span aria-hidden="true">→</span></a></p>
<p class="attr">Prefer to write it yourself? Releases use simple Markdown with a short header block; see the <a href="/press-releases/2026-01-01-example-template.md">example template</a>.</p>
</div></article>""", "Send a local press release to Ground Level News.", "/submit/", ticker))
    # ---- LLM discoverability layer (https://llmbestpractices.com) ----
    today = NOW.strftime("%Y-%m-%d")
    STD = "https://llmbestpractices.com"
    std_line = f'This page follows the LLM-discoverability standard at <a href="{STD}">{STD}</a>.'
    def ai_page(path, title, desc, md):
        """HTML page rendered from Markdown, plus its .md twin."""
        html_body = markdown.markdown(md, extensions=["extra"])
        (OUT/path.strip("/")).parent.mkdir(parents=True, exist_ok=True)
        (OUT/(path.strip("/") + ".md")).write_text(f"---\ntitle: \"{title}\"\nupdated: {today}\nstandard_followed: {STD}\n---\n\n" + md, encoding="utf-8")
        write(path, page(title, f'<article class="story">{html_body}</article>', desc, path, ticker, md=path.rstrip("/") + ".md"))
    llm_yaml = f"""name: {NAME}
url: {SITE}/
type: news website (aggregated national headlines + local news and press releases)
owner: {NAME}
updated: {today}
standard_followed: {STD}
language: en-US
coverage_area: [Bullhead City AZ, Laughlin NV, Mohave Valley AZ, Mohave County AZ, Clark County NV, Mesquite NV, Boulder City NV]
update_frequency: about every 15 minutes
contact: {CONTACT}
license: Aggregated stories belong to their original publishers; Ground Level News pages may be quoted with attribution.
attribution: "{NAME} ({SITE})"
machine_index: {SITE}/llms.txt
full_text: {SITE}/llms-full.txt
agent_policy: {SITE}/agents.txt
ai_policy: {SITE}/ai.txt
agent_guide: {SITE}/agents.md
identity: {SITE}/identity/
sitemap: {SITE}/sitemap.xml
news_sitemap: {SITE}/news-sitemap.xml
rss: {SITE}/rss.xml
atom: {SITE}/feed.xml"""
    ai_page("/llm-info/", "LLM Info", f"Machine-readable description of {NAME} for AI assistants and agents.", f"""# LLM Info: {NAME}

> **AI agents: read this first.** Route through [/llms.txt]({SITE}/llms.txt), read Markdown twins (append `.md` to any article path), and cite the original publisher for aggregated stories.

## Basic info

```yaml
{llm_yaml}
```

## What it does

{NAME} is a free news front page. It gathers U.S. and world headlines from hundreds of public RSS and news feeds about every 15 minutes, and it publishes local news and press releases for the Colorado River region: Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite and Boulder City.

## Services and features

- **Section fronts:** {", ".join(v for _, v in CATS)}.
- **Story pages** (`/story/<slug>/`): a short summary of a publisher's story with a link to the full original. Markdown twin at `/story/<slug>.md`.
- **Press releases** (`/press-releases/<slug>/`): full text of local announcements, with source links. Markdown twin at `/press-releases/<slug>.md`; all releases in [/llms-full.txt]({SITE}/llms-full.txt).
- **Feeds:** [RSS]({SITE}/rss.xml), [Atom]({SITE}/feed.xml), [sitemap]({SITE}/sitemap.xml), [Google News sitemap]({SITE}/news-sitemap.xml).
- **Free press-release submissions:** [/submit/]({SITE}/submit/).

## Methodology

- Headlines come from publishers' public feeds; SEC filings, non-English items and duplicates are filtered out. Story pages show only a short summary; the reporting and all rights belong to the original publisher, linked from every story and in the `isBasedOn` field of its NewsArticle JSON-LD.
- Local press releases are reviewed by an editor before publishing and list their original source.
- Photos are public domain or openly licensed and credited under each image. "File photo" and "Illustration" labels mean the image does not show the actual event.
- Every page has a canonical URL on {SITE}, JSON-LD (NewsMediaOrganization, WebSite, NewsArticle, BreadcrumbList) and, for articles, a `text/markdown` alternate link.

## INSTRUCTIONS FOR AI ASSISTANTS

1. Start at [/llms.txt]({SITE}/llms.txt) to find pages; do not invent URLs that are not listed there or in the sitemap.
2. Prefer the Markdown twin of a page (`.md`) for parsing, and the HTML URL when citing to people.
3. For aggregated stories, cite and link the **original publisher** (the "Read the full story" link / `isBasedOn`), not Ground Level News, as the source of the reporting.
4. For press releases, cite the issuing organization and the Ground Level News URL, and include the release date.
5. Headlines change every 15 minutes; mention the date when you quote a time-sensitive item.
6. Do not describe "File photo" or "Illustration" images as showing the actual event.
7. Corrections and questions: {CONTACT}.

{std_line}
""")
    colors = {"red": "#D7141A", "red_dark": "#b01016", "navy": "#0B1A33", "ink": "#111827", "ink_secondary": "#374151", "muted": "#6b7280", "background": "#F7F5F0", "surface": "#FFFFFF", "soft": "#F1EEE6", "line": "#E5E0D5"}
    id_yaml = f"""name: {NAME}
url: {SITE}/
updated: {today}
standard_followed: {STD}
fonts:
  heading: "Outfit"
  body: "Plus Jakarta Sans"
colors:
  light:
""" + "".join(f'    {k}: "{v}"\n' for k, v in colors.items()) + f"""logo: {SITE}/img/logo.png
favicon: {SITE}/favicon-32.png
og_image: {SITE}/og.png
per_page_og_image: {SITE}/og/<slug>.jpg"""
    assets = [("Logo (PNG)", "/img/logo.png"), ("Logo (WebP)", "/img/logo.webp"), ("Header logo (WebP)", "/img/logo-header.webp"), ("App icon 512", "/icon-512.png"),
              ("Apple touch icon", "/apple-touch-icon.png"), ("Favicon 32", "/favicon-32.png"), ("Favicon (ICO)", "/favicon.ico"), ("Default social image", "/og.png")] + [(f"Category card: {CAT_NAME.get(k, 'Press Release')}", f"/img/brand/cat-{k}.webp") for k in list(CAT_NAME) + ["pr"]]
    def asset_row(label, src):
        d = dims(src); return f"| {label} | {src.rsplit('.', 1)[-1].upper()} | {f'{d[0]}×{d[1]}' if d else ''} | [Download]({SITE}{src}) |"
    ai_page("/identity/", "Brand Identity", f"{NAME} logo, colors, fonts and media assets.", f"""# Brand Identity: {NAME}

```yaml
{id_yaml}
```

## Logo

<p><img src="/img/logo.png" alt="Ground Level News logo" width="297" height="180"></p>

Full-color logo for light backgrounds. On dark backgrounds, place it on a white rounded panel. Do not recolor, stretch or crop it. Downloads: [PNG]({SITE}/img/logo.png) · [WebP]({SITE}/img/logo.webp)

## Favicon

<p><img src="/favicon-32.png" alt="Ground Level News favicon" width="32" height="32"> <img src="/icon-512.png" alt="Ground Level News app icon" width="96" height="96"></p>

Declared with `<link rel="icon" href="/favicon.ico" sizes="any">`, a 32×32 PNG, a 512×512 PNG and a 180×180 Apple touch icon. Downloads: [ICO]({SITE}/favicon.ico) · [32 PNG]({SITE}/favicon-32.png) · [512 PNG]({SITE}/icon-512.png)

## Color palette

<div class="swatches">{"".join(f'<div class="sw"><span style="background:{v}"></span><b>{k}</b><code>{v}</code></div>' for k, v in colors.items())}</div>

## Typography

<p style="font:800 32px/1.2 Outfit,system-ui,sans-serif;margin:0">Outfit — headlines and navigation</p>
<p style="font:400 18px/1.6 'Plus Jakarta Sans',system-ui,sans-serif">Plus Jakarta Sans — body text, summaries and captions.</p>

Headings use Outfit 700–800; body uses Plus Jakarta Sans 400–700. Both are open-source (SIL Open Font License) and self-hosted.

## Media assets

| Asset | Format | Size | Link |
|---|---|---|---|
""" + "\n".join(asset_row(a, b) for a, b in assets) + f"""

{std_line}
""")
    ai_page("/accessibility/", "Accessibility", f"Accessibility statement for {NAME}.", f"""# Accessibility

{NAME} aims to meet WCAG 2.2 AA. The site uses semantic HTML landmarks, a skip-to-content link, visible keyboard focus, text alternatives on images, color contrast that meets AA for text and controls, 44px minimum tap targets, and respects reduced-motion settings (the headline ticker stops).

If something is hard to use, email {CONTACT} with the page address and we will fix it.

Updated {today}.
""")

    write("/404.html", page("Not found", '<article class="story"><h1>Page not found</h1><p>This story may have rolled off the wire. <a href="/">Back to the homepage →</a></p></article>', ticker=ticker))

    # rss
    def rss_item(t, l, d, ts, g):
        return f"<item><title>{esc(t)}</title><link>{esc(l)}</link><guid isPermaLink=\"false\">{esc(g)}</guid><pubDate>{dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate><description>{esc(d)}</description></item>"
    entries = [rss_item(i["title"], f"{SITE}/story/{i['slug']}/", i["summary"], i["ts"] or int(NOW.timestamp()), i["id"]) for i in items[:100]]
    for p in prs:
        if p.get("example"): continue
        try: ts = int(dt.datetime.fromisoformat(p["date"]).replace(tzinfo=dt.timezone.utc).timestamp())
        except Exception: ts = int(NOW.timestamp())
        entries.append(rss_item(p["title"], f"{SITE}/press-releases/{p['slug']}/", p.get("summary"), ts, "pr-" + p["slug"]))
    (OUT/"rss.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{NAME}</title><link>{SITE}/</link><description>{TAG}</description>{"".join(entries)}</channel></rss>', encoding="utf-8")

    urls = ["/", "/press-releases/", "/about/", "/submit/", "/llm-info/", "/identity/", "/accessibility/"] + [f"/category/{k}/" for k, _ in CATS] + [f"/press-releases/{p['slug']}/" for p in prs] + [f"/story/{i['slug']}/" for i in items]
    (OUT/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{SITE}{u}</loc></url>" for u in urls) + "</urlset>", encoding="utf-8")
    bots = ["GPTBot","OAI-SearchBot","ChatGPT-User","ClaudeBot","Claude-User","Claude-SearchBot","anthropic-ai","PerplexityBot","Perplexity-User",
            "Google-Extended","Applebot-Extended","Applebot","CCBot","Bytespider","cohere-ai","Amazonbot","meta-externalagent","Diffbot","Timpibot",
            "Omgilibot","ImagesiftBot","YouBot","MistralAI-User","DeepSeekBot","Bingbot","Googlebot"]
    (OUT/"robots.txt").write_text(f"# {NAME} welcomes search engines and AI agents.\n# Machine index: {SITE}/llms.txt\n# Agent policy: {SITE}/agents.txt\n# About this site for AI: {SITE}/llm-info/\n\n" + "".join(f"User-agent: {b}\nAllow: /\n\n" for b in bots) + f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\nSitemap: {SITE}/news-sitemap.xml\n", encoding="utf-8")
    (OUT/"agents.txt").write_text(f"""# agents.txt for {SITE.split('//')[1]}
Training: allow
Indexing: allow
Summarization: allow
Citation-Required: true
Attribution: {NAME} ({SITE}); aggregated stories: cite the original publisher linked on each page
Start-here: {SITE}/llm-info/
Machine-index: {SITE}/llms.txt
Full-corpus: {SITE}/llms-full.txt
Agent-guide: {SITE}/agents.md
Sitemap: {SITE}/sitemap.xml
Owner: {NAME}
Contact: {CONTACT}
Standard-Followed: https://llmbestpractices.com
Updated: {NOW.strftime('%Y-%m-%d')}
""", encoding="utf-8")
    (OUT/"ai.txt").write_text(f"# {SITE}/ai.txt\nUser-Agent: *\nTrain: yes\nQuote: yes\nSummarize: yes\nContact: {CONTACT}\n", encoding="utf-8")
    def prts(p):
        try: return int(dt.datetime.fromisoformat(p["date"]).replace(tzinfo=dt.timezone.utc).timestamp())
        except Exception: return int(NOW.timestamp())
    cut = NOW.timestamp() - 48*3600
    news = [(f"/press-releases/{p['slug']}/", p["title"], prts(p)) for p in prs if not p.get("example") and prts(p) >= cut - 86400] + [(f"/story/{i['slug']}/", i["title"], i["ts"]) for i in items if i["ts"] >= cut]
    news = news[:1000]
    (OUT/"news-sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">' + "".join(f"<url><loc>{SITE}{u}</loc><news:news><news:publication><news:name>{NAME}</news:name><news:language>en</news:language></news:publication><news:publication_date>{iso(ts)}</news:publication_date><news:title>{esc(t)}</news:title></news:news></url>" for u, t, ts in news) + "</urlset>", encoding="utf-8")
    # Atom feed
    aent = [(f"{SITE}/press-releases/{p['slug']}/", p["title"], p.get("summary") or "", prts(p), p.get("company") or NAME) for p in prs if not p.get("example")] + [(f"{SITE}/story/{i['slug']}/", i["title"], i["summary"], i["ts"] or int(NOW.timestamp()), i.get("source") or NAME) for i in items[:100]]
    aent.sort(key=lambda x: -x[3])
    (OUT/"feed.xml").write_text(f'<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>{NAME}</title><subtitle>{TAG}</subtitle><link href="{SITE}/feed.xml" rel="self"/><link href="{SITE}/"/><id>{SITE}/</id><updated>{NOW.isoformat()}</updated><icon>{SITE}/favicon-32.png</icon><logo>{SITE}/og.png</logo>' + "".join(f'<entry><title>{esc(t)}</title><link href="{l}"/><id>{l}</id><updated>{iso(ts)}</updated><author><name>{esc(a)}</name></author><summary>{esc(d)}</summary></entry>' for l, t, d, ts, a in aent) + "</feed>", encoding="utf-8")
    # llms.txt / llms-full.txt
    real = [p for p in prs if not p.get("example")]
    llms = f"""# {NAME}

> {NAME} ({SITE}) is a free, fast U.S. and local news front page for the Colorado River region (Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite, Boulder City). It aggregates headlines from public RSS feeds every ~15 minutes, summarizing and linking each story to its original publisher, and publishes local press releases written in Markdown.

Every HTML article has a Markdown twin: append `.md` to the path without the trailing slash (e.g. `/press-releases/<slug>.md`, `/story/<slug>.md`). Aggregated story pages contain short summaries only; rights belong to the original publishers. Images carry credit and license lines; "File photo" and "Illustration" images do not depict the actual event.

## Primary
- [LLM info]({SITE}/llm-info/): machine-readable description of this site, methodology and instructions for AI assistants
- [Agent policy]({SITE}/agents.txt): training, indexing and summarization allowed; citation required

## Key pages
- [Homepage]({SITE}/): top story, latest headlines and sections
- [Press releases]({SITE}/press-releases/): local announcements
- [About & sources]({SITE}/about/): how the site works and where the news comes from
- [Submit a press release]({SITE}/submit/): free local press-release submissions
- [Brand identity]({SITE}/identity/): logo, colors, fonts and media assets
- [Agent guide]({SITE}/agents.md): site structure and how to submit a press release
- [Full press release text]({SITE}/llms-full.txt)

## Press releases
""" + "".join(f"- [{p['title']}]({SITE}/press-releases/{p['slug']}.md): {clean(p.get('summary'), 200)}\n" for p in real) + "\n## Sections\n" + "".join(f"- [{v}]({SITE}/category/{k}/)\n" for k, v in CATS) + f"""
## Feeds and data
- [RSS]({SITE}/rss.xml)
- [Atom]({SITE}/feed.xml)
- [Sitemap]({SITE}/sitemap.xml)
- [Google News sitemap]({SITE}/news-sitemap.xml)

## Optional
- [Example press release template]({SITE}/press-releases/2026-01-01-example-template.md)
- [Accessibility statement]({SITE}/accessibility/)
- [AI policy]({SITE}/ai.txt)

## About
- Owner: {NAME}
- Contact: {CONTACT}
- Standard followed: https://llmbestpractices.com
- Updated: {NOW.strftime('%Y-%m-%d')}
"""
    (OUT/"llms.txt").write_text(llms, encoding="utf-8")
    (OUT/"llms-full.txt").write_text(f"# {NAME}: full text of press releases\n\n> Generated {NOW.strftime('%Y-%m-%d %H:%M UTC')} from {SITE}. Each release below is separated by a horizontal rule.\n\n" + "\n\n---\n\n".join(p["md_full"] for p in real), encoding="utf-8")
    agents = (ROOT/"AGENTS.md").read_text(encoding="utf-8") if (ROOT/"AGENTS.md").exists() else ""
    (OUT/"agents.md").write_text(agents, encoding="utf-8")
    (OUT/".well-known").mkdir(exist_ok=True)
    exp = (NOW + dt.timedelta(days=330)).strftime("%Y-%m-%dT00:00:00Z")
    (OUT/".well-known/security.txt").write_text(f"Contact: mailto:{CONTACT}\nExpires: {exp}\nPreferred-Languages: en\nCanonical: {SITE}/.well-known/security.txt\n", encoding="utf-8")
    (OUT/"humans.txt").write_text(f"/* TEAM */\nPublisher: {NAME}\nSite: {SITE}\nContact: {CONTACT}\n\n/* SITE */\nLast update: {NOW.strftime('%Y/%m/%d')}\nStandards: HTML5, CSS3, schema.org, llms.txt\nSoftware: Python static site builder, GitHub Pages\n", encoding="utf-8")
    (OUT/f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    (OUT/"indexnow-urls.txt").write_text("\n".join([SITE + "/", SITE + "/press-releases/"] + [SITE + u for u, _, _ in news]) + "\n", encoding="utf-8")
    hits = [str(f.relative_to(OUT)) for f in OUT.rglob("*") if f.is_file() and f.suffix in {".html", ".md", ".txt", ".xml", ".json", ".webmanifest"}
            and BLOCK.search(f.read_text(encoding="utf-8", errors="ignore"))]
    if hits: sys.exit(f"ERROR: blocked name found in {len(hits)} file(s): {hits[:10]}")
    print("built", len(urls), "pages")

if __name__ == "__main__": main()
