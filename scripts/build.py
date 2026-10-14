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
INDEXNOW_KEY = "5a8308b39ca87422bfd5d4eb53c1c5bb"
REPO = "https://github.com/AXIA-Enterprises-DEV/ground-level-news"
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

def page(title, body, desc=TAG, path="/", ticker="", og_type="website", extra_head="", og_img=None, md=None):
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
<link rel="alternate" type="application/rss+xml" title="{NAME} RSS" href="/rss.xml"><link rel="alternate" type="application/atom+xml" title="{NAME} Atom" href="/feed.xml">{f'<link rel="alternate" type="text/markdown" href="{md}">' if md else ''}<link rel="help" type="text/plain" href="/llms.txt" title="llms.txt">
<meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(desc)}"><meta name="robots" content="index,follow,max-image-preview:large">
<script type="application/ld+json">{SITE_LD}</script>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800;900&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">{extra_head}</head><body>
<div class="ticker"><span class="live">LIVE</span><div class="tk-wrap"><div class="tk">{ticker}{ticker}</div></div></div>
<header class="top"><div class="wrap hdr"><a class="logo" href="/" aria-label="Ground Level News home"><img src="/img/logo-knockout.webp" alt="Ground Level News" width="206" height="112" fetchpriority="high"></a>
<nav class="nav" aria-label="Sections">{nav}</nav></div></header>
<main class="wrap">{body}</main>
<footer class="foot"><div class="wrap"><a class="logo sm" href="/"><img src="/img/logo.webp" alt="Ground Level News" width="297" height="180" loading="lazy"></a>
<p>{TAG} Headlines are aggregated from public RSS feeds. Each story summarizes and links to the original publisher, who owns the content.</p>
<p><a href="/press-releases/">Press Releases</a> · <a href="/rss.xml">RSS</a> · <a href="/feed.xml">Atom</a> · <a href="/sitemap.xml">Sitemap</a> · <a href="/llms.txt">llms.txt</a> · <a href="/about/">About</a></p>
<p class="muted">© {NOW.year} {NAME}. Updated {NOW.strftime('%b %d, %Y %H:%M UTC')}.</p></div></footer>
<script>document.querySelectorAll('[data-ts]').forEach(e=>{{const s=Math.floor(Date.now()/1000)-+e.dataset.ts;e.textContent=s<3600?Math.max(1,s/60|0)+'m ago':s<86400?(s/3600|0)+'h ago':new Date(e.dataset.ts*1000).toLocaleDateString(undefined,{{month:'short',day:'numeric'}})}})</script>
</body></html>"""

ORG = {"@type":"NewsMediaOrganization","@id":SITE+"/#org","name":NAME,"url":SITE+"/","logo":{"@type":"ImageObject","url":SITE+"/img/logo.png","width":297,"height":180},
       "sameAs":[REPO],"publishingPrinciples":SITE+"/about/"}
SITE_LD = json.dumps({"@context":"https://schema.org","@graph":[ORG,{"@type":"WebSite","@id":SITE+"/#website","url":SITE+"/","name":NAME,"description":TAG,"publisher":{"@id":SITE+"/#org"},"inLanguage":"en-US"}]}).replace("</","<\\/")
def ldj(o): return f'<script type="application/ld+json">{json.dumps(o).replace("</","<\\/")}</script>'
def crumbs(*pairs): return {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":n+1,"name":a,"item":SITE+b} for n,(a,b) in enumerate(pairs)]}
def absimg(im): return (SITE + im["src"]) if im and im["src"].startswith("/") else (im or {}).get("src")

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
        body += f"""<section class="hero"><div class="leadwrap"><a class="lead" href="/story/{lead['slug']}/">{img_tag(lim, "lead-bg", False, "(max-width:980px) 100vw, 800px")}<span class="tag t-{lead['cat']}">Top Story</span>
