# Ground Level News

Live: https://groundlevelnews.com

An independent static news site for the Colorado River region of Arizona and Nevada, built with GitHub Actions and GitHub Pages. The generator (`scripts/build.py` + the `scripts/gln/` package) pulls headlines from the news-tracker data feed (`TRACKER_BASE`; `data/latest.json`, `data/manifest.json`, `data/days/*.json`), filters and categorises them, and renders the homepage, section pages, local and topic hubs, story pages (a summary plus a link to the original publisher), original local items (press releases, briefs, reports), editorial/trust pages, RSS/Atom feeds, sitemaps and the LLM layer.

`build.yml` rebuilds the site on a cron around the clock (GitHub throttles short intervals, so the real cadence is a few times a day; the footer `Updated` timestamp is the truth). `keepalive.yml` dispatches a rebuild if the cron skips.

## Requirements and local build

**Python 3.12 or newer is required** (the generator uses PEP 701 f-strings).

```sh
pip install -r requirements.txt
python scripts/build.py            # live tracker feed → _site/
```

Offline build from the saved fixture (no network, ~20 s):

```sh
TRACKER_BASE=tests/fixtures OUT_DIR=/tmp/site OG_STORIES=0 python scripts/build.py
```

- `TRACKER_BASE`: URL of the news-tracker Pages site, or a local directory holding `data/latest.json`, `data/manifest.json` and `data/days/*.json`.
- `OUT_DIR`: output directory (default `_site/`).
- `OG_STORIES`: how many aggregated stories get a generated share card (default 60; `0` skips them).
- `SITE_URL`, `CONTACT_EMAIL`: override the canonical origin and the newsroom address.

Tests: `python -m pytest tests/ -q` runs an offline smoke build and the LLM-layer checker (`python scripts/check_llm_layer.py _site`).

## Package layout (`scripts/gln/`)

| Module | Responsibility |
|---|---|
| `config.py` | Constants, environment, blocked-name regex |
| `text.py` | Escaping, cleaning, slugs, dates |
| `feed.py` | Tracker JSON loading, press-release loading and Markdown sanitising |
| `taxonomy.py` | `REGIONS`, `detect_regions`, `area_to_region`, categorisation, quality, publisher table, ranking |
| `images.py` | Photo registry (`content/images.yaml`), keyword matching, `<img>` markup |
| `head.py` | `<head>`, Open Graph, JSON-LD graph |
| `shell.py` | Page chrome, cards, grids, share cards, `write()` |
| `pages.py` | Homepage, sections, stories, original items, 404 |
| `local.py` | `/local/`, `/local/<area>/`, `/topic/<key>/`, events and `.ics` files |
| `editorial.py` | `/about/`, `/editorial-policy/`, `/corrections/`, `/contact/`, `/privacy/`, `/terms/`, `/submit/` (HTML + `.md` twins) |
| `llm_layer.py` | `/llm-info/`, `/identity/`, `/accessibility/` |
| `seo.py` | RSS/Atom, sitemaps, news sitemap, robots.txt, llms.txt, agents.txt, IndexNow list |

Dependency direction: `config → text → feed/images/taxonomy → head → shell → pages/local/editorial/llm_layer/seo → build.py`. `build.build_context()` creates `c.urls`; every renderer appends `{loc, kind, lastmod, title, image, ts, summary, area, cat}` for each indexable page, and `seo.render_feeds(c)` builds the sitemaps and feeds from that registry.

## Pages

- Sections: `/category/<us|world|politics|business|markets|tech|science|sports|local>/`; `/category/local/` mirrors the `/local/` hub.
- Local hubs: `/local/` and `/local/<area>/` (`bullhead-city`, `laughlin`, `mohave-valley`, `lake-havasu-city`, `kingman`, `mohave-county`, `clark-county`, `las-vegas`, `mesquite`, `boulder-city`, `lake-mead`, `colorado-river`, `needles`, `nevada`, `arizona`), each with a `feed.xml`.
- Topic hubs: `/topic/<energy|realestate|smallbiz|fed|ai|cannabis|golf|media>/`.
- Originals: `/press-releases/`, `/press-releases/<slug>/` (+ `.md`), `/press-releases/feed.xml`.
- Editorial and trust pages: `/about/`, `/editorial-policy/`, `/corrections/`, `/contact/`, `/privacy/`, `/terms/`, `/submit/`, `/accessibility/`, `/identity/`, each with a Markdown twin.
- Aggregated stories: `/story/<slug>/` (+ `.md`). **These are `noindex,follow`** and are left out of `sitemap.xml` and `news-sitemap.xml`; they stay in RSS/Atom for readers and agents. Originals, hubs, sections and static pages are indexable; the news sitemap lists originals from the last 48 hours only.

