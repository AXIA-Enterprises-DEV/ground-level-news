#!/usr/bin/env python3
"""Ground Level News static site builder.
Pulls news-tracker data from its GitHub Pages URL, renders HTML into _site/."""
import os, re, json, html, shutil, hashlib, datetime as dt, pathlib, sys
import requests, yaml, markdown
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
def pr_img(p):
    """Front-matter image for a press release, falling back to the category image."""
    if p.get("image"):
        return {"src": p["image"], "alt": p.get("image_alt") or p.get("title"), "credit": p.get("image_credit"),
                "license": p.get("image_license"), "license_url": p.get("image_license_url"),
                "source": p.get("image_source"), "label": p.get("image_label") or "File photo"}
    return cat_img(p.get("category") or "pr")
def img_tag(im, cls="", lazy=True, sizes="100vw"):
    if not im: return ""
    d = dims(im["src"]); wh = f' width="{d[0]}" height="{d[1]}"' if d else ""
    return f'<img class="{cls}" src="{esc(im["src"])}" alt="{esc(im.get("alt"))}"{wh}{" loading=\"lazy\"" if lazy else " fetchpriority=\"high\""} decoding="async" sizes="{sizes}">'
def credit(im):
    if not im: return ""
    lic = esc(im.get("license") or "")
    if im.get("license_url") and lic: lic = f'<a href="{esc(im["license_url"])}" rel="license noopener" target="_blank">{lic}</a>'
    src = f' · <a href="{esc(im["source"])}" rel="noopener" target="_blank">Source</a>' if im.get("source") else ""
    return f'<span class="lbl">{esc(im.get("label") or "File photo")}</span> {esc(im.get("credit") or "")}{" · " + lic if lic else ""}{src}'
def figure(im, lazy=True, note=""):
    if not im: return ""
    return f'<figure class="fig">{img_tag(im, "", lazy, "(max-width:900px) 100vw, 860px")}<figcaption>{note}{credit(im)}</figcaption></figure>'

def ago(ts):
    if not ts: return ""
    s = int(NOW.timestamp()) - ts
    if s < 3600: return f"{max(1, s//60)}m ago"
    if s < 86400: return f"{s//3600}h ago"
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%b %d")

def iso(ts): return dt.datetime.fromtimestamp(ts or NOW.timestamp(), dt.timezone.utc).isoformat()

def page(title, body, desc=TAG, path="/", ticker="", og_type="website", extra_head="", og_img=None):
    full = f"{esc(title)} | {NAME}" if title != NAME else f"{NAME} | {TAG}"
    url = SITE + path
    canon = SITE + path
    nav = "".join(f'<a href="/category/{k}/">{v}</a>' for k, v in CATS) + '<a href="/press-releases/" class="pr">Press Releases</a>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{full}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}"><meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}"><meta property="og:type" content="{og_type}">
<meta property="og:image" content="{og_img or SITE + "/og.png"}"><meta property="og:image:alt" content="{NAME}"><meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0b1020">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/png" sizes="512x512" href="/icon-512.png"><link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"><meta name="twitter:image" content="{og_img or SITE + "/og.png"}">
<link rel="alternate" type="application/rss+xml" title="{NAME}" href="/rss.xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">{extra_head}</head><body>
<div class="ticker"><span class="live">LIVE</span><div class="tk-wrap"><div class="tk">{ticker}{ticker}</div></div></div>
<header class="top"><div class="wrap hdr"><a class="logo" href="/" aria-label="Ground Level News home"><img src="/img/logo.webp" alt="Ground Level News" width="297" height="180" fetchpriority="high"></a>
<button class="menu" onclick="document.body.classList.toggle('open')" aria-label="Menu">☰</button></div>
<nav class="nav"><div class="wrap">{nav}</div></nav></header>
<main class="wrap">{body}</main>
<footer class="foot"><div class="wrap"><a class="logo sm" href="/"><img src="/img/logo.webp" alt="Ground Level News" width="297" height="180" loading="lazy"></a>
<p>{TAG} Headlines are aggregated from public RSS feeds. Each story summarizes and links to the original publisher, who owns the content.</p>
<p><a href="/press-releases/">Press Releases</a> · <a href="/rss.xml">RSS</a> · <a href="/sitemap.xml">Sitemap</a> · <a href="/about/">About</a></p>
<p class="muted">© {NOW.year} {NAME}. Updated {NOW.strftime('%b %d, %Y %H:%M UTC')}.</p></div></footer>
<script>document.querySelectorAll('[data-ts]').forEach(e=>{{const s=Math.floor(Date.now()/1000)-+e.dataset.ts;e.textContent=s<3600?Math.max(1,s/60|0)+'m ago':s<86400?(s/3600|0)+'h ago':new Date(e.dataset.ts*1000).toLocaleDateString(undefined,{{month:'short',day:'numeric'}})}})</script>
</body></html>"""

def card(it, cls="card"):
    cat = "local" if it.get("local") else it["cat"]
    th = f'<span class="thumb">{img_tag(cat_img(cat), sizes="(max-width:620px) 100vw, 400px")}</span>' if cls != "mini" else ""
    return f"""<a class="{cls}" href="/story/{it['slug']}/">{th}<span class="tag t-{cat}">{esc(CAT_NAME.get(cat))}</span>
