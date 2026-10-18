"""Machine-readable outputs: sitemap index + sitemaps, Google News sitemap, RSS/Atom (site, originals, per-section, per-area),
robots.txt, agents.txt, ai.txt, llms.txt, llms-full.txt, security.txt, humans.txt and the IndexNow list. Owned by SEO.
Reads the URL registry c.urls (DECISIONS §11), c.items (aggregated stories) and c.originals (press releases, briefs,
reports); never imports page renderers. Every attribute is read defensively so the build survives partial contexts."""
import datetime as dt, re
from .config import ROOT, OUT, SITE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME, INDEXNOW_KEY
from .text import esc, clean, iso
from .images import dims, pr_img
from . import head as H

MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif", "svg": "image/svg+xml"}
FEED_DESC = ("Local news for Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mesquite and Boulder City, "
             "plus U.S. and world headlines.")
XMLDECL = '<?xml version="1.0" encoding="UTF-8"?>\n'

def rfc822(ts): return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
def cdata(s): return "<![CDATA[" + str(s or "").replace("]]>", "]]]]><![CDATA[>") + "]]>"
def exists(path):
    f = OUT / path.strip("/")
    return (f / "index.html").exists() or f.is_file()
def region_name(key):
    r = (H.REGIONS or {}).get(key) or {}
    return r.get("name") or (H.AREAS.get(key) or (key.replace("-", " ").title(),))[0]
def kind_of(p): return p.get("kind") or "press-release"
def author_name(p):
    if kind_of(p) == "press-release": return p.get("company") or NAME
    return p.get("author") or f"{NAME} staff"
def og_card(slug):
    f = OUT / f"og/{slug}.jpg"
    return (f"{SITE}/og/{slug}.jpg", f.stat().st_size) if f.exists() else None
def write(rel, text):
    f = OUT / rel.lstrip("/"); f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text, encoding="utf-8")

# ---------- feed entries (one shape for stories and originals) ----------
def ent_pr(p):
    url = f"{SITE}/press-releases/{p['slug']}/"; pub = H.published(p); im = pr_img(p); image = None
    if im and im.get("src"):
        d = dims(im["src"]) if im["src"].startswith("/") else None
        image = {"url": H.absimg(im), "w": d[0] if d else None, "h": d[1] if d else None, "type": MIME.get(im["src"].rsplit(".", 1)[-1].lower(), "image/jpeg"),
                 "credit": im.get("credit") or NAME, "desc": im.get("alt") or ""}
    return {"url": url, "guid": url, "perma": True, "title": p["title"], "summary": clean(p.get("summary")), "ts": H.epoch(pub), "iso": pub, "mod": H.modified(p),
            "author": author_name(p), "cats": [c for c in ("Local", p.get("area"), H.KIND_LABEL.get(kind_of(p))) if c], "source": None,
            "content": p.get("body"), "image": image, "enclosure": og_card("pr-" + p["slug"]), "original": True}
def ent_item(i):
    cat = "local" if i.get("local") else i["cat"]
    ts = i["ts"] or int(NOW.timestamp())
    return {"url": f"{SITE}/story/{i['slug']}/", "guid": f"gln:{i['id']}", "perma": False, "title": i["title"], "summary": i.get("summary") or "", "ts": ts, "iso": iso(ts),
            "mod": None, "author": None, "cats": [CAT_NAME.get(cat, cat)], "source": (i.get("source") or "Wire report", i["link"]), "content": None, "image": None,
            "enclosure": None, "original": False}

