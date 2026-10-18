# AGENTS.md: Ground Level News

Guide for AI agents and automated tools working with **groundlevelnews.com** and this repository.

## What the site is
Ground Level News is an independent static news site for the Colorado River region of Arizona and Nevada. It publishes original local items (press releases, briefs and reports) for Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mohave County, Clark County, Mesquite, Boulder City and Lake Mead, wrapped in U.S./world headlines aggregated from publishers' public RSS feeds (via the `news-tracker` data feed). It is rebuilt by GitHub Actions around the clock and served by GitHub Pages at https://groundlevelnews.com. The footer `Updated` timestamp on every page is the time of the current edition.

## Site structure
| Path | What it is |
|---|---|
| `/` | Homepage: lead package, Latest, "Around the Colorado River" (local), sections, topics |
| `/local/` | Local hub: all original items, area chips, upcoming events |
| `/local/<area>/` | Area hubs: `bullhead-city`, `laughlin`, `mohave-valley`, `lake-havasu-city`, `kingman`, `mohave-county`, `clark-county`, `las-vegas`, `mesquite`, `boulder-city`, `lake-mead`, `colorado-river`, `needles`, `nevada`, `arizona` (+ `feed.xml` per area) |
| `/category/<us,world,politics,business,markets,tech,science,sports,local>/` | Section pages (+ `feed.xml` per section); `/category/local/` mirrors `/local/` |
| `/topic/<energy,realestate,smallbiz,fed,ai,cannabis,golf,media>/` | Topic hubs from tracker projects |
| `/story/<slug>/` and `/story/<slug>.md` | Aggregated story: headline + short summary + link to the original publisher (who owns the content). **`noindex,follow`**, not in sitemaps |
| `/press-releases/` | Index of original local items (press releases, briefs, reports) |
| `/press-releases/<slug>/` and `/press-releases/<slug>.md` | Full original item, HTML and Markdown; `/press-releases/feed.xml` is the originals-only feed |
| `/llms.txt`, `/llms-full.txt` | LLM index and full text of all original items |
| `/rss.xml`, `/feed.xml` | RSS 2.0 and Atom feeds (stories + originals) |
| `/sitemap.xml` → `/sitemaps/pages.xml`, `/sitemaps/press-releases.xml`; `/news-sitemap.xml` | Sitemap index and Google News sitemap (originals from the last 48h only) |
| `/about/` (+ `.md`) | Ownership, funding, masthead, coverage area, where the news comes from, sources in today's edition, removal requests |
| `/editorial-policy/` (+ `.md`) | Aggregation and attribution rules, content kinds and labels, AI-use disclosure, ethics, corrections standards |
| `/corrections/` (+ `.md`) | How to request a correction; corrections log (from `content/corrections.yaml`) |
| `/contact/` (+ `.md`) | Tips, press releases, corrections, partnerships, security (mailto links; no form) |
| `/privacy/`, `/terms/` (+ `.md`) | Privacy policy (static site, no cookies/analytics) and terms of use |
| `/submit/` (+ `.md`) | How to submit a press release, event notice or community announcement; front-matter template |
| `/llm-info/` (+ `.md`) | Machine-readable site description and instructions for AI assistants (start here) |
| `/identity/` (+ `.md`) | Brand page: logo, colors, fonts, assets |
| `/accessibility/` (+ `.md`) | Accessibility statement |
| `/agents.txt`, `/ai.txt` | Agent and AI usage policy (training, indexing, summarization allowed; citation required) |
| `/agents.md` | This file |

Every HTML page has a canonical URL on https://groundlevelnews.com and one JSON-LD `@graph` (NewsMediaOrganization + WebSite, plus NewsArticle/Event/BreadcrumbList/CollectionPage as appropriate). Articles and policy pages carry a `<link rel="alternate" type="text/markdown">` to their Markdown twin (append `.md` to the path without the trailing slash).

This site follows the LLM discoverability standard at https://llmbestpractices.com (`scripts/check_llm_layer.py` verifies the build in CI).

## Usage notes for agents
- Crawling is allowed for all agents (see `/robots.txt`). Please keep request rates reasonable. Googlebot and Bingbot are asked not to index the `.md` twins and `/llms-full.txt`; AI agents may read them.
- **Indexing policy:** aggregated `/story/` pages are `noindex,follow` and are not in the sitemaps; original items, hubs, sections and policy pages are indexable. Cite and link the original publisher for aggregated stories (the `isBasedOn` / "Read the full story" link).
- **Content kinds:** every original item has a `kind`. `press-release` = text issued by the named organization (byline = organization, has a media contact). `brief` = rewritten by Ground Level News staff from cited public reporting (byline "Ground Level News staff", has a Source link, no media contact). `report` = original reporting by Ground Level News (named author or staff). Cite accordingly. See `/editorial-policy/`.
- Images labelled "File photo" show the place or subject in general, not the event. Images labelled "Illustration" are generated with the open-source Z-Image-Turbo model, never depict real people or the actual event, and are labelled as such. Credits and licenses are on each image.
- Items with `example: true` (the format template) are excluded from the index, feeds, sitemaps and `llms.txt` and are `noindex`.

