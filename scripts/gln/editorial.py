"""Editorial and trust pages: /about/, /editorial-policy/, /corrections/, /contact/, /privacy/, /terms/ and /submit/.
Each page is written from Markdown (HTML via shell.page plus a .md twin) and registered in c.urls. Owned by editorial."""
import inspect, sys, pathlib, yaml, markdown
from .config import ROOT, OUT, SITE, NAME, TAG, CONTACT, NOW
from .text import esc, clean
from .shell import page, write
try:
    from .head import crumbs, ldj
except Exception:  # head.py is owned by SEO and may change shape
    crumbs = ldj = None

TODAY = NOW.strftime("%Y-%m-%d")
LASTMOD = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
TEMPLATE_MD = "/press-releases/2026-01-01-example-template.md"

# Coverage areas shown on /about/ (keys are /local/<key>/ hubs). taxonomy.REGIONS overrides the labels when present.
AREAS = [("bullhead-city", "Bullhead City, Arizona"), ("laughlin", "Laughlin, Nevada"), ("mohave-valley", "Mohave Valley and Fort Mohave, Arizona"),
         ("lake-havasu-city", "Lake Havasu City, Arizona"), ("kingman", "Kingman, Arizona"), ("mohave-county", "Mohave County, Arizona"),
         ("clark-county", "Clark County, Nevada"), ("mesquite", "Mesquite, Nevada"), ("boulder-city", "Boulder City, Nevada"), ("lake-mead", "Lake Mead and Hoover Dam")]


def _areas():
    try:
        from .taxonomy import REGIONS
    except Exception:
        return AREAS
    out = []
    for key, label in AREAS:
        r = REGIONS.get(key) if hasattr(REGIONS, "get") else None
        if r and r.get("name"):
            label = r["name"] + (f", {r['state']}" if r.get("state") and r.get("kind") != "area" else "")
        out.append((key, label))
    return out


def _mailto(subject, body=None):
    from urllib.parse import quote
    return f"mailto:{CONTACT}?subject={quote(subject)}" + (f"&body={quote(body)}" if body else "")


def _register(c, path, title, desc):
    urls = getattr(c, "urls", None)
    if urls is None: return
    urls.append({"loc": path, "kind": "page", "lastmod": LASTMOD, "title": title, "image": None,
                 "ts": int(NOW.timestamp()), "summary": desc, "area": None, "cat": None})


def _page(c, path, title, desc, md, crumb=None):
    """HTML page rendered from Markdown (+ breadcrumbs JSON-LD when head provides it), plus its .md twin."""
    desc = clean(desc, 155)
    html_body = markdown.markdown(md, extensions=["extra"])
    rel = path.strip("/")
    (OUT / rel).parent.mkdir(parents=True, exist_ok=True)
    (OUT / (rel + ".md")).write_text(f"---\ntitle: \"{title}\"\nupdated: {TODAY}\ncanonical: {SITE}{path}\n---\n\n" + md, encoding="utf-8")
    params = inspect.signature(page).parameters
    kw = {"desc": desc, "path": path, "md": f"/{rel}.md"}
    if "ticker" in params: kw["ticker"] = getattr(c, "ticker", "")
    if crumbs and ldj:
        node = crumbs(("Home", "/"), (crumb or title, path))
        if "ld" in params: kw["ld"] = [node]
        else: kw["extra_head"] = ldj(node)
    write(path, page(title, f'<article class="story"><div class="prose">{html_body}</div></article>', **kw))
    _register(c, path, title, desc)


def _sources(items):
    srcs = {}
    for i in items or []:
        n = (i.get("source") or "").strip()
        if n: srcs[n] = srcs.get(n, 0) + 1
    return sorted(srcs.items(), key=lambda x: (-x[1], x[0]))[:40]


