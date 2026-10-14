# Ground Level News

Live: https://groundlevelnews.com (fallback: https://axia-enterprises-dev.github.io/ground-level-news/)

This is a free static news site built with GitHub Actions and GitHub Pages. `scripts/build.py` pulls headlines from the public [news-tracker](https://github.com/AXIA-Enterprises-DEV/news-tracker) data (`data/latest.json`, `data/manifest.json`, `data/days/*.json`), filters out SEC filings, and renders the homepage, category pages, story pages (a summary plus a link to the original source), press releases, RSS (`/rss.xml`), and a sitemap.

The site rebuilds every 15 minutes (`build.yml`). `keepalive.yml` dispatches a rebuild if the cron skips.

Local build: `pip install -r requirements.txt && python scripts/build.py`. Output goes to `_site/`.

## Publishing press releases

**Option A: add a Markdown file.** Create `content/press-releases/YYYY-MM-DD-slug.md`:

```markdown
---
title: "Headline"
date: 2026-10-13
company: Acme Co
contact: "Jane Doe, jane@acme.com"
summary: "One or two sentences."
area: Bullhead City        # optional
source_url: https://...    # optional
source_name: City of X     # optional
---
Body in Markdown.
```

Commit it to `main`, or open a PR. The site updates within a few minutes of the merge.

**Option B: GitHub issue.** Go to Issues → New → "Submit a press release" and fill in the form. A workflow opens a PR with the file. Review it and merge to publish.

`2026-01-01-example-template.md` is a labeled example. Set `example: true` to mark a release as a sample.