<h3>{esc(it['title'])}</h3>{f'<p>{esc(clean(it["summary"],160))}</p>' if cls!='mini' and it['summary'] else ''}
<span class="meta">{esc(it.get('source'))} · <time data-ts="{it['ts']}">{ago(it['ts'])}</time></span></a>"""

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
    secs = ""
    for k, v in CATS:
        lst = [i for i in by[k] if i is not lead][:6]
        if not lst: continue
        secs += f'<section class="sec"><div class="sh"><h2><span class="bar t-{k}"></span>{v}</h2><a href="/category/{k}/">More {v} →</a></div><div class="grid">{"".join(card(i) for i in lst)}</div></section>'
    prbox = "".join(f'<a class="mini prm" href="/press-releases/{p["slug"]}/">{img_tag(pr_img(p), "pthumb", sizes="80px")}<span class="tag t-pr">{esc(p.get("area") or "Release")}</span><h3>{esc(p["title"])}</h3><span class="meta">{esc(p.get("company"))} · {esc(p["date"])}</span></a>' for p in prs[:5])
    body = ""
    if lead:
        lim = cat_img("local" if lead.get("local") else lead["cat"])
        body += f"""<section class="hero"><a class="lead" href="/story/{lead['slug']}/">{img_tag(lim, "lead-bg", False, "(max-width:980px) 100vw, 800px")}<span class="tag t-{lead['cat']}">Top Story</span>
<h1>{esc(lead['title'])}</h1><p>{esc(lead['summary'])}</p><span class="meta">{esc(lead.get('source'))} · <time data-ts="{lead['ts']}">{ago(lead['ts'])}</time></span>
<span class="lead-cr">{esc((lim or {}).get("label",""))}: {esc((lim or {}).get("credit",""))}</span></a>
<aside class="latest"><h2><span class="pulse"></span>Latest</h2>{"".join(card(i,'mini') for i in rest[:8])}</aside></section>"""
    body += f'<section class="sec"><div class="sh"><h2><span class="bar t-local"></span>Top Headlines</h2></div><div class="grid g4">{"".join(card(i) for i in rest[8:16])}</div></section>'
    body += f'<div class="two"><div>{secs}</div><aside class="side"><div class="box"><h2>Press Releases</h2>{prbox}<a class="btn" href="/press-releases/">All releases →</a></div></aside></div>'
    write("/", page(NAME, body, ticker=ticker))

    # categories
    for k, v in CATS:
        lst = by[k][:120]
        write(f"/category/{k}/", page(f"{v} News", f'<h1 class="ph"><span class="bar t-{k}"></span>{v}</h1>{figure(cat_img(k), False).replace("class=\"fig\"", "class=\"fig banner\"")}<div class="grid g3">{"".join(card(i) for i in lst) or "<p>No stories right now.</p>"}</div>', f"Latest {v} headlines from {NAME}.", f"/category/{k}/", ticker))

    # stories
    for i in items:
        cat = "local" if i.get("local") else i["cat"]
        rel = [r for r in by[i["cat"]] if r is not i][:4]
        ld = {"@context":"https://schema.org","@type":"NewsArticle","headline":i["title"][:110],"datePublished":iso(i["ts"]),
              "isBasedOn":i["link"],"publisher":{"@type":"Organization","name":NAME},"description":i["summary"][:300]}
        b = f"""<article class="story"><a class="crumb" href="/category/{cat}/">{esc(CAT_NAME[cat])}</a>
