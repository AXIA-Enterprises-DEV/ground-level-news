"""Page renderers: homepage, sections, stories, press releases, about, submit, 404. Owned by UI."""
import datetime as dt
from .config import OUT, SITE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME
from .text import esc, clean, ago, iso
from .images import story_img, pr_img, pick_img, img_tag, credit, figure
from .head import ORG, ldj, crumbs, absimg
from .shell import page, card, grid, write, og_for, OG_STORIES


def pr_card(p, cls="card pr-card"):
    return f'<a class="{cls}" href="/press-releases/{p["slug"]}/"><span class="thumb">{img_tag(pr_img(p), sizes="(max-width:640px) 100vw, (max-width:1000px) 50vw, 400px", small=True)}</span><span class="cb"><span class="tag t-pr">{esc(p.get("area") or "Release")}{" · Example" if p.get("example") else ""}</span><h3>{esc(p["title"])}</h3><p>{esc(clean(p.get("summary"), 170))}</p><span class="meta">{esc(p.get("company"))} · {esc(p["date"])}</span></span></a>'

def render_home(c):
    items, prs, ticker, by, real_prs = c.items, c.prs, c.ticker, c.by, c.real_prs
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


def render_categories(c):
    by, ticker = c.by, c.ticker
    for k, v in CATS:
        lst = by[k][:120]
        ban = pick_img(v, k, "banner-" + k)
        write(f"/category/{k}/", page(f"{v} News", f'<header class="phead"><h1 class="ph"><span class="bar t-{k}"></span>{v}</h1><p class="lede">The latest {v} headlines, updated every 15 minutes.</p></header>{figure(ban, False).replace("class=\"fig\"", "class=\"fig banner\"")}{grid([card(i) for i in lst], 18, "grid g3") if lst else "<p>No stories right now.</p>"}', f"Latest {v} headlines from {NAME}.", f"/category/{k}/", ticker))


def render_stories(c):
    items, by, ticker = c.items, c.by, c.ticker
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


def render_press_releases(c):
    prs, real_prs, ticker = c.prs, c.real_prs, c.ticker
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


def render_about(c):
    items, ticker = c.items, c.ticker
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


def render_404(c):
    ticker = c.ticker
    write("/404.html", page("Not found", '<article class="story"><h1>Page not found</h1><p>This story may have rolled off the wire. <a href="/">Back to the homepage →</a></p></article>', ticker=ticker))


def render_all(c):
    render_home(c); render_categories(c); render_stories(c); render_press_releases(c); render_about(c); render_404(c)