## Submitting a press release
1. **Email (easiest):** see https://groundlevelnews.com/submit/. Send the release to news@groundlevelnews.com with the fields `Kind`, `Title`, `Date`, `Company`, `Contact`, `Summary`, `Area`, `Source URL`, event details (optional) and `Body`. An editor reviews it before it is published, usually within one business day.
2. **Pull request:** add `content/press-releases/YYYY-MM-DD-slug.md` with front matter:
   ```yaml
   ---
   title: "Headline"
   date: 2026-10-13
   kind: press-release                  # press-release | brief | report (default press-release)
   published: "2026-10-13T09:00:00-07:00"   # optional full timestamp; defaults to date + T12:00:00-07:00
   updated: "2026-10-14T08:00:00-07:00"     # optional; when the item was last changed
   company: "Organization"
   area: "Bullhead City"                # maps to a /local/<area>/ hub
   contact: "Public media contact: name, email or phone"
   summary: "One or two sentences."
   source_url: "https://..."            # optional; expected for briefs
   source_name: "Publisher or agency"   # optional
   author: "Name"                       # optional; briefs and reports
   tags: [events, fire]                 # optional
   event_start: "2026-10-17T10:00:00-07:00"   # optional; ISO 8601 with offset
   event_end: "2026-10-17T14:00:00-07:00"     # optional
   event_all_day: true                  # optional; with a T00:00:00 event_start when only the date is known
   venue: "Station 91"                  # optional
   address: "2230 Joy Lane, Fort Mohave, AZ"  # optional
   event_url: "https://..."             # optional
   image: /img/photos/example.webp      # optional; falls back to a category image
   image_alt: "Describe the image"
   image_credit: "Author / Wikimedia Commons"
   image_license: "CC BY-SA 4.0"
   image_source: "https://commons.wikimedia.org/wiki/File:..."
   image_label: "File photo"            # or "Illustration"
   ---
   Markdown body…
   ```
   Images must be openly licensed or your own, with no photos of private individuals. Body Markdown is sanitised at build time (no scripts or inline HTML). Quote YAML strings that contain colons.
3. **GitHub issue form:** the "Submit a press release" issue template collects the same fields; a workflow validates the date and slug and opens a pull request with the file.

## Repo layout (for coding agents)
- `scripts/build.py`: orchestrates the build (Python 3.12+; deps in `requirements.txt`). Run `python scripts/build.py` → `_site/`.
- `scripts/gln/`: the generator package. Dependency direction: `config` → `text` → `feed` / `images` / `taxonomy` → `head` → `shell` → `pages` / `local` / `editorial` / `llm_layer` / `seo` → `build.py`.
  - `config.py` constants and environment; `text.py` escaping, cleaning, dates; `feed.py` tracker JSON + press-release loading (front matter, sanitising); `taxonomy.py` regions, categorisation, publisher table, ranking; `images.py` photo registry and matching; `head.py` `<head>` and JSON-LD; `shell.py` page chrome, cards, `write()`; `pages.py` home, sections, stories, originals, 404; `local.py` `/local/`, area and topic hubs, events and `.ics`; `editorial.py` about, editorial policy, corrections, contact, privacy, terms, submit; `llm_layer.py` `/llm-info/`, `/identity/`, `/accessibility/`; `seo.py` feeds, sitemaps, robots, llms.txt, IndexNow list.
- **Offline build:** `TRACKER_BASE=tests/fixtures OUT_DIR=/tmp/site OG_STORIES=0 python scripts/build.py` (`TRACKER_BASE` may be a URL or a local directory holding `data/latest.json`, `data/manifest.json`, `data/days/*.json`; `OUT_DIR` overrides `_site/`; `OG_STORIES` caps how many story share cards are drawn).
- **Tests:** `python -m pytest tests/ -q` (offline smoke build from the fixture); `python scripts/check_llm_layer.py _site` checks the LLM layer.
- `content/press-releases/*.md`: original items (front matter above). **Do not edit article text without editorial approval.** `content/corrections.yaml` (optional) is a list of `{date, url, title, note}` shown on `/corrections/`.
- `content/images.yaml`: photo registry (with `buckets` and headline `keywords` used to match photos to stories) and category fallback images, with attribution.
- `scripts/brand.py`: branded category cards and share cards (Pillow). Brand assets in `static/img/`: `logo-full` (full-colour horizontal logo, PNG/WebP, used in JSON-LD), `logo-reverse` (knockout version for dark backgrounds), `logo-mark` (square mark for icons and avatars), plus `logo-header` and `brand/cat-*.webp` category cards. See `/identity/`.
- `static/`: CSS, logos, favicons, fonts, images, copied verbatim into `_site/`.
- `.github/workflows/build.yml`: build, test, deploy to Pages, then ping IndexNow with changed URLs. `pr-from-issue.yml` turns a press-release issue into a pull request.