<h1>{esc(lead['title'])}</h1><p>{esc(lead['summary'])}</p><span class="meta">{esc(lead.get('source'))} · <time data-ts="{lead['ts']}">{ago(lead['ts'])}</time></span>
</a><p class="lead-cap">{credit(lim)}</p></div>
<aside class="latest"><h2><span class="pulse"></span>Latest</h2>{"".join(card(i,'mini') for i in rest[:6])}<details class="more"><summary>View more</summary>{"".join(card(i,'mini') for i in rest[6:16])}</details></aside></section>"""
    body += f'<section class="sec"><div class="sh"><h2><span class="bar t-local"></span>Top Headlines</h2></div><div class="grid g4">{"".join(card(i) for i in rest[16:24])}</div></section>'
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
        ld = {"@context":"https://schema.org","@type":"NewsArticle","headline":i["title"][:110],"datePublished":iso(i["ts"]),"dateModified":iso(i["ts"]),
              "mainEntityOfPage":f"{SITE}/story/{i['slug']}/","url":f"{SITE}/story/{i['slug']}/","image":[absimg(cat_img(cat))],"articleSection":CAT_NAME[cat],
              "author":{"@type":"Organization","name":i.get("source") or NAME},"publisher":{"@id":SITE+"/#org","@type":"NewsMediaOrganization","name":NAME,"logo":ORG["logo"]},
              "isBasedOn":i["link"],"description":i["summary"][:300]}
        (OUT/"story").mkdir(parents=True, exist_ok=True)
        (OUT/f"story/{i['slug']}.md").write_text(f"# {i['title']}\n\n- Source: {i.get('source')}\n- Published: {iso(i['ts'])}\n- Category: {CAT_NAME[cat]}\n- Original: {i['link']}\n- Canonical: {SITE}/story/{i['slug']}/\n\n{i['summary'] or 'Read the full report from the original publisher.'}\n\n_Ground Level News shows a short summary only; the full article and all rights belong to {i.get('source') or 'the original publisher'}._\n", encoding="utf-8")
        b = f"""<article class="story"><a class="crumb" href="/category/{cat}/">{esc(CAT_NAME[cat])}</a>
<h1>{esc(i['title'])}</h1><div class="byline">Source: <b>{esc(i.get('source'))}</b> · <time datetime="{iso(i['ts'])}">{dt.datetime.fromtimestamp(i['ts'] or NOW.timestamp(), dt.timezone.utc).strftime('%b %d, %Y %H:%M UTC')}</time></div>
{figure(cat_img(cat), False, "Category image, not from this story. ")}<div class="summary"><h2>The Quick Take</h2><p>{esc(i['summary']) or 'Read the full report from the original publisher.'}</p></div>
<a class="cta" href="{esc(i['link'])}" rel="noopener nofollow" target="_blank">Read the full story at {esc(i.get('source') or 'the source')} →</a>
<p class="attr">Ground Level News aggregates headlines from public feeds. This page shows a short summary only; the full article and all rights belong to {esc(i.get('source') or 'the original publisher')}.</p>
{f'<h2 class="rel">Related</h2><div class="grid">{"".join(card(r) for r in rel)}</div>' if rel else ''}</article>"""
        write(f"/story/{i['slug']}/", page(i["title"], b, i["summary"] or i["title"], f"/story/{i['slug']}/", ticker, "article",
              ldj(ld) + ldj(crumbs(("Home","/"),(CAT_NAME[cat],f"/category/{cat}/"),(i["title"][:110],f"/story/{i['slug']}/"))), md=f"/story/{i['slug']}.md"))

    # press releases
    lst = "".join(f'<a class="card pr-card" href="/press-releases/{p["slug"]}/"><span class="thumb">{img_tag(pr_img(p), sizes="(max-width:620px) 100vw, 400px")}</span><span class="tag t-pr">{esc(p.get("area") or "Release")}{" · EXAMPLE" if p.get("example") else ""}</span><h3>{esc(p["title"])}</h3><p>{esc(p.get("summary"))}</p><span class="meta">{esc(p.get("company"))} · {esc(p["date"])}</span></a>' for p in prs)
    write("/press-releases/", page("Press Releases", f'<h1 class="ph"><span class="bar t-pr"></span>Press Releases</h1><p class="lede">Local announcements from across Mohave Valley, Bullhead City, Laughlin, Clark County, Mesquite, Boulder City and beyond. <a href="https://github.com/AXIA-Enterprises-DEV/ground-level-news#publishing-press-releases">Submit a release →</a></p><div class="grid g3">{lst}</div>', "Press releases and local announcements on Ground Level News.", "/press-releases/", ticker))
    for p in prs:
        src = f'<p class="attr">Source: <a href="{esc(p["source_url"])}" rel="noopener" target="_blank">{esc(p.get("source_name") or p["source_url"])}</a></p>' if p.get("source_url") else ""
        b = f"""<article class="story"><a class="crumb" href="/press-releases/">Press Release{' · EXAMPLE' if p.get('example') else ''}</a><h1>{esc(p['title'])}</h1>
