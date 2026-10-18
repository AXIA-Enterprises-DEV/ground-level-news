"""Site-wide constants and environment configuration. Side-effect free apart from the optional `brand` import;
this module must never import taxonomy/feed/pages (they import it)."""
import os, re, datetime as dt, pathlib, sys
from urllib.parse import urlparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # scripts/ on the path for brand.py
try:
    import brand
except Exception as e:
    brand = None; print(f"WARN brand: {e}", file=sys.stderr)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
OUT = pathlib.Path(os.environ.get("OUT_DIR") or ROOT / "_site")
SRC = os.environ.get("TRACKER_BASE", "https://axia-enterprises-dev.github.io/news-tracker")
SITE = os.environ.get("SITE_URL", "https://groundlevelnews.com").rstrip("/")
BASE = urlparse(SITE).path.rstrip("/")
NAME = "Ground Level News"
TAG = "News from the ground up."
INDEXNOW_KEY = "5a8308b39ca87422bfd5d4eb53c1c5bb"
CONTACT = os.environ.get("CONTACT_EMAIL", "news@groundlevelnews.com")
# Names that must never appear anywhere on the published site.
BLOCK = re.compile(r"\b(axia|clem)\b", re.I)
NOW = dt.datetime.now(dt.timezone.utc)
TZ_NAME = "America/Phoenix"            # newsroom time zone (Arizona, no DST); UTC stays in datetime attributes

# ---------- feed guards (DECISIONS §12) ----------
MIN_ITEMS = int(os.environ.get("MIN_ITEMS", "200"))      # fewer surviving items than this fails the build
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "1500"))     # cap on aggregated items rendered per build
OG_STORIES = int(os.environ.get("OG_STORIES", "60"))     # share cards only for the first N stories
SOURCES_DISABLED = os.environ.get("SOURCES_DISABLED", "") not in ("", "0", "false", "no")
FEED_TIMEOUT = int(os.environ.get("FEED_TIMEOUT", "30"))

# ---------- sections (DECISIONS §1; local first, keys never change) ----------
CATS = [("local", "Local"), ("us", "U.S."), ("world", "World"), ("politics", "Politics"), ("business", "Business"),
        ("markets", "Markets"), ("tech", "Tech & Science"), ("science", "Science"), ("sports", "Sports")]
CAT_NAME = dict(CATS)
# Shorter labels for kickers/tags where "Tech & Science" is too long.
CAT_SHORT = {**CAT_NAME, "tech": "Tech"}
# Page titles / H1s per section.
CAT_TITLE = {"local": "Local News: Colorado River & Southern Nevada", "us": "U.S. News", "world": "World News & Foreign Policy",
             "politics": "Politics & Government", "business": "Business & Economy", "markets": "Markets & Money",
             "tech": "Technology & AI", "science": "Science & Health", "sports": "Sports"}
# One-line editorial description per section (no refresh-cadence claims).
CAT_DESC = {
    "local": "News from Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman and the Clark County communities along the Colorado River: press releases, briefs and the region's own publishers.",
    "us": "National news from across the United States: public safety, courts, weather, culture and the stories shaping daily life.",
    "world": "Foreign affairs, conflicts, diplomacy and the international economy, from wire services and newsrooms around the world.",
    "politics": "Elections, Congress, the White House, the courts and state government, with an eye on Nevada and Arizona.",
    "business": "Companies, jobs, housing, energy and small business, from Main Street to the national economy.",
    "markets": "Stocks, the Fed, bonds, commodities and oil prices, plus the money stories behind the numbers.",
    "tech": "Artificial intelligence, Big Tech, cybersecurity, gadgets and startups, with the science desk alongside.",
    "science": "Research, space, climate and public health, reported from journals, labs and agencies.",
    "sports": "Golf, football, hockey, basketball and the fight game, including Las Vegas events and Nevada and Arizona prep sports.",
}
# Sections that are shown as sub-tabs of another section in the primary nav.
CAT_PARENT = {"markets": "business", "science": "tech"}
# Sub-tabs shown on a section page: parent key -> [(key, label, href)].
CAT_TABS = {"business": [("business", "Business", "/category/business/"), ("markets", "Markets", "/category/markets/")],
            "tech": [("tech", "Tech", "/category/tech/"), ("science", "Science", "/category/science/")]}
