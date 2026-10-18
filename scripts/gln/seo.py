"""Machine-readable outputs: RSS, Atom, sitemaps, robots, agents.txt, ai.txt, llms.txt, security.txt, IndexNow list. Owned by SEO."""
import datetime as dt
from .config import ROOT, OUT, SITE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME, INDEXNOW_KEY
from .text import esc, clean, iso


def render_feeds(c):
    """Writes all machine-readable files; returns the list of canonical page URLs (for the build summary)."""
    items, prs = c.items, c.prs
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
    return urls
