"""LLM discoverability layer (https://llmbestpractices.com): /llm-info/, /identity/, /accessibility/ and their .md twins."""
import markdown
from .config import OUT, SITE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME
from .images import dims
from .shell import page, write


def render_llm_pages(c):
    ticker = c.ticker
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
