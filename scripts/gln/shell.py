"""Page chrome (header, nav, "Just in" strip, footer), the card family and shared components, share-card hookup
and file writing. Owned by UI. Stable component API used by pages.py, local.py, editorial.py and llm_layer.py:

    page(title, body, desc, path, og_type, extra_head, og_img, md, robots=None, ld=None, preload_img=None, kicker=None,
         article=None, feeds=None, canonical=True, body_class="")
    card(it, size="lg|md|row|text", kicker=None, show_dek=True)      aggregated item or original (auto-detected)
    pr_card(p, size="md")                                              original (press release / brief / report)
    rows(items, size="row", limit=None)                                <div class="list"> of cards
    section_header(title, href=None, cat=None, more_label=None, tag="h2", id=None)
    chips(pairs, current=None, scroll=False)                           [(label, href)] -> <ul class="chips">
    grid(cards, show, cls="grid", step=None, label="Show more")        with a no-JS-safe "Show N more" button
    events_list(events)                                                "Happening this week" list (+ .ics links)
    cond_strip(html)                                                   wrapper for the conditions fragment
    og_for(slug, title, cat, im, source=None, date=None, kicker=None)  branded share card
    write(path, html)                                                  the only HTML writer
    set_justin(items), region_name(key), item_area(it), pr_region(p), fmt_date, time_tag, tile(label, kicker)
"""
import os, re, sys, inspect, itertools, pathlib
from . import config as CFG
from .config import ROOT, OUT, SITE, BASE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME, brand
from . import text as T
from .text import esc, clean
from .images import story_img, pr_img, img_tag, thumb, dims, cat_img
from . import head as H
try:
    from . import taxonomy as TX
except Exception:
    TX = None

# ---------- optional interfaces (other agents' modules may land later) ----------
REGIONS = getattr(TX, "REGIONS", None) or {}
LOCAL_AREAS = getattr(CFG, "LOCAL_AREAS", None) or [("bullhead-city", "Bullhead City", "/local/bullhead-city/"), ("laughlin", "Laughlin", "/local/laughlin/"),
    ("mohave-valley", "Mohave Valley", "/local/mohave-valley/"), ("lake-havasu-city", "Lake Havasu City", "/local/lake-havasu-city/"), ("kingman", "Kingman", "/local/kingman/"),
    ("clark-county", "Clark County", "/local/clark-county/"), ("mesquite", "Mesquite", "/local/mesquite/"), ("boulder-city", "Boulder City", "/local/boulder-city/")]
TOPIC_LINKS = getattr(CFG, "TOPIC_LINKS", None) or []
CAT_SHORT = getattr(CFG, "CAT_SHORT", None) or {**CAT_NAME, "tech": "Tech"}
NAV_CTA = getattr(CFG, "NAV_CTA", None) or ("Submit news", "/submit/")
_AREA_NAME = {k: v for k, v, _ in LOCAL_AREAS}
_HOME_KEYS = [k for k, r in REGIONS.items() if r.get("home")] or [k for k, _, _ in LOCAL_AREAS]
KIND_LABEL = {"press-release": "Press release", "brief": "Brief", "report": "Report", "event": "Event", "meeting": "Meeting", "gov": "Official"}

fmt_date = getattr(T, "fmt_date", None)
time_tag = getattr(T, "time_tag", None)
if not fmt_date:
    def fmt_date(v, style="rel"):   # pragma: no cover (text.py fallback)
        import datetime as dt
        ts = int(v) if isinstance(v, (int, float)) else int(NOW.timestamp())
        if style == "iso": return T.iso(ts)
        d = dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=-7)))
        return d.strftime("%b %-d, %Y, %-I:%M %p MST") if style == "long" else (d.strftime("%b %-d") if style == "short" else T.ago(ts))
if not time_tag:
    def time_tag(ts, style="rel", est=False, cls=""):   # pragma: no cover
        ts = int(ts or NOW.timestamp())
        return f'<time datetime="{T.iso(ts)}"{"" if est or style != "rel" else f" data-ts={chr(34)}{ts}{chr(34)}"}>{esc(fmt_date(ts, style))}</time>'

def region_name(key):
    r = REGIONS.get(key) if key else None
    return (r or {}).get("name") or _AREA_NAME.get(key) or (key or "").replace("-", " ").title()
def item_area(it):
    """Key of the first home region an item names (for the town kicker); None when not local."""
    regs = it.get("regions") or []
    for r in regs:
        if r in _HOME_KEYS: return r
    return regs[0] if regs else None
