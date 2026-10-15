# AGENTS.md: Ground Level News

Guide for AI agents and automated tools working with **groundlevelnews.com** and this repository.

## What the site is
Ground Level News is a static news site: U.S./world headlines aggregated from public RSS feeds (via the `news-tracker` data feed) plus local press releases for the Colorado River region (Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite, Boulder City). It is rebuilt about every 15 minutes by GitHub Actions and served by GitHub Pages at https://groundlevelnews.com.

## Site structure
| Path | What it is |
|---|---|
| `/` | Homepage: top story, Latest, sections, press releases |
| `/category/<us,world,politics,business,markets,tech,science,sports,local>/` | Section pages |
| `/story/<slug>/` and `/story/<slug>.md` | Aggregated story: short summary + link to the original publisher (who owns the content) |
| `/press-releases/` | Press release index |
| `/press-releases/<slug>/` and `/press-releases/<slug>.md` | Full press release, HTML and Markdown |
| `/llms.txt`, `/llms-full.txt` | LLM index and full text of all press releases |
| `/rss.xml`, `/feed.xml` | RSS 2.0 and Atom feeds |
| `/sitemap.xml`, `/news-sitemap.xml` | Full sitemap and Google News sitemap (last 48h) |
| `/about/` | How the site works and where the news comes from |
| `/submit/` | How to submit a press release |
| `/llm-info/` (+ `.md`) | Machine-readable site description and instructions for AI assistants (start here) |
| `/identity/` | Brand page: logo, colors, fonts, assets |
| `/agents.txt`, `/ai.txt` | Agent and AI usage policy (training, indexing, summarization allowed; citation required) |
| `/agents.md` | This file |

Every HTML page has a canonical URL on https://groundlevelnews.com, JSON-LD (NewsMediaOrganization, WebSite, NewsArticle, BreadcrumbList) and, for articles, a `<link rel="alternate" type="text/markdown">` to its Markdown twin.

This site follows the LLM discoverability standard at https://llmbestpractices.com (`scripts/check_llm_layer.py` verifies the build in CI).

## Usage notes for agents
- Crawling is allowed for all agents (see `/robots.txt`). Please keep request rates reasonable.
- Story pages contain summaries only. Cite and link the original publisher in the `isBasedOn` / "Read the full story" link.
- Images labelled "File photo" or "Illustration" do not show the actual event. Credits and licenses are on each image.

## Submitting a press release
1. **Email (easiest):** see https://groundlevelnews.com/submit/. Send the release to news@groundlevelnews.com with the fields `Title`, `Date`, `Company`, `Contact`, `Summary`, `Area`, `Source URL`, `Body`. An editor reviews it before it is published.
2. **Pull request:** add `content/press-releases/YYYY-MM-DD-slug.md` with front matter:
   ```yaml
   ---
   title: "Headline"
   date: 2026-10-13
   company: "Organization"
   area: "Bullhead City"
   contact: "Name, email or phone"
   summary: "One or two sentences."
   source_url: "https://..."            # optional
   image: /img/photos/example.webp      # optional; falls back to a category image
   image_alt: "Describe the image"
   image_credit: "Author / Wikimedia Commons"
   image_license: "CC BY-SA 4.0"
   image_source: "https://commons.wikimedia.org/wiki/File:..."
   image_label: "File photo"            # or "Illustration"
   ---
   Markdown body…
   ```
   Images must be openly licensed or your own, with no photos of private individuals.

## Repo layout (for coding agents)
- `scripts/build.py`: the whole static site generator (Python; deps in `requirements.txt`). Run `python scripts/build.py` → `_site/`.
- `content/press-releases/*.md`: press releases. **Do not edit article text without editorial approval.**
- `content/images.yaml`: photo registry (with `buckets` and headline `keywords` used to match photos to stories) and category fallback images, with attribution.
- `scripts/brand.py`: branded category cards and share cards (Pillow).
- `static/`: CSS, logo, favicons, images, copied verbatim into `_site/`.
- `.github/workflows/build.yml`: build, deploy to Pages, then ping IndexNow.
