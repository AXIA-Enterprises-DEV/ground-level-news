"""Site-wide constants and environment configuration."""
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

CATS = [("us","U.S."),("world","World"),("politics","Politics"),("business","Business"),
        ("markets","Markets"),("tech","Tech"),("science","Science"),("sports","Sports"),("local","Local")]
CAT_NAME = dict(CATS)
LOCAL_PROJECTS = {"nevada","realestate","civic"}
HIDE_CATS = {"filings"}
