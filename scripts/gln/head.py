"""Everything inside <head>: title, meta, Open Graph/Twitter, icons, feed links and ONE JSON-LD @graph. Owned by SEO.
Renderers build schema.org nodes with the helpers below (webpage_node, article_node, story_node, image_node,
collection_node, event_node, crumbs) and pass them as shell.page(ld=[...]); head() merges them with the
NewsMediaOrganization and WebSite nodes. Legacy ldj() scripts found in extra_head are folded into the same graph."""
import json, re, datetime as dt
from .config import ROOT, OUT, SITE, NAME, TAG, CONTACT, NOW, CAT_NAME
from .text import esc, clean
from .images import dims
try:
    from .taxonomy import REGIONS          # taxonomy agent; optional until it lands
except Exception:
    REGIONS = {}

ROBOTS = "index,follow,max-image-preview:large,max-snippet:-1,max-video-preview:-1"
NOINDEX = "noindex,follow,max-image-preview:large"
HOME_TITLE = f"Bullhead City, Laughlin & Colorado River News | {NAME}"
HOME_DESC = ("Local news and press releases for Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, "
             "Mesquite and Boulder City, plus U.S. and world headlines, refreshed around the clock.")
AZ = dt.timezone(dt.timedelta(hours=-7))   # Arizona (no DST): the newsroom's dateline time zone
ORG_ID, SITE_ID = SITE + "/#org", SITE + "/#website"
BUILD_ISO = NOW.replace(microsecond=0).isoformat()   # build time, RFC 3339 without microseconds
KIND_LABEL = {"press-release": "Press release", "brief": "Brief", "report": "Report"}
WD = "https://www.wikidata.org/wiki/"
# Coverage area: key -> (name, state, schema type, Wikidata id). Ids verified against Wikidata on 2026-10-18
# (the audit's indicative ids were wrong). taxonomy.REGIONS overrides this table when present.
AREAS = {"bullhead-city": ("Bullhead City", "AZ", "City", "Q79432"), "laughlin": ("Laughlin", "NV", "Place", "Q594154"),
         "mohave-valley": ("Mohave Valley", "AZ", "Place", "Q615832"), "fort-mohave": ("Fort Mohave", "AZ", "Place", "Q5471708"),
         "lake-havasu-city": ("Lake Havasu City", "AZ", "City", "Q79435"), "kingman": ("Kingman", "AZ", "City", "Q79733"),
         "mohave-county": ("Mohave County", "AZ", "AdministrativeArea", "Q58696"), "clark-county": ("Clark County", "NV", "AdministrativeArea", "Q108403"),
         "las-vegas": ("Las Vegas", "NV", "City", "Q23768"), "mesquite": ("Mesquite", "NV", "City", "Q991218"),
         "boulder-city": ("Boulder City", "NV", "City", "Q858801"), "lake-mead": ("Lake Mead", "NV", "Place", "Q654515"),
         "colorado-river": ("Colorado River", "", "Place", "Q1265"), "needles": ("Needles", "CA", "City", "Q846591"),
         "nevada": ("Nevada", "", "State", "Q1227"), "arizona": ("Arizona", "", "State", "Q816")}
STATE = {"AZ": "Arizona", "NV": "Nevada", "CA": "California"}
_KIND_TYPE = {"city": "City", "county": "AdministrativeArea", "area": "Place", "state": "State", "river": "Place"}

def place_node(key):
    """schema.org Place for a region key (taxonomy.REGIONS first, then the static AREAS table); None if unknown."""
    r = (REGIONS or {}).get(key)
    if r:
        st = STATE.get(r.get("state") or "", r.get("state") or "")
        n = {"@type": _KIND_TYPE.get(r.get("kind"), "Place"), "name": f"{r['name']}, {st}" if st and r.get("kind") != "state" else r["name"]}
        if r.get("wikidata"): n["sameAs"] = WD + str(r["wikidata"]).rsplit("/", 1)[-1]
        return n
    a = AREAS.get(key)
    if not a: return None
    name, st, typ, q = a
    n = {"@type": typ, "name": f"{name}, {STATE[st]}" if st else name}
    if q: n["sameAs"] = WD + q
    return n