def pr_region(p):
    if p.get("region"): return p["region"]
    fn = getattr(TX, "area_to_region", None)
    if fn and p.get("area"):
        try: return fn(p["area"])
        except Exception: pass
    return T.slugify(p.get("area") or "") or None
def area_href(key): return f"/local/{key}/" if key else "/local/"

# ---------- head bridge ----------
_HEAD_KW = set(inspect.signature(H.head).parameters)
JUSTIN = ""
def set_justin(items, max_age=3600, n=3):
    """Static 'Just in' strip: only when the newest item is < 60 min old; max 3 items; no animation."""
    global JUSTIN
    now = int(NOW.timestamp())
    fresh = [i for i in (items or [])[:40] if i.get("ts") and now - int(i["ts"]) < max_age][:n]
    if not fresh: JUSTIN = ""; return JUSTIN
    links = "".join(f'<a href="/story/{i["slug"]}/">{esc(clean(i["title"], 90))} {time_tag(i["ts"])}</a>' for i in fresh)
    JUSTIN = f'<section class="justin" aria-label="Just in"><div class="wrap"><span class="lbl">Just in</span>{links}</div></section>'
    return JUSTIN

def _nav_items():
    nav = getattr(CFG, "NAV", None)
    out = []
    try:
        for n in nav or []:
            if isinstance(n, dict):
                kids = [(c[0], c[1], c[2]) if isinstance(c, (list, tuple)) else (c.get("key"), c.get("label") or c.get("name"), c.get("href") or c.get("url")) for c in (n.get("children") or n.get("items") or [])]
                out.append({"key": n.get("key"), "label": n.get("label") or n.get("name"), "href": n.get("href") or n.get("url") or "/", "children": [k for k in kids if k[1] and k[2]]})
            else:
                out.append({"key": n[0], "label": n[1], "href": n[2], "children": []})
    except Exception as e:
        print(f"WARN nav: {e}", file=sys.stderr); out = []
    if not out:
        out = [{"key": "local", "label": "Local", "href": "/local/", "children": [(k, v, h) for k, v, h in LOCAL_AREAS] + [("local-all", "All local news", "/local/"), ("submit", "Submit news", "/submit/")]}]
        for k, v in CATS:
            if k == "local" or k in ("markets", "science"): continue
            kids = {"business": [("business", "Business", "/category/business/"), ("markets", "Markets", "/category/markets/")], "tech": [("tech", "Tech", "/category/tech/"), ("science", "Science", "/category/science/")]}.get(k, [])
            out.append({"key": k, "label": v, "href": f"/category/{k}/", "children": kids})
        out.append({"key": "more", "label": "More", "href": "/about/", "children": [("topics", "Topics", "/topic/"), ("about", "About", "/about/"), ("standards", "Editorial policy", "/editorial-policy/"), ("feeds", "Feeds", "/rss.xml"), ("ai", "For AI", "/llm-info/")]})
    return out
NAV_ITEMS = _nav_items()
_MORE_STD = [("about", "About", "/about/"), ("standards", "Editorial policy", "/editorial-policy/"), ("corrections", "Corrections", "/corrections/"),
             ("contact", "Contact", "/contact/"), ("feeds", "Feeds", "/rss.xml"), ("ai", "For AI", "/llm-info/")]

def _is_cur(n, path):
    k = n["key"]
    if k == "local": return path.startswith(("/local/", "/press-releases/", "/category/local/"))
    if k == "more": return path in {h for _, _, h in _MORE_STD} or path.startswith("/topic/")
    hrefs = [n["href"]] + [h for _, _, h in n["children"]]
    return any(path.startswith(h) for h in hrefs if h not in ("/", "/submit/"))