<div class="byline"><b>{esc(p.get('company'))}</b> · {esc(p['date'])}{' · ' + esc(p.get('area')) if p.get('area') else ''}</div>
{figure(pr_img(p), False)}<div class="summary"><p>{esc(p.get('summary'))}</p></div><div class="prose">{p['body']}</div>{src}
<p class="attr">Media contact: {esc(p.get('contact'))}</p></article>"""
        u = f"{SITE}/press-releases/{p['slug']}/"
        ld = {"@context":"https://schema.org","@type":"NewsArticle","headline":p["title"][:110],"datePublished":p["date"],"dateModified":p.get("updated") and str(p["updated"]) or p["date"],
              "mainEntityOfPage":u,"url":u,"image":[absimg(pr_img(p))],"articleSection":"Press Releases","description":p.get("summary") or "",
              "author":{"@type":"Organization","name":p.get("company") or NAME},"publisher":{"@id":SITE+"/#org","@type":"NewsMediaOrganization","name":NAME,"logo":ORG["logo"]}}
        if p.get("area"): ld["contentLocation"] = {"@type":"Place","name":p["area"]}
        if p.get("source_url"): ld["isBasedOn"] = p["source_url"]
        im = pr_img(p) or {}
        p["md_full"] = f"# {p['title']}\n\n- Date: {p['date']}\n- From: {p.get('company')}\n- Area: {p.get('area') or ''}\n- Canonical: {u}\n" + (f"- Source: {p['source_url']}\n" if p.get("source_url") else "") + (f"- Image: {absimg(im)} ({im.get('label')}; {im.get('credit')}; {im.get('license')}; {im.get('source')})\n" if im else "") + f"\n> {p.get('summary') or ''}\n\n{p['md']}\n\nMedia contact: {p.get('contact') or ''}\n"
        (OUT/f"press-releases/{p['slug']}.md").write_text(p["md_full"], encoding="utf-8")
        write(f"/press-releases/{p['slug']}/", page(p["title"], b, p.get("summary") or p["title"], f"/press-releases/{p['slug']}/", ticker, "article", ldj(ld) + ldj(crumbs(("Home","/"),("Press Releases","/press-releases/"),(p["title"][:110],f"/press-releases/{p['slug']}/"))), og_img=absimg(pr_img(p)), md=f"/press-releases/{p['slug']}.md"))

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
    bots = ["GPTBot","OAI-SearchBot","ChatGPT-User","ClaudeBot","Claude-User","Claude-SearchBot","PerplexityBot","Perplexity-User","Google-Extended","Applebot-Extended","Applebot","CCBot","Bingbot","Googlebot"]
    (OUT/"robots.txt").write_text("# Ground Level News welcomes search engines and AI agents. See /llms.txt and /agents.md\n" + "".join(f"User-agent: {b}\nAllow: /\n\n" for b in bots) + f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\nSitemap: {SITE}/news-sitemap.xml\n", encoding="utf-8")
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

## Key pages
- [Homepage]({SITE}/): top story, latest headlines and sections
- [Press releases]({SITE}/press-releases/): local announcements
- [About]({SITE}/about/): what the site is and how it works
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
- [Source repository]({REPO})
- [Example press release template]({SITE}/press-releases/2026-01-01-example-template.md)
"""
    (OUT/"llms.txt").write_text(llms, encoding="utf-8")
    (OUT/"llms-full.txt").write_text(f"# {NAME}: full text of press releases\n\n> Generated {NOW.strftime('%Y-%m-%d %H:%M UTC')} from {SITE}. Each release below is separated by a horizontal rule.\n\n" + "\n\n---\n\n".join(p["md_full"] for p in real), encoding="utf-8")
    agents = (ROOT/"AGENTS.md").read_text(encoding="utf-8") if (ROOT/"AGENTS.md").exists() else ""
    (OUT/"agents.md").write_text(agents, encoding="utf-8")
    (OUT/".well-known").mkdir(exist_ok=True)
    exp = (NOW + dt.timedelta(days=330)).strftime("%Y-%m-%dT00:00:00Z")
    (OUT/".well-known/security.txt").write_text(f"Contact: {REPO}/security/advisories/new\nContact: {REPO}/issues\nExpires: {exp}\nPreferred-Languages: en\nCanonical: {SITE}/.well-known/security.txt\n", encoding="utf-8")
    (OUT/"humans.txt").write_text(f"/* TEAM */\nPublisher: {NAME}\nSite: {SITE}\nSource: {REPO}\n\n/* SITE */\nLast update: {NOW.strftime('%Y/%m/%d')}\nStandards: HTML5, CSS3, schema.org, llms.txt\nSoftware: Python static site builder, GitHub Pages\n", encoding="utf-8")
    (OUT/f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY, encoding="utf-8")
    (OUT/"indexnow-urls.txt").write_text("\n".join([SITE + "/", SITE + "/press-releases/"] + [SITE + u for u, _, _ in news]) + "\n", encoding="utf-8")
    print("built", len(urls), "pages")

if __name__ == "__main__": main()