ORG = {"@type": "NewsMediaOrganization", "@id": ORG_ID, "name": NAME, "alternateName": "GLN", "slogan": TAG, "url": SITE + "/",
       "logo": {"@type": "ImageObject", "@id": SITE + "/#logo", "url": SITE + "/img/logo-full.png", "contentUrl": SITE + "/img/logo-full.png", "width": 1200, "height": 656, "caption": NAME},
       "image": {"@id": SITE + "/#logo"}, "foundingDate": "2026-10", "email": CONTACT, "knowsLanguage": "en-US",
       "areaServed": [place_node(k) for k in ("bullhead-city", "laughlin", "mohave-valley", "fort-mohave", "lake-havasu-city", "kingman", "mohave-county", "clark-county", "mesquite", "boulder-city")],
       "contactPoint": [{"@type": "ContactPoint", "contactType": "newsroom", "email": CONTACT, "url": SITE + "/contact/", "availableLanguage": "en"},
                        {"@type": "ContactPoint", "contactType": "corrections", "email": CONTACT, "url": SITE + "/corrections/"}],
       "publishingPrinciples": SITE + "/editorial-policy/", "ethicsPolicy": SITE + "/editorial-policy/", "correctionsPolicy": SITE + "/corrections/",
       "actionableFeedbackPolicy": SITE + "/contact/", "ownershipFundingInfo": SITE + "/about/", "masthead": SITE + "/about/"}
WEBSITE = {"@type": "WebSite", "@id": SITE_ID, "url": SITE + "/", "name": NAME, "alternateName": SITE.split("//")[-1], "description": HOME_DESC,
           "publisher": {"@id": ORG_ID}, "inLanguage": "en-US"}

def _j(o): return json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
def ldj(o): return f'<script type="application/ld+json">{_j(o)}</script>'
SITE_LD = _j({"@context": "https://schema.org", "@graph": [ORG, WEBSITE]})   # back-compat
def _abs(u): return u if u.startswith("http") else SITE + u
def absimg(im): return (SITE + im["src"]) if im and im.get("src", "").startswith("/") else (im or {}).get("src")

# ---------- dates ----------
def to_iso(v, fallback_time="T12:00:00-07:00"):
    """ISO 8601 with offset from a front-matter value (date, datetime, string) or an epoch; None for empty."""
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return dt.datetime.fromtimestamp(v, dt.timezone.utc).isoformat()
    if isinstance(v, dt.datetime): return (v if v.tzinfo else v.replace(tzinfo=AZ)).isoformat()
    if isinstance(v, dt.date): return v.isoformat() + fallback_time
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s): return s + fallback_time
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00")); return (d if d.tzinfo else d.replace(tzinfo=AZ)).isoformat()
    except ValueError: return s
def published(p): return p.get("published_iso") or to_iso(p.get("published")) or to_iso(p.get("date")) or BUILD_ISO
def modified(p): return to_iso(p.get("updated")) or published(p)
def epoch(s):
    try: return int(dt.datetime.fromisoformat(str(s)).timestamp())
    except Exception: return int(NOW.timestamp())

# ---------- JSON-LD nodes ----------
def crumbs(*pairs):
    """BreadcrumbList node (@id = last crumb URL + #breadcrumb). pairs: (name, path)."""
    last = pairs[-1][1] if pairs else "/"
    return {"@type": "BreadcrumbList", "@id": _abs(last) + "#breadcrumb",
            "itemListElement": [{"@type": "ListItem", "position": n + 1, "name": clean(a, 110), "item": _abs(b)} for n, (a, b) in enumerate(pairs)]}