CAT_TABS["markets"] = CAT_TABS["business"]; CAT_TABS["science"] = CAT_TABS["tech"]

# ---------- regions and topics shown in navigation (plain data for the UI agent) ----------
# Home regions in nav order: (region key, label, href). Must match taxonomy.REGIONS home keys (tested).
LOCAL_AREAS = [("bullhead-city", "Bullhead City", "/local/bullhead-city/"), ("laughlin", "Laughlin", "/local/laughlin/"),
               ("mohave-valley", "Mohave Valley", "/local/mohave-valley/"), ("lake-havasu-city", "Lake Havasu City", "/local/lake-havasu-city/"),
               ("kingman", "Kingman", "/local/kingman/"), ("mohave-county", "Mohave County", "/local/mohave-county/"),
               ("needles", "Needles", "/local/needles/"), ("boulder-city", "Boulder City", "/local/boulder-city/"),
               ("lake-mead", "Lake Mead", "/local/lake-mead/"), ("mesquite", "Mesquite", "/local/mesquite/"),
               ("henderson", "Henderson", "/local/henderson/"), ("las-vegas", "Las Vegas", "/local/las-vegas/"),
               ("north-las-vegas", "North Las Vegas", "/local/north-las-vegas/"), ("clark-county", "Clark County", "/local/clark-county/"),
               ("colorado-river", "Colorado River", "/local/colorado-river/")]
# Topic hubs linked from the "Topics" row and the More menu: (topic key, label, href). Keys exist in taxonomy.TOPICS.
TOPIC_LINKS = [("energy", "Energy & Oil", "/topic/energy/"), ("realestate", "Real Estate & Housing", "/topic/realestate/"),
               ("smallbiz", "Small Business", "/topic/smallbiz/"), ("fed", "Economy & Fed", "/topic/fed/"), ("ai", "Artificial Intelligence", "/topic/ai/"),
               ("water", "Colorado River & Water", "/topic/water/"), ("elections", "Elections 2026", "/topic/elections/"),
               ("cannabis", "Cannabis", "/topic/cannabis/"), ("golf", "Golf", "/topic/golf/"), ("media", "Media & Journalism", "/topic/media/")]
# Primary navigation (desktop + drawer). Each entry: {key, label, href, children: [(key, label, href)]}.
NAV = [
    {"key": "local", "label": "Local", "href": "/local/", "children": LOCAL_AREAS + [("local-all", "All local news", "/local/"), ("submit", "Submit news", "/submit/")]},
    {"key": "us", "label": "U.S.", "href": "/category/us/", "children": []},
    {"key": "world", "label": "World", "href": "/category/world/", "children": []},
    {"key": "politics", "label": "Politics", "href": "/category/politics/", "children": []},
    {"key": "business", "label": "Business", "href": "/category/business/", "children": [("business", "Business", "/category/business/"), ("markets", "Markets", "/category/markets/")]},
    {"key": "tech", "label": "Tech & Science", "href": "/category/tech/", "children": [("tech", "Tech", "/category/tech/"), ("science", "Science", "/category/science/")]},
    {"key": "sports", "label": "Sports", "href": "/category/sports/", "children": []},
    {"key": "more", "label": "More", "href": "/about/", "children": [("topics", "Topics", "/topic/"), ("about", "About", "/about/"),
                                                                    ("standards", "Standards", "/editorial-policy/"), ("feeds", "Feeds", "/rss.xml"), ("ai", "For AI", "/llm-info/")]},
]
NAV_CTA = ("Submit news", "/submit/")

# ---------- legacy names kept for back-compat ----------
LOCAL_PROJECTS = set()        # no longer used: a tracker project tag never makes an item local (taxonomy.detect_regions does)
HIDE_CATS = {"filings"}       # upstream categories that are never rendered