def _nav_html(path):
    lis = []
    for n in NAV_ITEMS:
        cur = _is_cur(n, path); k = n["key"]
        if k == "local":
            areas = [(kk, l, h) for kk, l, h in n["children"] if h.startswith("/local/") and h != "/local/"]
            extra = [(kk, l, h) for kk, l, h in n["children"] if (kk, l, h) not in areas]
            if not any(h == "/local/" for _, _, h in extra): extra.insert(0, ("local-all", "All local news", "/local/"))
            if not any(h == "/submit/" for _, _, h in extra): extra.append(("submit", "Submit news", "/submit/"))
            panel = '<h3>Coverage areas</h3>' + "".join(f'<a href="{h}"{" aria-current=\"page\"" if path == h else ""}>{esc(l)}</a>' for _, l, h in areas) + '<div class="sep"></div>' + "".join(f'<a class="strong" href="{h}">{esc(l)}</a>' for _, l, h in extra)
            lis.append(f'<li><details class="dd{" cur" if cur else ""}"><summary aria-haspopup="true">Local</summary><div class="panel wide cols3">{panel}</div></details></li>')
        elif k == "more":
            kids = list(n["children"]); topics = ""
            if any(kk == "topics" for kk, _, _ in kids) and TOPIC_LINKS:
                topics = "<h3>Topics</h3>" + "".join(f'<a href="{h}">{esc(l)}</a>' for _, l, h in TOPIC_LINKS) + '<div class="sep"></div>'
                kids = [c for c in kids if c[0] != "topics"]
            seen = {h for _, _, h in kids}
            kids += [c for c in _MORE_STD if c[2] not in seen]
            order = {"about": 0, "standards": 1, "corrections": 2, "contact": 3, "feeds": 4, "ai": 5}
            kids.sort(key=lambda c: order.get(c[0], 9))
            panel = topics + "".join(f'<a href="{h}">{esc(l)}</a>' for _, l, h in kids)
            lis.append(f'<li><details class="dd{" cur" if cur else ""}"><summary aria-haspopup="true">More</summary><div class="panel{" wide" if topics else ""}">{panel}</div></details></li>')
        else:
            a = f'<a href="{n["href"]}"{" aria-current=\"page\"" if cur else ""}>{esc(n["label"])}</a>'
            sub = f'<ul class="sub">{"".join(f"<li><a href={chr(34)}{h}{chr(34)}>{esc(l)}</a></li>" for _, l, h in n["children"])}</ul>' if n["children"] else ""
            lis.append(f"<li>{a}{sub}</li>")
    cta = f'<a class="btn ghost sm" href="{NAV_CTA[1]}">{esc(NAV_CTA[0])}</a>'
    return f'<nav class="nav" id="site-nav" aria-label="Primary"><ul>{"".join(lis)}</ul>{cta}</nav>'

_REV = dims("/img/logo-reverse.webp") or (1200, 656)
def _footer():
    areas = "".join(f'<li><a href="{h}">{esc(l)}</a></li>' for _, l, h in LOCAL_AREAS[:12])
    secs = "".join(f'<li><a href="/category/{k}/">{esc(v)}</a></li>' for k, v in CATS if k != "local")
    about = "".join(f'<li><a href="{h}">{esc(l)}</a></li>' for l, h in (("About", "/about/"), ("Editorial policy", "/editorial-policy/"), ("Corrections", "/corrections/"), ("Contact", "/contact/"), ("Privacy", "/privacy/"), ("Terms", "/terms/"), ("Submit news", "/submit/")))
    feeds = "".join(f'<li><a href="{h}">{esc(l)}</a></li>' for l, h in (("RSS", "/rss.xml"), ("Atom", "/feed.xml"), ("Local news RSS", "/press-releases/feed.xml"), ("Sitemap", "/sitemap.xml")))
    return f"""<footer class="foot" id="foot"><div class="wrap">
<div class="fgrid"><div class="fbrand"><a href="/" aria-label="Ground Level News home"><img src="/img/logo-reverse.webp" alt="" width="{_REV[0]}" height="{_REV[1]}" loading="lazy" decoding="async"></a>
<p>{TAG} Local news for the Colorado River region of Arizona and Nevada, plus U.S. and world headlines from publishers' public feeds. Every story links to its original publisher.</p>
<a class="btn ghost light" href="/submit/">Submit news</a></div>
<nav aria-label="Coverage areas"><h2>Coverage</h2><ul class="cols2">{areas}<li><a href="/local/">All local news</a></li></ul></nav>
<nav aria-label="Footer sections"><h2>Sections</h2><ul class="cols2">{secs}</ul></nav>
<nav aria-label="About and feeds" class="two"><h2>About</h2><ul>{about}</ul><h2>Feeds</h2><ul>{feeds}</ul></nav></div>
<div class="fbar"><p>© {NOW.year} {NAME} · Updated <time datetime="{NOW.strftime('%Y-%m-%dT%H:%M:%SZ')}">{esc(fmt_date(int(NOW.timestamp()), "long"))}</time></p>
<p class="dev">For developers &amp; AI: <a href="/llm-info/">llm-info</a> · <a href="/llms.txt">llms.txt</a> · <a href="/agents.txt">agents.txt</a> · <a class="ai" href="/llm-info/">Hey AI, learn about us</a></p>
<a class="totop" href="#top">Back to top <span aria-hidden="true">↑</span></a></div></div></footer>"""
FOOTER = None