def webpage_node(url, name, breadcrumb_id=None, date_mod=None, kind="WebPage", desc=None, image_id=None, date_pub=None, about=None):
    url = _abs(url)
    n = {"@type": kind, "@id": url + "#webpage", "url": url, "name": clean(name, 110), "isPartOf": {"@id": SITE_ID}, "publisher": {"@id": ORG_ID}, "inLanguage": "en-US"}
    if desc: n["description"] = clean(desc, 300)
    if breadcrumb_id: n["breadcrumb"] = {"@id": breadcrumb_id if "#" in breadcrumb_id else _abs(breadcrumb_id) + "#breadcrumb"}
    if image_id: n["primaryImageOfPage"] = {"@id": image_id}
    if date_pub: n["datePublished"] = date_pub
    n["dateModified"] = date_mod or BUILD_ISO
    if about: n["about"] = about
    return n

def _author(p):
    kind = p.get("kind") or "press-release"
    if kind == "press-release":
        a = {"@type": "Organization", "name": p.get("company") or NAME}
        if p.get("company_url"): a["url"] = p["company_url"]
        return a
    if p.get("author"):
        a = {"@type": "Person", "name": p["author"]}
        if p.get("author_url"): a["url"] = p["author_url"]
        return a
    return {"@type": "Organization", "name": f"{NAME} staff"}