def rss(path, title, desc, ents):
    ents = sorted(ents, key=lambda e: -e["ts"]); now = int(NOW.timestamp())
    x = [XMLDECL, '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/">\n<channel>',
         f'<title>{esc(title)}</title><link>{SITE}/</link><atom:link href="{SITE}{path}" rel="self" type="application/rss+xml"/><description>{esc(desc)}</description><language>en-us</language>',
         f"<copyright>© {NOW.year} {NAME}. Aggregated items remain the property of their publishers.</copyright><managingEditor>{CONTACT} ({NAME})</managingEditor><webMaster>{CONTACT} ({NAME})</webMaster>",
         f"<lastBuildDate>{rfc822(now)}</lastBuildDate><pubDate>{rfc822(ents[0]['ts'] if ents else now)}</pubDate><ttl>15</ttl><generator>{NAME} static builder</generator><docs>https://www.rssboard.org/rss-specification</docs>",
         f"<image><url>{SITE}/img/logo-full.png</url><title>{esc(title)}</title><link>{SITE}/</link><width>144</width><height>79</height></image>\n"]
    for e in ents:
        it = [f'<item><title>{esc(e["title"])}</title><link>{esc(e["url"])}</link><guid isPermaLink="{"true" if e["perma"] else "false"}">{esc(e["guid"])}</guid><pubDate>{rfc822(e["ts"])}</pubDate>']
        if e["author"]: it.append(f"<dc:creator>{esc(e['author'])}</dc:creator>")
        it += [f"<category>{esc(c)}</category>" for c in e["cats"]]
        if e["source"]: it.append(f'<source url="{esc(e["source"][1])}">{esc(e["source"][0])}</source>')
        if e["summary"]: it.append(f"<description>{esc(e['summary'])}</description>")
        if e["content"]: it.append(f"<content:encoded>{cdata(e['content'])}</content:encoded>")
        if e["image"]:
            im = e["image"]; wh = f' width="{im["w"]}" height="{im["h"]}"' if im["w"] else ""
            it.append(f'<media:content url="{esc(im["url"])}" medium="image"{wh} type="{im["type"]}"><media:credit>{esc(im["credit"])}</media:credit><media:description>{esc(im["desc"])}</media:description></media:content>')
        if e["enclosure"]: it.append(f'<enclosure url="{esc(e["enclosure"][0])}" type="image/jpeg" length="{e["enclosure"][1]}"/>')
        x.append("".join(it) + "</item>\n")
    write(path, "".join(x) + "</channel></rss>\n")

def atom(path, title, subtitle, ents):
    ents = sorted(ents, key=lambda e: -e["ts"])
    x = [XMLDECL, f'<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="en-US"><title>{esc(title)}</title><subtitle>{esc(subtitle)}</subtitle>',
         f'<link href="{SITE}{path}" rel="self" type="application/atom+xml"/><link href="{SITE}/" rel="alternate" type="text/html"/><id>{SITE}/</id>',
         f'<updated>{H.to_iso(ents[0]["ts"]) if ents else H.BUILD_ISO}</updated><author><name>{NAME}</name><email>{CONTACT}</email><uri>{SITE}/</uri></author>',
         f'<rights>© {NOW.year} {NAME}. Aggregated entries remain the property of their publishers.</rights><generator uri="{SITE}/">{NAME} static builder</generator>',
         f"<icon>{SITE}/favicon-32.png</icon><logo>{SITE}/og.png</logo>\n"]
    for e in ents:
        en = [f'<entry><title>{esc(e["title"])}</title><link rel="alternate" type="text/html" href="{esc(e["url"])}"/><id>{esc(e["url"])}</id>',
              f'<published>{e["iso"]}</published><updated>{e["mod"] or e["iso"]}</updated><author><name>{esc(e["author"] or (e["source"] or [NAME])[0])}</name></author>']
        en += [f'<category term="{esc(c)}" label="{esc(c)}"/>' for c in e["cats"]]
        if e["source"]: en.append(f'<link rel="via" href="{esc(e["source"][1])}" title="{esc(e["source"][0])}"/>')
        if e["enclosure"]: en.append(f'<link rel="enclosure" type="image/jpeg" length="{e["enclosure"][1]}" href="{esc(e["enclosure"][0])}"/>')
        if e["summary"]: en.append(f"<summary>{esc(e['summary'])}</summary>")
        if e["content"]: en.append(f'<content type="html">{esc(e["content"])}</content>')
        x.append("".join(en) + "</entry>\n")
    write(path, "".join(x) + "</feed>\n")

# ---------- URL registry ----------
STATIC_PAGES = ["/", "/local/", "/press-releases/", "/about/", "/editorial-policy/", "/corrections/", "/contact/", "/privacy/", "/terms/", "/submit/",
                "/llm-info/", "/identity/", "/accessibility/"]