def page(title, body, desc=TAG, path="/", og_type="website", extra_head="", og_img=None, md=None, robots=None, ld=None, preload_img=None,
         kicker=None, article=None, feeds=None, canonical=True, body_class="", ticker=None, strip=None):
    """Full HTML document. Unknown head params are dropped when head.head() lacks them (modules land independently)."""
    global FOOTER
    if FOOTER is None: FOOTER = _footer()
    kw = {"robots": robots, "ld": ld, "preload_img": preload_img, "article": article, "feeds": feeds, "canonical": canonical}
    kw = {k: v for k, v in kw.items() if k in _HEAD_KW and (v is not None or k == "robots")}
    if "canonical" not in _HEAD_KW and canonical is False and not path.endswith("404.html"):
        pass   # head decides; note in the report that canonical=False needs head support
    if "canonical" in _HEAD_KW and isinstance(canonical, str):
        # canonical override URL: head takes True/False only -> emit our own tag when head accepts canonical=False
        kw["canonical"] = False
        extra_head = (extra_head or "") + f'<link rel="canonical" href="{esc(canonical if canonical.startswith("http") else SITE + canonical)}"><meta property="og:url" content="{esc(canonical if canonical.startswith("http") else SITE + canonical)}">'
    hd = H.head(title, desc, path, og_type, extra_head, og_img, md, **kw)
    cls = f' class="{esc(body_class)}"' if body_class else ""
    strip = JUSTIN if strip is None else strip
    return f"""<!doctype html><html lang="en"><head>{hd}</head><body{cls}>
<a class="skip" href="#main">Skip to content</a>
<header class="top" id="top"><div class="wrap hdr"><a class="logo" href="/" aria-label="Ground Level News home"><img src="/img/logo-header.webp" srcset="/img/logo-header.webp 1x, /img/logo-header@2x.webp 2x" alt="Ground Level News" width="191" height="104"></a>
{_nav_html(path)}<button class="menu" type="button" aria-controls="site-nav" aria-expanded="false" aria-label="Open menu"><span></span><span></span><span></span></button></div></header>
{strip}<main class="wrap" id="main" tabindex="-1">{body}</main>
{FOOTER}
<script src="/app.js" defer></script>
</body></html>"""

# ---------- share cards ----------
OG_CACHE = ROOT/".ogcache"
OG_STORIES = int(os.environ.get("OG_STORIES", str(getattr(CFG, "OG_STORIES", 60))))
def og_for(slug, title, cat, im=None, source=None, date=None, kicker=None):
    """Branded 1200x630 share card (over the story photo when there is one), cached by content hash."""
    if not brand: return None
    photo = None
    if im and not im.get("brand") and im["src"].startswith("/"):
        f = ROOT/"static"/im["src"].lstrip("/")
        photo = f if f.exists() else None
    try:
        kw = {}
        params = inspect.signature(brand.og_cached).parameters
        if "source" in params: kw["source"] = source
        if "date" in params: kw["date"] = date
        if "kicker" in params: kw["kicker"] = kicker
        brand.og_cached(title, cat, OUT/f"og/{slug}.jpg", OG_CACHE, photo, (im or {}).get("credit") if photo else None, **kw)
        return f"{SITE}/og/{slug}.jpg"
    except Exception as e:
        print(f"WARN og {slug}: {e}", file=sys.stderr); return None

# ---------- cards ----------
_CARD = {}
_SIZES = {"lg": "(max-width:1024px) 100vw, 860px", "md": "(max-width:640px) 100vw, (max-width:1024px) 50vw, 420px", "row": "96px"}
def _is_repeat(title, summary):
    if not summary: return True
    t = re.sub(r"\W+", " ", title.lower()).strip(); s = re.sub(r"\W+", " ", summary.lower()).strip()
    return not s or s.startswith(t[:40]) or t.startswith(s[:40]) or len(s) < 25
def tile(label, kicker="", cls="tile"):
    """Compact branded publisher tile (navy) used instead of an unrelated file photo."""
    return f'<div class="{cls}" aria-hidden="true"><span>{esc(kicker or NAME)}</span><b>{esc(clean(label, 60))}</b></div>'