def article_node(p, im=None, url=None, regions=None):
    """NewsArticle (ReportageNewsArticle for kind=report) for an original: press release, brief or report."""
    url = _abs(url or f"/press-releases/{p['slug']}/")
    kind = p.get("kind") or "press-release"
    body = clean(p.get("body") or p.get("md") or "")
    pub = published(p)
    n = {"@type": "ReportageNewsArticle" if kind == "report" else "NewsArticle", "@id": url + "#article", "mainEntityOfPage": {"@id": url + "#webpage"},
         "url": url, "headline": clean(p["title"], 110), "description": clean(p.get("summary") or "", 300), "articleBody": body, "wordCount": len(body.split()),
         "articleSection": "Local", "datePublished": pub, "dateModified": modified(p), "inLanguage": "en-US", "isAccessibleForFree": True,
         "author": _author(p), "publisher": {"@id": ORG_ID}, "copyrightHolder": {"@id": ORG_ID}, "copyrightYear": int(pub[:4]),
         "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".story h1", ".summary p"]}}
    if p.get("subtitle"): n["alternativeHeadline"] = clean(p["subtitle"], 150)
    kws = [p.get("area"), p.get("company")] + [str(t) for t in (p.get("tags") or [])]
    n["keywords"] = [k for k in kws if k]
    if kind == "press-release": n["genre"] = "press release"; n["creativeWorkStatus"] = "Published"
    if p.get("source_url") and kind != "report":
        n["isBasedOn"] = p["source_url"]
        n["citation"] = [{"@type": "CreativeWork", "name": p.get("source_name") or p["source_url"], "url": p["source_url"]}]
    if im:
        n["image"] = [{"@id": url + "#primaryimage"}]
        n["thumbnailUrl"] = absimg({**im, "src": im.get("sm") or im["src"]})
    places = [x for x in (place_node(r) for r in (regions or p.get("regions") or ([p["region"]] if p.get("region") else []))) if x]
    if places: n["spatialCoverage"] = places[0]; n["mentions"] = places
    if p.get("area"):
        loc = {"@type": "Place", "name": p.get("venue") or p["area"]}
        if p.get("address"): loc["address"] = p["address"]
        n["contentLocation"] = loc
    if p.get("company"): n["about"] = [{"@type": "Organization", "name": p["company"]}]
    return n

def story_node(i, im=None, url=None):
    """NewsArticle for an aggregated story (only worth emitting when the page is indexable)."""
    url = _abs(url or f"/story/{i['slug']}/")
    cat = "local" if i.get("local") else i["cat"]
    n = {"@type": "NewsArticle", "@id": url + "#article", "mainEntityOfPage": {"@id": url + "#webpage"}, "url": url, "headline": clean(i["title"], 110),
         "description": clean(i.get("summary") or "", 300), "datePublished": to_iso(i["ts"] or None) or BUILD_ISO, "dateModified": BUILD_ISO,
         "inLanguage": "en", "isAccessibleForFree": True, "articleSection": CAT_NAME.get(cat, cat), "author": {"@type": "Organization", "name": i.get("source") or NAME},
         "publisher": {"@id": ORG_ID}, "sdPublisher": {"@id": ORG_ID}, "copyrightHolder": {"@type": "Organization", "name": i.get("source") or NAME},
         "isBasedOn": i["link"], "citation": {"@type": "CreativeWork", "url": i["link"]}}
    if im: n["image"] = {"@id": url + "#primaryimage"}
    return n

_ORG_WORDS = re.compile(r"\b(NASA|U\.S\.|US|Library|Department|Service|Bureau|Office|Agency|Commons|Congress|Administration|Army|Navy|Guard|Force|Corps|County|City|Museum|University|Government|News|Press|Flickr|Unsplash|Pexels|rawpixel)\b", re.I)
def image_node(im, page_url):
    """ImageObject per images.yaml fields: credit -> creditText/creator, license_url -> license, source -> acquireLicensePage."""
    if not im or not im.get("src"): return None
    url = _abs(page_url); src = absimg(im)
    n = {"@type": "ImageObject", "@id": url + "#primaryimage", "url": src, "contentUrl": src, "caption": clean(im.get("alt") or ""), "representativeOfPage": True}
    d = dims(im["src"]) if im["src"].startswith("/") else None
    if d: n["width"], n["height"] = d
    credit, label = (im.get("credit") or "").strip(), im.get("label") or ""
    if im.get("brand") or credit.startswith(NAME):
        ai = "generat" in credit.lower() or label == "Illustration"
        n["creditText"] = f"AI-generated illustration: {credit}" if ai and credit else credit or NAME
        n["creator"] = {"@id": ORG_ID}; n["copyrightNotice"] = f"© {NOW.year} {NAME}"
        if ai: n["description"] = "AI-generated illustration; does not depict the actual event."
    elif credit:
        who = credit.split(" / ")[0].strip()
        n["creditText"] = credit
        n["creator"] = {"@type": "Organization" if _ORG_WORDS.search(who) or len(who.split()) > 3 else "Person", "name": who}
        n["copyrightNotice"] = ", ".join(x for x in (credit, im.get("license")) if x)
    if not im.get("brand"):
        if im.get("license_url"): n["license"] = im["license_url"]
        if im.get("source"): n["acquireLicensePage"] = im["source"]
        if label == "File photo": n["description"] = "File photo; does not depict the event described."
    return n

def _list_item(it):
    if isinstance(it, (tuple, list)): return clean(it[0], 110), _abs(it[1])
    u = it.get("url") or it.get("loc") or (f"/story/{it['slug']}/" if it.get("link") else f"/press-releases/{it['slug']}/")
    return clean(it.get("title") or it.get("name") or "", 110), _abs(u)
def collection_node(url, name, items, about=None, desc=None, breadcrumb_id=None, date_mod=None):
    """CollectionPage + ItemList. items: press releases, stories, c.urls entries or (name, url) pairs.
    about: a region key, "org", or a ready node."""
    n = webpage_node(url, name, breadcrumb_id, date_mod, "CollectionPage", desc)
    els = [{"@type": "ListItem", "position": k + 1, "name": nm, "url": u} for k, (nm, u) in enumerate(_list_item(it) for it in list(items)[:50])]
    n["mainEntity"] = {"@type": "ItemList", "itemListOrder": "https://schema.org/ItemListOrderDescending", "numberOfItems": len(els), "itemListElement": els}
    if about == "org": about = {"@id": ORG_ID}
    elif isinstance(about, str): about = place_node(about)
    if about:
        n["about"] = about
        if about.get("@type") in ("City", "Place", "AdministrativeArea", "State"): n["spatialCoverage"] = about
    return n

def event_node(p, url=None):
    """Event node for an original with event_start (date or datetime); None otherwise."""
    if not p.get("event_start"): return None
    url = _abs(url or f"/press-releases/{p['slug']}/")
    n = {"@type": "Event", "@id": url + "#event", "name": clean(p.get("event_name") or p["title"], 110), "startDate": to_iso(p["event_start"], ""),
         "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
         "url": p.get("event_url") or url, "organizer": {"@type": "Organization", "name": p.get("company") or NAME}}
    if p.get("summary"): n["description"] = clean(p["summary"], 300)
    if p.get("event_end"): n["endDate"] = to_iso(p["event_end"], "")
    loc = {"@type": "Place", "name": p.get("venue") or p.get("area") or NAME}
    if p.get("address"): loc["address"] = p["address"]
    n["location"] = loc
    if p.get("image"): n["image"] = _abs(p["image"])
    if p.get("free") is True: n["isAccessibleForFree"] = True
    return n

_LD_RX = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
def graph(nodes=None):
    """One <script type=application/ld+json> with ORG + WebSite + the given nodes (deduped by @id)."""
    out, seen = [ORG, WEBSITE], {ORG_ID, SITE_ID}
    def add(n):
        if not n: return
        if "@graph" in n: [add(x) for x in n["@graph"]]; return
        n = {k: v for k, v in n.items() if k != "@context"}
        i = n.get("@id")
        if i in seen: return
        if i: seen.add(i)
        out.append(n)
    for n in nodes or []: add(n)
    return ldj({"@context": "https://schema.org", "@graph": out})

# ---------- titles ----------
def page_title(title, path="/"):
    """<title>: the keyword-bearing home title, else the headline cut at 60 chars on a word boundary + site name."""
    if path == "/" or title == NAME: return HOME_TITLE
    t = clean(title)
    if len(t) > 60: t = t[:61].rsplit(" ", 1)[0].rstrip(" ,;:-–—") + "…"
    return f"{t} | {NAME}"

_ICONS = [('<link rel="icon" href="/favicon.ico" sizes="32x32">', "favicon.ico"), ('<link rel="icon" href="/favicon.svg" type="image/svg+xml">', "favicon.svg"),
          ('<link rel="icon" href="/favicon-96.png" type="image/png" sizes="96x96">', "favicon-96.png"), ('<link rel="icon" href="/favicon-32.png" type="image/png" sizes="32x32">', "favicon-32.png"),
          ('<link rel="icon" href="/icon-192.png" type="image/png" sizes="192x192">', "icon-192.png"), ('<link rel="apple-touch-icon" href="/apple-touch-icon.png">', "apple-touch-icon.png"),
          ('<link rel="manifest" href="/site.webmanifest">', "site.webmanifest")]
ICONS = "".join(tag for tag, f in _ICONS if (ROOT / "static" / f).exists())
_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif", "svg": "image/svg+xml"}
def _og_meta(og):
    """(width, height, mime) of a share image; branded cards are always 1200x630."""
    typ = _MIME.get(og.rsplit(".", 1)[-1].lower(), "image/jpeg")
    rel = og[len(SITE):] if og.startswith(SITE) else None
    d = dims(rel) if rel and not rel.startswith("/og/") else None
    return (d or (1200, 630)) + (typ,)

def _feeds(path, feeds):
    out = [(f"{NAME} RSS", "/rss.xml", "rss"), (f"{NAME} Atom", "/feed.xml", "atom")]
    if feeds is None:
        feeds = []
        m = re.fullmatch(r"/category/([a-z0-9-]+)/", path)
        if m and m.group(1) in CAT_NAME: feeds = [(f"{CAT_NAME[m.group(1)]} RSS", f"/category/{m.group(1)}/feed.xml")]
        m = re.fullmatch(r"/local/([a-z0-9-]+)/", path)
        if m: feeds = [(f"{m.group(1).replace('-', ' ').title()} RSS", f"/local/{m.group(1)}/feed.xml")]
        if path in ("/press-releases/", "/local/"): feeds = [("Local news RSS", "/press-releases/feed.xml")]
    out += [(t, h, "atom" if h.endswith("feed.xml") and "/category/" not in h and "/local/" not in h and h != "/press-releases/feed.xml" else "rss") for t, h in feeds]
    return "".join(f'<link rel="alternate" type="application/{k}+xml" title="{esc(t)}" href="{h}">' for t, h, k in out)

def head(title, desc=TAG, path="/", og_type="website", extra_head="", og_img=None, md=None, robots=None, ld=None, preload_img=None, article=None, feeds=None, canonical=True):
    """Inner HTML of <head>. robots: None = index (stories and the 404 default to noindex). ld: list of JSON-LD nodes.
    preload_img: href or {"href","srcset","sizes"} for the LCP image. article: {"published","modified","section","tags","author"}.
    feeds: extra [(title, href)] alternates (auto-derived for section/area/local pages). canonical=False drops canonical and og:url."""
    url = SITE + path
    is404 = path.endswith("404.html")
    if robots is None: robots = NOINDEX if (path.startswith("/story/") or is404) else ROBOTS
    if is404: canonical = False
    desc = HOME_DESC if path == "/" and (not desc or desc == TAG) else clean(desc or TAG, 155)
    og = og_img or SITE + "/og.png"
    ow, oh, otype = _og_meta(og)
    alt = NAME if title == NAME else clean(title, 200)
    nodes = list(ld or [])
    for m in _LD_RX.findall(extra_head or ""):      # legacy: ldj() scripts passed in extra_head join the graph
        try: nodes.append(json.loads(m))
        except ValueError: pass
    extra_head = _LD_RX.sub("", extra_head or "")
    pre = ""
    if preload_img:
        pi = preload_img if isinstance(preload_img, dict) else {"href": preload_img}
        pre = f'<link rel="preload" as="image" href="{esc(pi["href"])}"' + (f' imagesrcset="{esc(pi["srcset"])}"' if pi.get("srcset") else "") + (f' imagesizes="{esc(pi["sizes"])}"' if pi.get("sizes") else "") + ' fetchpriority="high">'
    art = ""
    if article:
        a = article
        art = "".join(f'<meta property="article:{k}" content="{esc(v)}">' for k, v in (("published_time", a.get("published")), ("modified_time", a.get("modified")), ("section", a.get("section"))) if v)
        art += "".join(f'<meta property="article:tag" content="{esc(t)}">' for t in (a.get("tags") or []) if t)
        if a.get("author"): art += f'<meta name="author" content="{esc(a["author"])}">'
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(page_title(title, path))}</title>
<link rel="stylesheet" href="/style.css">
<link rel="preload" href="/fonts/outfit.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/fonts/jakarta.woff2" as="font" type="font/woff2" crossorigin>{pre}
<meta name="description" content="{esc(desc)}">{f'<link rel="canonical" href="{url}">' if canonical else ''}
<meta name="robots" content="{robots}"><meta name="theme-color" content="#0B1A33"><meta name="color-scheme" content="light"><meta name="format-detection" content="telephone=no">
{ICONS}{_feeds(path, feeds)}{f'<link rel="alternate" type="text/markdown" href="{md}">' if md else ''}<link rel="help" type="text/plain" href="/llms.txt" title="llms.txt">
<meta property="og:site_name" content="{NAME}"><meta property="og:locale" content="en_US"><meta property="og:type" content="{og_type}">{f'<meta property="og:url" content="{url}">' if canonical else ''}
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{esc(og)}"><meta property="og:image:secure_url" content="{esc(og)}"><meta property="og:image:type" content="{otype}"><meta property="og:image:width" content="{ow}"><meta property="og:image:height" content="{oh}"><meta property="og:image:alt" content="{esc(alt)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(desc)}"><meta name="twitter:image" content="{esc(og)}"><meta name="twitter:image:alt" content="{esc(alt)}">{art}
{graph(nodes)}
<script>document.documentElement.classList.add("js")</script>{extra_head}"""