def registry(c, originals, examples):
    """c.urls completed with the pages that exist in OUT but were not registered; no stories, examples or the 404."""
    urls = []
    seen = set()
    def add(u):
        loc = u.get("loc") or ""
        if not loc or loc in seen or loc.startswith("/story/") or u.get("kind") == "story" or loc in examples or "404" in loc: return
        if loc == "/category/local/" and exists("/local/"): return   # canonical is /local/
        u = {**u, "lastmod": H.to_iso(u.get("lastmod")) or H.BUILD_ISO}
        seen.add(loc); urls.append(u)
    for u in (getattr(c, "urls", None) or []): add(u)
    for loc in STATIC_PAGES + [f"/category/{k}/" for k, _ in CATS]:
        if loc not in seen and exists(loc):
            add({"loc": loc, "kind": "section" if loc.startswith("/category/") else "page", "lastmod": H.BUILD_ISO, "title": CAT_NAME.get(loc.strip("/").split("/")[-1], ""), "image": None, "ts": int(NOW.timestamp()), "summary": "", "area": None, "cat": None})
    for p in originals:
        pub = H.published(p)
        add({"loc": f"/press-releases/{p['slug']}/", "kind": "original", "lastmod": H.modified(p), "title": p["title"], "image": H.absimg(pr_img(p)), "ts": H.epoch(pub),
             "summary": p.get("summary") or "", "area": p.get("region"), "cat": "local"})
    return urls

def sm_url(loc, lastmod, image=None, news=None):
    x = f"<url><loc>{esc(loc)}</loc><lastmod>{esc(lastmod)}</lastmod>"
    if news:
        kw = f"<news:keywords>{esc(', '.join(news['keywords'][:6]))}</news:keywords>" if news.get("keywords") else ""
        x += f"<news:news><news:publication><news:name>{NAME}</news:name><news:language>en</news:language></news:publication><news:publication_date>{news['date']}</news:publication_date><news:title>{esc(news['title'])}</news:title>{kw}</news:news>"
    if image: x += f"<image:image><image:loc>{esc(image)}</image:loc></image:image>"
    return x + "</url>\n"
URLSET = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'