def _corrections_log():
    f = ROOT / "content/corrections.yaml"
    if not f.exists(): return []
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        if isinstance(data, dict): data = data.get("corrections") or []
        return [d for d in data if isinstance(d, dict) and d.get("url") and d.get("note")]
    except Exception as e:
        print(f"WARN corrections.yaml: {e}", file=sys.stderr); return []


def render_editorial(c):
    items = getattr(c, "items", []) or []
    areas = _areas()
    area_links = "\n".join(f"- [{label}](/local/{key}/)" for key, label in areas)
    srcs = _sources(items)
    src_list = "\n".join(f"- {n} ({k})" for n, k in srcs) if srcs else "- No aggregated stories in this build."
    email = f"[{CONTACT}](mailto:{CONTACT})"

    # ---------------------------------------------------------------- /about/
    _page(c, "/about/", "About Ground Level News", f"Who runs {NAME}, how it is funded, where its news comes from and how to reach the newsroom.", f"""# About {NAME}

{NAME} is an independent, reader-focused news site for the Colorado River region of Arizona and Nevada: Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman and the rest of Mohave County, and Clark County communities such as Mesquite, Boulder City and the Lake Mead area. We publish local press releases, briefs and reports in full, and we wrap them in a front page of U.S. and world headlines gathered from publishers' public feeds, each linked to its original source.

The site is refreshed around the clock. The exact time of the current edition is the **Updated** timestamp in the footer of every page.

## Ownership and funding {{#ownership}}

{NAME} is independently owned and operated and is based in the Colorado River region. It is not part of a newspaper chain, a broadcaster or a political organization.

The site is currently self-funded by its publisher. It carries **no advertising**, **no sponsored content** and **no paid placements**. Nobody can pay to have a story, press release or brief published, promoted or removed, and we do not accept payment, gifts or favors from the people and organizations we cover. If that ever changes, this page and the [editorial policy](/editorial-policy/) will say so first.

## Masthead {{#masthead}}

- **Editor:** {NAME} staff
- **Newsroom email:** {email}
- **Corrections:** see [Corrections](/corrections/), or email {email} with "Correction" in the subject line

{NAME} is a small operation. Local briefs and reports carry the byline "{NAME} staff" or a named author; press releases carry the name of the organization that issued them. See the [editorial policy](/editorial-policy/) for how each kind of item is labelled.

## Coverage area {{#coverage}}

Our local coverage follows the river. Each area has its own hub page with the latest local items and upcoming events:

{area_links}

All local items together: [Local news](/local/).

## Where the news comes from {{#sources}}

**Local items** come from city, county and tribal governments, fire and police departments, school districts, chambers of commerce, nonprofits and businesses in the region, either as press releases they send us or as briefs our staff rewrite from their public notices and from regional newspapers' reporting. Every local item names its source and links to it.

**National and world headlines** are gathered automatically from publishers' public RSS and news feeds: wire services, national newspapers and broadcasters, trade and technology outlets, and Nevada and Arizona newsrooms. Each story page shows the headline and a short summary only and links straight to the original article. The reporting and all rights belong to that publisher; we do not copy article text. These aggregated pages are marked so that search engines index the publisher's article rather than our summary.

### Sources in today's edition {{#todays-sources}}

Publishers with headlines in the current build, with the number of items from each:

{src_list}

## Photos and illustrations {{#photos}}

Photos are public domain or openly licensed (U.S. government agencies, the Library of Congress, Creative Commons photographers) or supplied by the organization issuing a release, and each one is credited under the image with its license and source. Images labelled **"File photo"** show the place or subject in general, not the actual event. Images labelled **"Illustration"** are generated with the open-source Z-Image-Turbo model, never depict real people or the actual event, and are always labelled as such. Details are in the [editorial policy](/editorial-policy/#ai).

## Publishers: how to request removal {{#removal}}

If you publish one of the feeds we aggregate and would rather not appear on {NAME}, email {email} with the name of your publication and feed URL. We remove the feed within one business day and do not need a reason. If a single headline or summary is wrong, see [Corrections](/corrections/).

## Policies

- [Editorial policy](/editorial-policy/): how we gather, label and correct the news, including our use of AI
- [Corrections](/corrections/)
- [Contact](/contact/)
- [Privacy](/privacy/)
- [Terms of use](/terms/)
- [Accessibility](/accessibility/)
- [Brand and logo](/identity/)
- For AI assistants and developers: [LLM info](/llm-info/), [llms.txt](/llms.txt), [agents.txt](/agents.txt)
""", crumb="About")

    # ------------------------------------------------------ /editorial-policy/
    _page(c, "/editorial-policy/", "Editorial Policy", f"How {NAME} gathers, labels, edits and corrects the news, including attribution rules and how AI is and is not used.", f"""# Editorial policy

This page explains how {NAME} gathers and labels what it publishes, what it will not do, and how to hold it to account. It applies to everything on the site. Questions and complaints: [{CONTACT}](mailto:{CONTACT}).

## Aggregation method and attribution {{#aggregation}}

- National and world headlines are collected automatically from publishers' public RSS and news feeds. We publish the **headline, the publisher's name and a short summary** from the feed, with a prominent link to the original article. We do not reproduce article text, and we do not rewrite or editorialize aggregated headlines.
- Every aggregated story page names the publisher as the author of the reporting, links to it as the original and marks the page `noindex` so that search engines send readers to the publisher, not to us.
- Feed boilerplate is removed; headlines are otherwise shown as the publisher wrote them. Wire-service filings, non-English items, duplicates and low-quality sources are filtered out automatically.
- Publishers can ask to be removed from the site at any time: see [About › Removal](/about/#removal).

## Kinds of local content and how each is labelled {{#kinds}}

Local items appear under **Local** and at `/press-releases/`. Each one carries a kicker that tells you what it is:

| Kicker | What it is | Byline and source line |
|---|---|---|
| **Press release** | The text of an announcement issued by a government agency, business, nonprofit or other organization, published in full with light copy-editing. | Byline is the issuing organization; a "Media contact" line gives its public contact; a "Source" link goes to the original notice when there is one. |
| **Brief** | A short news item **rewritten by {NAME} staff** from cited public reporting or public records: a newspaper article, an agency notice, a meeting agenda. | Byline "{NAME} staff"; a "Source" line links to the reporting it is based on; it carries no "Media contact" line, because the organization did not issue it. |
| **Report** | Original reporting by {NAME}: interviews, documents and observations gathered by us. | A named author, or "{NAME} staff"; sources are named in the text; any relationship between the publisher and the subject is disclosed in the piece. |

Press releases are published in the issuer's words. Their Markdown is sanitised before publishing: scripts, inline HTML, forms and tracking links are removed and only plain formatting (headings, lists, links, emphasis, tables and images from this site) is kept. We may trim promotional language, fix typos and add context in a clearly separated note, but we do not change the substance of a release. An example item used to show the format is labelled "Example" and excluded from feeds and search indexes.

## Use of AI {{#ai}}

- **Illustrations.** Some local items carry an illustration generated with the open-source Z-Image-Turbo model. Every one is labelled **"Illustration"** in the caption and in the image metadata. Illustrations never depict real people and never show the actual event; they are generic scenes (a desert fire station, a main street). We prefer a real, credited photo whenever one is available, and we ask organizations to send their own photos.
- **Briefs** are rewritten by staff from cited public reporting and link to the source. Staff may use software, including AI tools, to help draft, shorten or check a brief, but a person reads the source, checks the facts against it and is responsible for every brief we publish.
- **No AI-written content is presented as original reporting.** Anything labelled "Report" is written by a person from material gathered by {NAME}.
- Aggregated headlines and summaries are the publisher's own text, selected and filtered by software, and are labelled as the publisher's.
- Photo matching (which stock photo appears on an aggregated headline) is automated; those photos are labelled "File photo" and do not show the event.

## Ethics {{#ethics}}

- **No pay-to-publish.** Nobody can pay for coverage, placement, removal or a favorable rewrite. We carry no advertising or sponsored content. If that changes, paid material will be labelled as such and this policy updated first.
- **Disclosure of relationships.** When a report concerns a person or organization with a business, family or financial relationship to {NAME} or its staff, the piece says so.
- **Public figures and private individuals.** We name public officials, organizations and people who speak to us on the record. We do not publish photos of private individuals without consent, and we do not publish personal contact details beyond the public media contact an organization supplies.
- **Independence.** Editorial decisions are made by {NAME} staff alone. Governments, advertisers (we have none), sources and the subjects of coverage have no say in what is published.

## Diversity and fairness {{#diversity}}

The region we cover is home to tribal nations, retirees, seasonal workers, cross-border commuters and small-town residents on both sides of the river. We try to publish notices from all of them, in all of our coverage areas, and to label opinion, promotion and fact clearly so readers can judge for themselves. If a community or point of view is missing, tell us: [{CONTACT}](mailto:{CONTACT}).

## Corrections and updates {{#corrections}}

- We correct errors of fact promptly and visibly. A corrected item carries a note saying what was wrong and when it was fixed, and the correction is listed on the [Corrections](/corrections/) page.
- Updates that add information without fixing an error are marked "Updated" with a timestamp.
- A press release that its issuer later withdraws or amends is updated or removed at the issuer's request, with a note.
- Aggregated headlines come from the publisher's feed; if a publisher corrects a story, the corrected headline replaces the old one on the next refresh. Errors in our summary or source attribution are fixed by us.
- How to request a correction: [Corrections](/corrections/).

## Changes to this policy

This page is updated as the site grows. The date of the current edition is the Updated timestamp in the footer. Earlier versions are in the site's public source-code history.
""", crumb="Editorial policy")

    # ------------------------------------------------------------ /corrections/
    log = _corrections_log()
    log_md = "\n".join(f"- **{esc(str(d.get('date') or ''))}** · [{esc(str(d.get('title') or d['url']))}]({esc(d['url'])}): {esc(d['note'])}" for d in log) if log else "No corrections have been issued yet."
    _page(c, "/corrections/", "Corrections", f"How to report an error on {NAME}, what gets corrected or updated, and the public log of corrections.", f"""# Corrections

We would rather be right than first. If you see an error on {NAME}, tell us and we will fix it quickly and say what we fixed.

## How to request a correction

Email [{CONTACT}]({_mailto("Correction request", "Page URL:\n\nWhat is wrong:\n\nWhat it should say, with a source if you have one:\n\nYour name and how to reach you (optional):\n")}) with **"Correction"** in the subject line and:

1. the address (URL) of the page,
2. what is wrong, and
3. what it should say, with a source we can check if you have one.

We reply to every request, usually within one business day, and we never publish your name or email without asking.

## What gets corrected, and what gets updated

- **Corrected:** errors of fact in anything we wrote: a brief, a report, a headline we edited, a caption, a date, a name, a source attribution. The item is fixed and carries a note saying what was wrong and when it was corrected. Significant corrections are listed below.
- **Updated:** new information that does not fix an error (a time changes, an event sells out, a quote is added). The item is marked "Updated" with a timestamp and no correction note.
- **Press releases** are the issuer's words. If the issuer tells us something in its release was wrong, we add a note and, at its request, amend or withdraw the release.
- **Aggregated headlines** are the publisher's own text. If a publisher's headline or summary is wrong, contact that publisher; if our page misattributes the source or mangles the summary, contact us and we will fix our page.
- **Typos and formatting** are fixed silently when they do not change meaning.

## Removal requests

We do not remove accurate items because the subject prefers not to be covered. We do remove or amend items at the request of the publisher or issuer, and we remove anything that violates a person's privacy or safety. See also [About › Removal](/about/#removal).

## Corrections log {{#log}}

{log_md}
""", crumb="Corrections")

    # ---------------------------------------------------------------- /contact/
    _page(c, "/contact/", "Contact", f"How to reach {NAME}: news tips, press releases, corrections, partnerships and security reports.", f"""# Contact {NAME}

Everything reaches a person, usually within one business day. There is no form on this site; use the email links below (each opens a message with the right subject line) or write to {email} directly.

## News tips {{#tips}}

Something happening in Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mesquite, Boulder City or anywhere along the river? [Send a tip]({_mailto("News tip", "What happened, where and when:\n\nHow you know (saw it, documents, a link):\n\nHow we can reach you (optional):\n")}). Tell us what you saw, where and when, and how we can confirm it. You can stay anonymous; we never publish a tipster's name without permission.

## Press releases and event notices {{#press}}

Agencies, businesses, nonprofits and community groups can send releases free of charge. The quickest route is the [submission page](/submit/), which explains what to include. Or [email a release]({_mailto("Press release submission")}) with the fields listed there.

## Corrections {{#corrections}}

Spotted an error? [Request a correction]({_mailto("Correction request")}) or read the [corrections policy](/corrections/) first.

## Partnerships and publishers {{#partners}}

Regional newsrooms, agencies and community organizations that want to syndicate, link, share a feed or be removed from aggregation: [partnerships]({_mailto("Partnership inquiry")}). We do not sell advertising or sponsored content.

## Security {{#security}}

To report a security issue with this website, email [security]({_mailto("Security report")}) or follow [/.well-known/security.txt](/.well-known/security.txt). We acknowledge reports within two business days.

## Everything else

{email}. We are based in the Colorado River region of Arizona and Nevada and work on Mountain/Pacific time.

- [About](/about/) · [Editorial policy](/editorial-policy/) · [Corrections](/corrections/) · [Privacy](/privacy/) · [Terms](/terms/)
""", crumb="Contact")

    # ---------------------------------------------------------------- /privacy/
    _page(c, "/privacy/", "Privacy Policy", f"What {NAME} does and does not collect: a static site with no cookies, no analytics and no accounts, hosted on GitHub Pages.", f"""# Privacy policy

Short version: {NAME} is a static website. It sets **no cookies**, runs **no analytics or tracking scripts**, has **no accounts, logins or comment system**, and shows **no advertising**. We do not know who you are when you read it.

## What the site itself collects

Nothing. The pages are plain HTML files. There are no cookies, no local storage used for tracking, no third-party scripts, no embedded social widgets and no fonts loaded from other companies (the fonts are served from this site). The only scripts on the page are small ones that open the menu, show relative times and expand "View more" lists; none of them sends data anywhere.

## Hosting and server logs

The site is hosted by **GitHub Pages**. Like any web host, GitHub's servers receive your IP address, the page you requested, the time, and your browser's user-agent string, and may keep those in server logs for security and operations. {NAME} does not have access to visitor-level logs. GitHub's handling of this data is described in the [GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

## External links

Aggregated stories link to the publishers that wrote them, and local items link to the agencies and organizations they come from. Those sites have their own privacy policies, cookies and advertising.

## Email

If you email us (a news tip, a press release, a correction, a question), we receive your email address, your name if you include it, and whatever you send. We use it only to answer you and to publish what you asked us to publish. We do not add you to any list, share your address with anyone or use it for marketing. Press releases are published with the **public media contact the issuer supplies**; we do not publish the personal contact details of the person who sent it unless they are that contact. Tipsters are never named without permission. We delete correspondence that is no longer needed.

## Feeds, sitemaps and machine readers

Our RSS and Atom feeds, sitemaps and `llms.txt` files are public and contain only published content. Feed readers, search engines and AI crawlers that fetch them are subject to the same hosting logs described above and to our [agent policy](/agents.txt).

## Children

The site is a general-audience news site and does not knowingly collect information from anyone, including children.

## Changes

If we ever add analytics, newsletters, comments or anything else that touches personal data, this page will say so before it goes live, and the Updated date below will change.

## Contact

Privacy questions: [{CONTACT}]({_mailto("Privacy question")}). See also [Terms of use](/terms/) and [Contact](/contact/).

Updated {TODAY}.
""", crumb="Privacy")

    # ------------------------------------------------------------------ /terms/
    _page(c, "/terms/", "Terms of Use", f"Plain-language terms for using {NAME}: who owns what, no warranty, acceptable use and how the terms change.", f"""# Terms of use

Plain language, kept short. By using {NAME} ({SITE}) you agree to these terms.

## Who owns what

- **Aggregated stories** (`/story/…`) belong to the publishers who wrote them. We show the headline, publisher name and a short summary from their public feed, with a link to the original. Read, quote and share them under that publisher's terms, not ours.
- **Press releases** belong to the organizations that issued them. By sending us a release you confirm you have the right to publish it and you grant {NAME} a non-exclusive, perpetual licence to publish, edit for length and style, and distribute it, including in our feeds and Markdown versions.
- **Briefs, reports, summaries written by us, page design and code** are © {NOW.year} {NAME}. You may quote them with attribution and a link.
- **Photos and illustrations** carry their own credit and licence under each image; follow that licence. Illustrations labelled as such are generated and may be reused with the credit shown.
- Feeds, sitemaps and `llms.txt` files are provided for personal, research and indexing use, including by AI systems, under our [agent policy](/agents.txt). Citation is required.

## No warranty

We work hard to be accurate and we correct errors, but the site is provided **"as is"**, without warranty of any kind. Headlines are refreshed automatically from third-party feeds and may be out of date, incomplete or wrong; event details can change. Check with the original publisher or organizer before relying on anything, especially times, places and prices. To the extent permitted by law, {NAME} is not liable for any loss arising from use of the site or of the sites it links to.

## Acceptable use

Do not use the site to break the law, to harass anyone, to republish our content while stripping attribution, or to overload the servers with abusive crawling (reasonable automated access, including by search engines and AI agents, is welcome; see [robots.txt](/robots.txt)). Do not send us material you do not have the right to publish, or anything defamatory, deceptive or that invades a person's privacy.

## Submissions

Material you send for publication must be truthful and yours to send. We may decline, edit, label or remove anything we publish; see the [editorial policy](/editorial-policy/). We do not pay for submissions and do not charge for publishing them.

## Links

Links to other sites are provided for your convenience. We do not control them and are not responsible for their content or practices.

## Changes

We may change these terms by posting a new version here; the date below is the current edition's. Continued use after a change means you accept it.

## Governing law and contact

These terms are governed by the laws of the State of Arizona, United States. Questions: [{CONTACT}](mailto:{CONTACT}). See also [Privacy](/privacy/) and [Contact](/contact/).

Updated {TODAY}.
""", crumb="Terms")

    # ----------------------------------------------------------------- /submit/
    email_body = ("Kind (press release / event notice / community announcement):\nTitle:\nDate (YYYY-MM-DD):\nOrganization:\nArea (city or community):\n"
                  "Public media contact (name, email or phone):\nSummary (1-2 sentences):\nSource URL (optional):\n\n"
                  "Event (if any): start date and time / end / venue / street address / event web page:\n\nBody:\n\n\nPhoto (optional, attach): who took it, licence, who is in it:\n")
    _page(c, "/submit/", "Submit News", f"Send {NAME} a press release, event notice or community announcement for free. What we publish, turnaround, photo rules and the template.", f"""# Submit news

{NAME} publishes local announcements from the Colorado River region free of charge. An editor reads every submission before it goes live; nothing is published automatically.

## What we publish

- **Press releases** from government agencies, police and fire departments, school districts, utilities, businesses, nonprofits, churches, clubs and tribal organizations in or about our [coverage area](/about/#coverage).
- **Event notices:** open houses, concerts, fundraisers, markets, meetings, elections and early-voting schedules, road work, anything with a date, a time and a place.
- **Community announcements:** grants, awards, hires, openings, closures, service changes, scam warnings, calls for volunteers.

We do not publish advertising, product promotion without a local news angle, political attack material, or anything about private individuals without their consent. See the [editorial policy](/editorial-policy/).

## The three kinds of local item

Everything local carries a kicker so readers know what they are reading:

- **Press release**: your announcement in your words, under your organization's name, with your public media contact.
- **Brief**: a short item our staff rewrite from public reporting or records, with a link to the source. If you would rather we summarise your long notice than run it in full, say so.
- **Report**: original reporting by {NAME}. You cannot submit a report, but you can [send us a tip](/contact/#tips).

## Turnaround

Usually **within one business day**, often the same day. Time-sensitive items (a road closure tonight, an event tomorrow) should say so in the subject line. We will email you when it is live or if we have questions.

## What we edit

We copy-edit for spelling, grammar, AP-style dates and times, and length; we may trim marketing language and add a sentence of context in a clearly separated note. We do not change the facts or substance of your release. Formatting is reduced to plain headings, lists, links and emphasis; scripts and inline HTML are removed. If we think a release needs a correction before publishing, we will ask you.

## Photos

- Send only photos **you own** or that are **openly licensed** (public domain, Creative Commons), and tell us the photographer, the licence and where it came from. We print that credit under the image.
- **No photos of private individuals** without their consent, and no photos of children unless a parent or guardian consents.
- Minimum 1200 pixels wide, JPEG or PNG. Logos are fine. We do not use photos lifted from other websites.
- If you send no photo, we use a credited file photo of the area or, failing that, a labelled illustration that does not depict the event.

## How to send it

### By email

[Email your release]({_mailto("Press release submission", email_body)}) to {email}. The link opens a message with these fields; paste your text in:

`Kind`, `Title`, `Date`, `Organization`, `Area`, `Contact`, `Summary`, `Source URL` (optional), `Event` details (optional), `Body`, and a photo attachment (optional).

### As a file

If you are comfortable with Markdown, you can write the item yourself using the [Markdown template]({TEMPLATE_MD}) and email it, or open a pull request on the site's repository adding `content/press-releases/YYYY-MM-DD-slug.md`. The header block looks like this:

```yaml
---
title: "Headline that leads with the place or agency"
date: 2026-10-13
kind: press-release            # press-release | brief | report (default press-release)
published: "2026-10-13T09:00:00-07:00"   # optional; defaults to noon local on `date`
company: "Organization issuing it"
area: "Bullhead City"
contact: "Public media contact: name, email or phone"
summary: "One or two sentences."
source_url: "https://..."      # optional; required for briefs
source_name: "Publisher or agency name"   # optional
author: "Name"                 # optional; for briefs and reports
tags: [events, fire]           # optional
# Event details (optional; shown in "Happening this week" and as calendar files)
event_start: "2026-10-17T10:00:00-07:00"
event_end: "2026-10-17T14:00:00-07:00"
event_all_day: false
venue: "Station 91"
address: "2230 Joy Lane, Fort Mohave, AZ"
event_url: "https://..."
# Image (optional; falls back to a credited area photo)
image: /img/photos/example.webp
image_alt: "Describe the image"
image_credit: "Photographer / Organization"
image_license: "CC BY-SA 4.0"
image_source: "https://..."
image_label: "File photo"      # or "Illustration"
---
Body in Markdown…
```

Times use the region's UTC offset (`-07:00`). Dates are the year 2026 unless you say otherwise.

## Questions

[{CONTACT}](mailto:{CONTACT}) or the [contact page](/contact/). There is no charge, now or later, for anything on this page.
""", crumb="Submit news")