def _kick_for(it, kicker=None):
    if kicker is not None: return kicker, ("local" if it.get("local") else it.get("cat") or "us")
    if it.get("local"):
        a = item_area(it)
        return (region_name(a) if a else "Local"), "local"
    cat = it.get("cat") or "us"
    return CAT_SHORT.get(cat, CAT_NAME.get(cat, cat)), cat
def _is_original(it): return "company" in it or (it.get("kind") in ("press-release", "brief", "report") and not it.get("link"))
def card(it, size="md", kicker=None, show_dek=True, lazy=True, est=False):
    """One markup, four sizes: lg (3:2 photo, 30px title), md (16:9, 20px), row (1:1 96px thumb, 16px), text (no image).
    lg uses a photo only when keyword-matched, else a branded publisher tile; valid HTML (article > div/h3/p), stretched link."""
    if _is_original(it): return pr_card(it, size)
    size = {"card": "md", "mini": "row"}.get(size, size)
    im = None
    if size == "lg": im = story_img(it, require_match=True)
    elif size in ("md", "row"): im = story_img(it)
    key = (it.get("id"), size, kicker, show_dek, (im or {}).get("src"))
    if key in _CARD: return _CARD[key]
    kick, cat = _kick_for(it, kicker)
    href = f"/story/{it['slug']}/"
    pub = (it.get("publisher") or {}).get("name") or it.get("source") or "Wire report"
    media = ""
    if size == "lg": media = thumb(im, _SIZES["lg"], lazy) if im else tile(pub, kick)
    elif size in ("md", "row"): media = thumb(im, _SIZES[size], lazy) if im else ""
    title = esc(it["title"])
    dek = f'<p class="dek">{esc(clean(it["summary"], 180))}</p>' if show_dek and size in ("lg", "md") and not _is_repeat(it["title"], it.get("summary") or "") else ""
    kchip = f' <span class="chip">{esc(KIND_LABEL[it["kind"]])}</span>' if it.get("kind") in ("event", "meeting") else ""
    meta = f'<span class="meta"><bdi>{esc(pub)}</bdi> · {time_tag(it.get("ts"), "rel", est or not it.get("ts"))}</span>'
    html = (f'<article class="card card--{size}{" noimg" if size == "row" and not media else ""} t-{cat}">{media}<div class="cb"><span class="kick">{esc(kick)}{kchip}</span>'
            f'<h3><a href="{href}">{title}</a></h3>{dek}{meta}</div></article>')
    _CARD[key] = html
    return html
def pr_card(p, size="md", kicker=None, show_dek=True, lazy=True):
    """Card for an original: town kicker + kind chip, company · date meta."""
    size = {"card": "md", "mini": "row", "card pr-card": "md"}.get(size, size)
    im = pr_img(p) if size != "text" else None
    key = ("pr", p["slug"], size, kicker, show_dek)
    if key in _CARD: return _CARD[key]
    reg = pr_region(p); kick = kicker if kicker is not None else (region_name(reg) if reg else (p.get("area") or "Local"))
    kind = p.get("kind") or "press-release"
    href = f"/press-releases/{p['slug']}/"
    media = thumb(im, _SIZES.get(size, _SIZES["md"]), lazy) if im else ""
    ts = p.get("ts") or T.to_ts(p.get("published_iso") or p.get("published") or p.get("date"))
    dek = f'<p class="dek">{esc(clean(p.get("summary"), 180))}</p>' if show_dek and size in ("lg", "md") and not _is_repeat(p["title"], p.get("summary") or "") else ""
    ex = ' <span class="chip red">Example</span>' if p.get("example") else ""
    meta = f'<span class="meta"><bdi>{esc(p.get("company") or NAME)}</bdi> · {time_tag(ts, "rel", True) if ts else ""}</span>'
    html = (f'<article class="card card--{size} t-local">{media}<div class="cb"><span class="kick">{esc(kick)} <span class="chip">{esc(KIND_LABEL.get(kind, "Press release"))}</span>{ex}</span>'
            f'<h3><a href="{href}">{esc(p["title"])}</a></h3>{dek}{meta}</div></article>')
    _CARD[key] = html
    return html
def rows(items, size="row", limit=None, kicker=None, cls="list"):
    items = list(items)[:limit] if limit else list(items)
    return f'<div class="{cls}">{"".join(card(i, size, kicker=kicker) for i in items)}</div>'