def render_feeds(c):
    """Writes every machine-readable file; returns the canonical page URLs (sitemap set)."""
    items = list(getattr(c, "items", None) or [])
    prs = list(getattr(c, "prs", None) or [])
    originals = list(getattr(c, "originals", None) or getattr(c, "real_prs", None) or [p for p in prs if not p.get("example")])
    examples = {f"/press-releases/{p['slug']}/" for p in prs if p.get("example")}
    by = getattr(c, "by", None) or {}
    urls = registry(c, originals, examples)
    hubs = [u for u in urls if u.get("kind") == "hub"]
    area_hubs = [u for u in hubs if u.get("area")]
    now_iso = H.BUILD_ISO

    # ---- sitemaps: index -> pages + press releases; stories are noindex and stay out
    (OUT / "sitemaps").mkdir(parents=True, exist_ok=True)
    pages = [u for u in urls if u.get("kind") != "original"]
    origs = [u for u in urls if u.get("kind") == "original"]
    write("/sitemaps/pages.xml", XMLDECL + URLSET + "".join(sm_url(SITE + u["loc"], u["lastmod"], u.get("image")) for u in pages) + "</urlset>\n")
    write("/sitemaps/press-releases.xml", XMLDECL + URLSET + "".join(sm_url(SITE + u["loc"], u["lastmod"], u.get("image")) for u in origs) + "</urlset>\n")
    write("/sitemap.xml", XMLDECL + '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"<sitemap><loc>{SITE}/sitemaps/{f}.xml</loc><lastmod>{max([u['lastmod'] for u in lst] or [now_iso])}</lastmod></sitemap>\n" for f, lst in (("pages", pages), ("press-releases", origs))) + "</sitemapindex>\n")
    cut = NOW.timestamp() - 48 * 3600
    news = [p for p in originals if H.epoch(H.published(p)) >= cut]
    news.sort(key=lambda p: -H.epoch(H.published(p)))
    write("/news-sitemap.xml", XMLDECL + URLSET + "".join(
        sm_url(f"{SITE}/press-releases/{p['slug']}/", H.modified(p), H.absimg(pr_img(p)), {"date": H.published(p), "title": p["title"], "keywords": [str(t) for t in (p.get("tags") or [])] or [x for x in (p.get("area"),) if x]})
        for p in news[:1000]) + "</urlset>\n")

    # ---- feeds
    pr_ents = [ent_pr(p) for p in originals]
    story_ents = [ent_item(i) for i in items[:100]]
    rss("/rss.xml", NAME, FEED_DESC, story_ents + pr_ents)
    atom("/feed.xml", NAME, TAG, story_ents + pr_ents)
    rss("/press-releases/feed.xml", f"{NAME}: Local", "Local news, press releases, briefs and reports for the Colorado River region.", pr_ents)
    for k, v in CATS:
        ents = [ent_item(i) for i in (by.get(k) or [i for i in items if i.get("cat") == k])[:50]] + (pr_ents if k == "local" else [])
        rss(f"/category/{k}/feed.xml", f"{NAME}: {v}", f"{v} headlines from {NAME}.", ents)
    for u in area_hubs:
        a = u["area"]; nm = u.get("title") or region_name(a)
        ents = [ent_pr(p) for p in originals if p.get("region") == a] + [ent_item(i) for i in items if a in (i.get("regions") or [])][:50]
        rss(f"/local/{a}/feed.xml", f"{NAME}: {region_name(a)}", clean(u.get("summary") or f"{nm} on {NAME}.", 300), ents)

    # ---- robots.txt (§5.5): one wildcard group; Googlebot/Bingbot keep Markdown twins out of web search
    write("/robots.txt", f"""# {NAME} welcomes search engines and AI agents. See {SITE}/agents.txt, {SITE}/llms.txt and {SITE}/llm-info/
# All AI crawlers are welcome; see /agents.txt for the usage policy.
User-agent: *
Allow: /

# Keep Markdown twins and the full-text dump out of web search indexes (agents may still read them)
User-agent: Googlebot
Disallow: /*.md$
Disallow: /llms-full.txt

User-agent: Bingbot
Disallow: /*.md$
Disallow: /llms-full.txt

Sitemap: {SITE}/sitemap.xml
Sitemap: {SITE}/news-sitemap.xml
""")
    write("/agents.txt", f"""# agents.txt for {SITE.split('//')[1]}
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
News-Sitemap: {SITE}/news-sitemap.xml
Owner: {NAME}
Contact: {CONTACT}
Standard-Followed: https://llmbestpractices.com
Updated: {NOW.strftime('%Y-%m-%d')}
""")
    write("/ai.txt", f"# {SITE}/ai.txt\nUser-Agent: *\nTrain: yes\nQuote: yes\nSummarize: yes\nContact: {CONTACT}\n")

    # ---- llms.txt / llms-full.txt
    policy = [("Editorial policy", "/editorial-policy/", "aggregation method, attribution and AI-use disclosure"), ("Corrections", "/corrections/", "how to request a correction"),
              ("Contact", "/contact/", "newsroom contact"), ("Privacy", "/privacy/", "privacy notice"), ("Terms", "/terms/", "terms of use")]
    policy_md = "".join(f"- [{t}]({SITE}{u}): {d}\n" for t, u, d in policy if exists(u))
    hubs_md = "".join(f"- [{h.get('title') or region_name(h.get('area') or '')}]({SITE}{h['loc']})" + (f": {clean(h['summary'], 160)}" if h.get("summary") else "") + "\n" for h in hubs)
    kind_md = lambda p: {"brief": " (brief)", "report": " (report)"}.get(kind_of(p), "")
    llms = f"""# {NAME}

> {NAME} ({SITE}) is a free local news site for the Colorado River region: Bullhead City, Laughlin, Mohave Valley, Fort Mohave, Lake Havasu City, Kingman, Mohave County, Clark County, Mesquite and Boulder City. It publishes local press releases, briefs and reports, and wraps them in a front page of U.S. and world headlines aggregated from public RSS feeds, each summarized and linked to its original publisher. The site is rebuilt around the clock; see the Updated line below.

Every HTML article has a Markdown twin: append `.md` to the path without the trailing slash (e.g. `/press-releases/<slug>.md`, `/story/<slug>.md`). Aggregated story pages contain short summaries only and are marked noindex; rights belong to the original publishers. Images carry credit and license lines; "File photo" and "Illustration" images do not depict the actual event.

## Primary
- [LLM info]({SITE}/llm-info/): machine-readable description of this site, methodology and instructions for AI assistants
- [Agent policy]({SITE}/agents.txt): training, indexing and summarization allowed; citation required

## Key pages
- [Homepage]({SITE}/): local lead, latest headlines and sections
{f"- [Local news hub]({SITE}/local/): all local originals, area pages and events" + chr(10) if exists("/local/") else ""}- [Press releases]({SITE}/press-releases/): local announcements, briefs and reports
- [About & sources]({SITE}/about/): ownership, how the site works and where the news comes from
{policy_md}- [Submit a press release]({SITE}/submit/): free local press-release submissions
- [Brand identity]({SITE}/identity/): logo, colors, fonts and media assets
- [Agent guide]({SITE}/agents.md): site structure and how to submit a press release
- [Full press release text]({SITE}/llms-full.txt)
""" + (f"\n## Local areas and topics\n{hubs_md}" if hubs_md else "") + "\n## Local news (originals)\n" + "".join(
        f"- [{p['title']}]({SITE}/press-releases/{p['slug']}.md): {clean(p.get('summary'), 200)}{kind_md(p)}\n" for p in originals) + "\n## Sections\n" + "".join(
        f"- [{v}]({SITE}/category/{k}/)\n" for k, v in CATS if not (k == "local" and exists("/local/"))) + f"""
## Feeds and data
- [RSS]({SITE}/rss.xml)
- [Atom]({SITE}/feed.xml)
- [Local news RSS]({SITE}/press-releases/feed.xml)
- [Sitemap index]({SITE}/sitemap.xml)
- [Google News sitemap]({SITE}/news-sitemap.xml)

## Optional
- [Accessibility statement]({SITE}/accessibility/)
- [AI policy]({SITE}/ai.txt)

## About
- Owner: {NAME}
- Contact: {CONTACT}
- Standard followed: https://llmbestpractices.com
- Updated: {NOW.strftime('%Y-%m-%d')}
"""
    write("/llms.txt", llms)
    write("/llms-full.txt", f"# {NAME}: full text of local originals\n\n> Generated {NOW.strftime('%Y-%m-%d %H:%M UTC')} from {SITE}. Each item below is separated by a horizontal rule.\n\n"
          + "\n\n---\n\n".join(p.get("md_full") or f"# {p['title']}\n\n{p.get('md', '')}" for p in originals))
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8") if (ROOT / "AGENTS.md").exists() else ""
    write("/agents.md", agents)
    exp = (NOW + dt.timedelta(days=330)).strftime("%Y-%m-%dT00:00:00Z")
    sec = f"Contact: mailto:{CONTACT}\nExpires: {exp}\nPreferred-Languages: en\nCanonical: {SITE}/.well-known/security.txt\n" + (f"Policy: {SITE}/contact/\n" if exists("/contact/") else "")
    write("/.well-known/security.txt", sec); write("/security.txt", sec)
    write("/humans.txt", f"/* TEAM */\nPublisher: {NAME}\nSite: {SITE}\nContact: {CONTACT}\n\n/* SITE */\nLast update: {NOW.strftime('%Y/%m/%d')}\nStandards: HTML5, CSS3, schema.org, llms.txt\nSoftware: Python static site builder, GitHub Pages\n")
    write(f"/{INDEXNOW_KEY}.txt", INDEXNOW_KEY)
    # IndexNow: home, local hubs and originals; the workflow diffs this list against the previous run and submits additions only
    idx = [SITE + "/"] + [SITE + u["loc"] for u in urls if u["loc"] in ("/local/", "/press-releases/") or u.get("kind") in ("hub", "original")]
    write("/indexnow-urls.txt", "\n".join(dict.fromkeys(idx)) + "\n")
    return [SITE + u["loc"] for u in urls]