## Publishing original items

Files live in `content/press-releases/YYYY-MM-DD-slug.md`. The body is Markdown (sanitised at build time: no scripts or inline HTML). **Never edit a published body without editorial approval.**

```markdown
---
title: "Headline"
date: 2026-10-13
kind: press-release                      # press-release | brief | report
published: "2026-10-13T09:00:00-07:00"   # optional; defaults to date + T12:00:00-07:00
updated: "2026-10-14T08:00:00-07:00"     # optional
company: "Acme Co"
contact: "Jane Doe, jane@acme.com"        # public media contact
summary: "One or two sentences."
area: "Bullhead City"                    # optional; maps to /local/<area>/
source_url: "https://..."                # optional; expected for briefs
source_name: "City of X"                 # optional
author: "Name"                           # optional; briefs and reports
tags: [events]                           # optional
event_start: "2026-10-17T10:00:00-07:00" # optional event fields
event_end: "2026-10-17T14:00:00-07:00"
event_all_day: true                      # with a T00:00:00 start when only the date is known
venue: "Station 91"
address: "2230 Joy Lane, Fort Mohave, AZ"
event_url: "https://..."
image: /img/photos/x.webp                # optional, with image_alt/credit/license/source/label
---
Body in Markdown.
```

**Kinds.** `press-release`: text issued by the named organization; rendered with the organization as byline and a "Media contact" line. `brief`: rewritten by Ground Level News staff from cited public reporting (newspaper article, agency notice); rendered with the byline "Ground Level News staff", a Source link and no media contact. `report`: original reporting with a named `author`. Rule of thumb used for the existing files: if `source_url` is on the issuing organization's own site, it is a press release; if it is a newspaper or another third party, it is a brief.

**Event fields** feed the "Happening this week" lists, the `.ics` downloads and the `Event` JSON-LD. Use ISO 8601 with the region's offset (`-07:00`). For an all-day or multi-day event, set `event_start` (and `event_end`) to the dates at `T00:00:00-07:00` and `event_all_day: true`; `event_end` is the last day.

`2026-01-01-example-template.md` is a labelled example (`example: true`): it is rendered `noindex` for `/submit/` to link to and excluded from the index, feeds, sitemaps and `llms.txt`.

Ways to add a file: commit to `main` or open a PR; email news@groundlevelnews.com (see `/submit/`); or use the "Submit a press release" GitHub issue form, which `pr-from-issue.yml` turns into a pull request after validating the date (`YYYY-MM-DD`) and slug.

**Corrections.** `content/corrections.yaml` (optional) is a list of `{date, url, title, note}` entries rendered on `/corrections/`; without it the page says no corrections have been issued.

## Images and brand assets

`content/images.yaml` is the photo registry. Each photo has `buckets` (sections it suits) and `keywords`; the build gives a story the photo whose keywords best match its headline, otherwise a branded card. Only public-domain or openly licensed photos, with credit, license and source filled in. Illustrations are generated with the open-source Z-Image-Turbo model, labelled "Illustration", and never depict real people or the actual event.

Brand assets in `static/img/`: `logo-full.{png,webp}` (full-colour horizontal logo; the JSON-LD organization logo), `logo-reverse.{png,webp}` (knockout version for dark backgrounds), `logo-mark.{png,webp}` (square mark for icons and avatars), `logo-header*.webp` (header sizes) and `brand/cat-<section>.webp` category cards. `python scripts/brand.py` regenerates the cards, share cards and `static/og.png`. The `/identity/` page documents colours, fonts and downloads.

## Contact

`CONTACT_EMAIL` (default `news@groundlevelnews.com`) is shown on `/about/`, `/contact/`, `/submit/` and in `security.txt`.
