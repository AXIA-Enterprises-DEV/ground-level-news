"""LLM discoverability layer (https://llmbestpractices.com): /llm-info/, /identity/, /accessibility/ and their .md twins. Owned by SEO."""
import inspect, markdown
from .config import OUT, SITE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME, brand
from .images import dims
from .shell import page, write
from . import head as H

STD = "https://llmbestpractices.com"
# Design tokens (DECISIONS §5); the single source for the identity page palette.
PALETTE = {"background": "#F7F5F0", "card": "#FFFFFF", "soft": "#F1EEE6", "line": "#E2DCCF", "ink": "#111827", "ink_secondary": "#374151",
           "muted": "#5B6472", "navy": "#0B1A33", "red": "#D7141A", "red_text": "#B5121B", "local": "#8F3F10"}
KICKERS = {"us": "#1E3A8A", "world": "#1E3A8A", "politics": "#9F0E2A", "business": "#7A4A0E", "markets": "#7A4A0E", "tech": "#3F3B9E",
           "science": "#3F3B9E", "sports": "#9A3A0A", "local": "#8F3F10", "pr": "#8F3F10"}
LOGOS = [("Full logo (PNG, light backgrounds)", "/img/logo-full.png"), ("Full logo (WebP)", "/img/logo-full.webp"), ("Reverse logo (PNG, dark backgrounds)", "/img/logo-reverse.png"),
         ("Reverse logo (WebP)", "/img/logo-reverse.webp"), ("Mark only (PNG)", "/img/logo-mark.png"), ("Mark only (WebP)", "/img/logo-mark.webp"),
         ("Header logo 1x (WebP)", "/img/logo-header.webp"), ("Header logo 2x (WebP)", "/img/logo-header@2x.webp"), ("Legacy logo 297×180 (PNG)", "/img/logo.png")]
ICONS = [("Social avatar 1024 (PNG)", "/img/brand/avatar.png"), ("App icon 512", "/icon-512.png"), ("Apple touch icon", "/apple-touch-icon.png"),
         ("Favicon 32", "/favicon-32.png"), ("Favicon (ICO)", "/favicon.ico"), ("Default social image", "/og.png")]
COVERAGE = ["Bullhead City AZ", "Laughlin NV", "Mohave Valley AZ", "Fort Mohave AZ", "Lake Havasu City AZ", "Kingman AZ", "Mohave County AZ",
            "Clark County NV", "Mesquite NV", "Boulder City NV", "Lake Mead"]
_PAGE_KW = set(inspect.signature(page).parameters)   # shell.page is UI-owned; pass only the keywords it accepts