<h1>{esc(i['title'])}</h1><div class="byline">Source: <b>{esc(i.get('source'))}</b> · <time datetime="{iso(i['ts'])}">{dt.datetime.fromtimestamp(i['ts'] or NOW.timestamp(), dt.timezone.utc).strftime('%b %d, %Y %H:%M UTC')}</time></div>
{figure(cat_img(cat), False, "Category image, not from this story. ")}<div class="summary"><h2>The Quick Take</h2><p>{esc(i['summary']) or 'Read the full report from the original publisher.'}</p></div>
<a class="cta" href="{esc(i['link'])}" rel="noopener nofollow" target="_blank">Read the full story at {esc(i.get('source') or 'the source')} →</a>
<p class="attr">Ground Level News aggregates headlines from public feeds. This page shows a short summary only; the full article and all rights belong to {esc(i.get('source') or 'the original publisher')}.</p>
{f'<h2 class="rel">Related</h2><div class="grid">{"".join(card(r) for r in rel)}</div>' if rel else ''}</article>"""
        write(f"/story/{i['slug']}/", page(i["title"], b, i["summary"] or i["title"], f"/story/{i['slug']}/", ticker, "article",
              f'<script type="application/ld+json">{json.dumps(ld)}</script>'))

    # press releases
    lst = "".join(f'<a class="card pr-card" href="/press-releases/{p["slug"]}/"><span class="thumb">{img_tag(pr_img(p), sizes="(max-width:620px) 100vw, 400px")}</span><span class="tag t-pr">{esc(p.get("area") or "Release")}{" · EXAMPLE" if p.get("example") else ""}</span><h3>{esc(p["title"])}</h3><p>{esc(p.get("summary"))}</p><span class="meta">{esc(p.get("company"))} · {esc(p["date"])}</span></a>' for p in prs)
    write("/press-releases/", page("Press Releases", f'<h1 class="ph"><span class="bar t-pr"></span>Press Releases</h1><p class="lede">Local announcements from across Mohave Valley, Bullhead City, Laughlin, Clark County, Mesquite, Boulder City and beyond. <a href="https://github.com/AXIA-Enterprises-DEV/ground-level-news#publishing-press-releases">Submit a release →</a></p><div class="grid g3">{lst}</div>', "Press releases and local announcements on Ground Level News.", "/press-releases/", ticker))
    for p in prs:
        src = f'<p class="attr">Source: <a href="{esc(p["source_url"])}" rel="noopener" target="_blank">{esc(p.get("source_name") or p["source_url"])}</a></p>' if p.get("source_url") else ""
        b = f"""<article class="story"><a class="crumb" href="/press-releases/">Press Release{' · EXAMPLE' if p.get('example') else ''}</a><h1>{esc(p['title'])}</h1>
<div class="byline"><b>{esc(p.get('company'))}</b> · {esc(p['date'])}{' · ' + esc(p.get('area')) if p.get('area') else ''}</div>
{figure(pr_img(p), False)}<div class="summary"><p>{esc(p.get('summary'))}</p></div><div class="prose">{p['body']}</div>{src}
<p class="attr">Media contact: {esc(p.get('contact'))}</p></article>"""
        write(f"/press-releases/{p['slug']}/", page(p["title"], b, p.get("summary") or p["title"], f"/press-releases/{p['slug']}/", ticker, "article", og_img=(SITE + pr_img(p)["src"]) if pr_img(p) and pr_img(p)["src"].startswith("/") else None))

    write("/about/", page("About", f'<article class="story"><h1>About {NAME}</h1><div class="prose"><p>{NAME} is a fast, free news front page built from hundreds of public RSS feeds and refreshed every 15 minutes. Every story links to its original publisher. Raw SEC filing noise is filtered out.</p><p>Local press releases are published from Markdown files in our <a href="https://github.com/AXIA-Enterprises-DEV/ground-level-news">GitHub repository</a>.</p></div></article>', path="/about/", ticker=ticker))
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

    urls = ["/", "/press-releases/", "/about/"] + [f"/category/{k}/" for k, _ in CATS] + [f"/press-releases/{p['slug']}/" for p in prs] + [f"/story/{i['slug']}/" for i in items]
    (OUT/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{SITE}{u}</loc></url>" for u in urls) + "</urlset>", encoding="utf-8")
    (OUT/"robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    print("built", len(urls), "pages")

if __name__ == "__main__": main()