# ---------- small components ----------
_ids = itertools.count(1)
def section_header(title, href=None, cat=None, more_label=None, tag="h2", id=None, soft=False):
    t = f' t-{cat}' if cat else ""
    more = f'<a class="link" href="{href}">{esc(more_label or f"More {title}")}</a>' if href else ""
    idattr = f' id="{esc(id)}"' if id else ""
    return f'<div class="sh{t}{" soft" if soft else ""}"><{tag}{idattr}><span class="bar"></span>{esc(title)}</{tag}>{more}</div>'
def chips(pairs, current=None, scroll=False, label=None):
    lis = "".join(f'<li><a href="{h}"{" aria-current=\"page\"" if h == current else ""}>{esc(l)}</a></li>' for l, h in pairs)
    al = f' aria-label="{esc(label)}"' if label else ""
    return f'<ul class="chips{" scroll" if scroll else ""}"{al}>{lis}</ul>'
def grid(cards, show, cls="grid", step=None, label="Show more", noun=None):
    """Shows `show` cards; the rest stay in the HTML (crawlers, no-JS) behind a 'Show N more' button."""
    step = step or show
    cards = list(cards)
    if len(cards) <= show: return f'<div class="{cls}">{"".join(cards)}</div>'
    gid = f"g{next(_ids)}"
    html = "".join(c if n < show else c.replace('class="', 'class="more-item ', 1) for n, c in enumerate(cards))
    return (f'<div class="{cls}" id="{gid}" data-step="{step}" data-noun="{esc(noun or "more")}">{html}</div>'
            f'<div class="more-wrap"><button class="loadmore" type="button" aria-controls="{gid}">{esc(label)}</button></div>')
def _ev_ts(v): return T.to_ts(v)
def events_list(events, limit=6):
    """[{title, start, end, all_day, venue, area, url, ics}] -> <ol class="events">. Past events are dropped, sorted by start."""
    now = int(NOW.timestamp()); out = []
    for e in events or []:
        st = _ev_ts(e.get("start")); en = _ev_ts(e.get("end")) or st
        if not st or (en and en < now - 6 * 3600): continue
        out.append((st, en, e))
    out.sort(key=lambda x: x[0])
    if not out: return ""
    lis = []
    for st, en, e in out[:limit]:
        d0 = T._dt(st).astimezone(T.TZ) if hasattr(T, "TZ") else T._dt(st)
        d1 = T._dt(en).astimezone(T.TZ) if (en and hasattr(T, "TZ")) else d0
        when = d0.strftime("%a, %b %-d") if d0.date() == d1.date() else f"{d0.strftime('%b %-d')}–{d1.strftime('%b %-d')}"
        if not e.get("all_day") and d0.strftime("%H%M") != "0000": when += d0.strftime(", %-I:%M %p").replace(":00", "")
        box = f'<span class="d" aria-hidden="true"><small>{d0.strftime("%b")}</small>{d0.day}</span>'
        where = " · ".join(x for x in (e.get("venue"), region_name(e.get("area")) if e.get("area") and (e.get("area") in REGIONS or e.get("area") in _AREA_NAME) else e.get("area")) if x)
        ics = f' <a class="ics" href="{esc(e["ics"])}">Add to calendar</a>' if e.get("ics") or e.get("ics_path") else ""
        if not e.get("ics") and e.get("ics_path"): ics = f' <a class="ics" href="{esc(e["ics_path"])}">Add to calendar</a>'
        lis.append(f'<li>{box}<div><h3><a href="{esc(e.get("url") or "/local/")}">{esc(clean(e.get("title"), 90))}</a></h3><span class="meta">{esc(when)}{" · " + esc(where) if where else ""}</span>{ics}</div></li>')
    return f'<ol class="events">{"".join(lis)}</ol>'
def cond_strip(html, label="River and weather"):
    """Wraps the conditions fragment (classes prefixed cond) in a labelled region; empty when there is nothing."""
    if not html: return ""
    return f'<div class="cond" role="region" aria-label="{esc(label)}"><span class="cond-title">{esc(label)}</span>{html}</div>'
def crumbs_html(pairs):
    """Visible breadcrumb trail (pairs of (name, href)); the last item is the current page."""
    lis = "".join(f'<li><a href="{h}">{esc(n)}</a></li>' if k < len(pairs) - 1 else f'<li aria-current="page">{esc(clean(n, 60))}</li>' for k, (n, h) in enumerate(pairs))
    return f'<nav aria-label="Breadcrumb"><ol class="crumbs">{lis}</ol></nav>'

def write(path, content):
    f = OUT / path.lstrip("/")
    if path.endswith("/"): f = f / "index.html"
    if BASE: content = re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{BASE}/', content)
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(content, encoding="utf-8")