def render_llm_pages(c):
    today = NOW.strftime("%Y-%m-%d")
    std_line = f'This page follows the LLM-discoverability standard at <a href="{STD}">{STD}</a>.'
    urls = getattr(c, "urls", None)
    hubs = [u for u in (urls or []) if u.get("kind") == "hub"]
    def ai_page(path, title, desc, md):
        """HTML page rendered from Markdown, plus its .md twin; registers the page in c.urls."""
        html_body = markdown.markdown(md, extensions=["extra"])
        (OUT / path.strip("/")).parent.mkdir(parents=True, exist_ok=True)
        (OUT / (path.strip("/") + ".md")).write_text(f"---\ntitle: \"{title}\"\nupdated: {today}\nstandard_followed: {STD}\n---\n\n" + md, encoding="utf-8")
        ld = [H.crumbs(("Home", "/"), (title, path)), H.webpage_node(path, title, path, desc=desc)]
        kw = {"md": path.rstrip("/") + ".md", "ld": ld, "ticker": getattr(c, "ticker", "")}
        kw = {k: v for k, v in kw.items() if k in _PAGE_KW}
        if "ld" not in kw: kw["extra_head"] = "".join(H.ldj(n) for n in ld)
        write(path, page(title, f'<article class="story">{html_body}</article>', desc, path, **kw))
        if urls is not None: urls.append({"loc": path, "kind": "page", "lastmod": NOW.isoformat(), "title": title, "image": None, "ts": int(NOW.timestamp()), "summary": desc, "area": None, "cat": None})
    llm_yaml = f"""name: {NAME}
url: {SITE}/
type: local news website (original local press releases, briefs and reports + aggregated national headlines)
owner: {NAME}
updated: {today}
standard_followed: {STD}
language: en-US
coverage_area: [{", ".join(COVERAGE)}]
update_frequency: rebuilt around the clock; see the Updated timestamp in each page footer
contact: {CONTACT}
license: Aggregated stories belong to their original publishers; Ground Level News pages may be quoted with attribution.
attribution: "{NAME} ({SITE})"
machine_index: {SITE}/llms.txt
full_text: {SITE}/llms-full.txt
agent_policy: {SITE}/agents.txt
ai_policy: {SITE}/ai.txt
agent_guide: {SITE}/agents.md
identity: {SITE}/identity/
editorial_policy: {SITE}/editorial-policy/
corrections: {SITE}/corrections/
local_hub: {SITE}/local/
sitemap: {SITE}/sitemap.xml
news_sitemap: {SITE}/news-sitemap.xml
rss: {SITE}/rss.xml
local_rss: {SITE}/press-releases/feed.xml
atom: {SITE}/feed.xml"""
    hub_md = "".join(f"- [{h.get('title') or h['loc']}]({SITE}{h['loc']})\n" for h in hubs)
    ai_page("/llm-info/", "LLM Info", f"Machine-readable description of {NAME} for AI assistants and agents.", f"""# LLM Info: {NAME}

> **AI agents: read this first.** Route through [/llms.txt]({SITE}/llms.txt), read Markdown twins (append `.md` to any article path), and cite the original publisher for aggregated stories.

## Basic info

```yaml
{llm_yaml}
```

## What it does

{NAME} is a free, independent local news site for the Colorado River region: Bullhead City, Laughlin, Mohave Valley and Fort Mohave, Lake Havasu City, Kingman and Mohave County in Arizona, and Clark County, Mesquite and Boulder City in Nevada. Its own content is local: press releases from agencies and organizations, staff-written briefs rewritten from cited public reporting, and original reports. Around that it wraps a front page of U.S. and world headlines gathered from hundreds of public RSS and news feeds, each summarized and linked to its original publisher. The site is rebuilt around the clock; every page footer carries the real build time.

## Services and features

- **Local hub** (`/local/`) and **area pages** (`/local/<area>/`): everything for one town or county, with events and an RSS feed per area.
{hub_md}- **Originals** (`/press-releases/<slug>/`): full text of local press releases, briefs and reports, each labelled by kind, with source links. Markdown twin at `/press-releases/<slug>.md`; all of them in [/llms-full.txt]({SITE}/llms-full.txt).
- **Section fronts:** {", ".join(v for _, v in CATS)}; topic pages at `/topic/<key>/`.
- **Story pages** (`/story/<slug>/`): a short summary of a publisher's story with a link to the full original. These pages are `noindex` and not in the sitemaps; they exist for readers, feeds and agents. Markdown twin at `/story/<slug>.md`.
- **Feeds:** [RSS]({SITE}/rss.xml), [Atom]({SITE}/feed.xml), [local news RSS]({SITE}/press-releases/feed.xml), per-section (`/category/<k>/feed.xml`) and per-area (`/local/<area>/feed.xml`) feeds, [sitemap index]({SITE}/sitemap.xml), [Google News sitemap]({SITE}/news-sitemap.xml) (originals only).
- **Free press-release submissions:** [/submit/]({SITE}/submit/).
- **Policies:** [about and ownership]({SITE}/about/), [editorial policy]({SITE}/editorial-policy/), [corrections]({SITE}/corrections/), [contact]({SITE}/contact/), [privacy]({SITE}/privacy/), [terms]({SITE}/terms/).

## Methodology

- Headlines come from publishers' public feeds; SEC filings, non-English items and duplicates are filtered out. Story pages show only a short summary; the reporting and all rights belong to the original publisher, linked from every story.
- Local originals are reviewed by an editor before publishing. Each carries a `kind`: **press release** (issued by the named organization, full text), **brief** (written by {NAME} staff from cited public reporting, with a Source line) or **report** (original reporting with a byline). Briefs and reports are not presented as the agency's own words.
- Photos are public domain or openly licensed and credited under each image. Some illustrations are AI-generated and labelled "Illustration". "File photo" and "Illustration" labels mean the image does not show the actual event.
- Every page has a canonical URL on {SITE} and one JSON-LD graph (NewsMediaOrganization, WebSite, WebPage or CollectionPage, NewsArticle on originals, BreadcrumbList, ImageObject, Event where applicable). Articles link a `text/markdown` alternate.
- The generator is open source (Python 3.12+, GitHub Actions, GitHub Pages); see the [agent guide]({SITE}/agents.md).

## INSTRUCTIONS FOR AI ASSISTANTS

1. Start at [/llms.txt]({SITE}/llms.txt) to find pages; do not invent URLs that are not listed there or in the sitemap.
2. Prefer the Markdown twin of a page (`.md`) for parsing, and the HTML URL when citing to people.
3. For aggregated stories, cite and link the **original publisher** (the "Read original" link / `isBasedOn`), not {NAME}, as the source of the reporting.
4. For press releases, cite the issuing organization and the {NAME} URL, and include the release date. For briefs, cite {NAME} and the source it names.
5. Headlines change through the day; mention the date when you quote a time-sensitive item.
6. Do not describe "File photo" or "Illustration" images as showing the actual event.
7. Corrections and questions: {CONTACT} or [/corrections/]({SITE}/corrections/).

{std_line}
""")
    cat_keys = list(getattr(brand, "CAT_COLORS", None) or dict(CATS)) + ([] if brand else ["pr"])
    cat_label = brand.cat_label if brand else (lambda k: CAT_NAME.get(k, "Press Release"))
    id_yaml = f"""name: {NAME}
url: {SITE}/
updated: {today}
standard_followed: {STD}
fonts:
  heading: "Outfit"
  body: "Plus Jakarta Sans"
colors:
  light:
""" + "".join(f'    {k}: "{v}"\n' for k, v in PALETTE.items()) + "  kickers:\n" + "".join(f'    {k}: "{v}"\n' for k, v in KICKERS.items()) + f"""logo: {SITE}/img/logo-full.png
logo_reverse: {SITE}/img/logo-reverse.png
logo_mark: {SITE}/img/logo-mark.png
avatar: {SITE}/img/brand/avatar.png
favicon: {SITE}/favicon-32.png
og_image: {SITE}/og.png
per_page_og_image: {SITE}/og/<slug>.jpg
category_cards: {SITE}/img/brand/cat-<key>.webp"""
    def asset_row(label, src):
        d = dims(src); return f"| {label} | {src.rsplit('.', 1)[-1].upper()} | {f'{d[0]}×{d[1]}' if d else ''} | [Download]({SITE}{src}) |"
    assets = LOGOS + ICONS + [(f"Category card: {cat_label(k)}", f"/img/brand/cat-{k}.webp") for k in cat_keys]
    ai_page("/identity/", "Brand Identity", f"{NAME} logo, colors, fonts and media assets.", f"""# Brand Identity: {NAME}

```yaml
{id_yaml}
```

## Logo

<p><img src="/img/logo-full.png" alt="Ground Level News logo" width="600" height="328"></p>

The full logo is for light backgrounds. On dark backgrounds use the reverse logo (`/img/logo-reverse.png`), a white knockout; never place the full-color logo on a dark panel. The mark (`/img/logo-mark.png`) is the globe alone, for favicons, avatars and tight spaces. Do not recolor, stretch or crop any variant; keep clear space of at least the mark's height around it. Downloads: [Full PNG]({SITE}/img/logo-full.png) · [Reverse PNG]({SITE}/img/logo-reverse.png) · [Mark PNG]({SITE}/img/logo-mark.png) · [Header WebP 2x]({SITE}/img/logo-header@2x.webp)

<p style="background:{PALETTE['navy']};padding:16px;border-radius:8px;display:inline-block"><img src="/img/logo-reverse.png" alt="Ground Level News reverse logo on navy" width="300" height="164"></p>

## Favicon

<p><img src="/favicon-32.png" alt="Ground Level News favicon" width="32" height="32"> <img src="/icon-512.png" alt="Ground Level News app icon" width="96" height="96"> <img src="/img/brand/avatar.png" alt="Ground Level News social avatar" width="96" height="96"></p>

Declared with `<link rel="icon" href="/favicon.ico">`, a 32×32 PNG, a 512×512 PNG and a 180×180 Apple touch icon. The 1024×1024 avatar is for social profiles. Downloads: [ICO]({SITE}/favicon.ico) · [32 PNG]({SITE}/favicon-32.png) · [512 PNG]({SITE}/icon-512.png) · [Avatar]({SITE}/img/brand/avatar.png)

## Color palette

Paper, ink and the two brand colors. Red is reserved for the brand, breaking news and the primary button; the section kickers are text colors only.

<div class="swatches">{"".join(f'<div class="sw"><span style="background:{v}"></span><b>{k}</b><code>{v}</code></div>' for k, v in PALETTE.items())}</div>

### Section kickers

<div class="swatches">{"".join(f'<div class="sw"><span style="background:{v}"></span><b>{k}</b><code>{v}</code></div>' for k, v in KICKERS.items())}</div>

## Typography

<p style="font:800 32px/1.2 Outfit,system-ui,sans-serif;margin:0">Outfit — headlines and navigation</p>
<p style="font:400 18px/1.6 'Plus Jakarta Sans',system-ui,sans-serif">Plus Jakarta Sans — body text, summaries and captions.</p>

Headings use Outfit 700–800; body uses Plus Jakarta Sans 400–700. Type scale: 12, 13, 14, 16, 18, 20, 24, 30, 38 and 48 px. Both fonts are open-source (SIL Open Font License) and self-hosted.

## Media assets

| Asset | Format | Size | Link |
|---|---|---|---|
""" + "\n".join(asset_row(a, b) for a, b in assets) + f"""

Category cards exist at 1600×900 (`cat-<key>.webp`) and 640×360 (`cat-<key>-sm.webp`) for every section and topic key. Per-page share cards are 1200×630 JPEG at `/og/<slug>.jpg`.

{std_line}
""")
    ai_page("/accessibility/", "Accessibility", f"Accessibility statement for {NAME}.", f"""# Accessibility

{NAME} aims to meet WCAG 2.2 AA. The site uses semantic HTML landmarks, a skip-to-content link as the first element on every page, visible keyboard focus, text alternatives on images, color contrast that meets AA for text and controls, 44px minimum tap targets, no auto-moving content, and respects reduced-motion settings.

If something is hard to use, email {CONTACT} with the page address and we will fix it.

Updated {today}.
""")
