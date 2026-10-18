"""Regional sources ingested directly at build time (DECISIONS.md section 13).

Reads content/sources.yaml, fetches every enabled feed concurrently (12s per feed, one retry, failures
tolerated), parses with feedparser and normalises entries to the tracker item shape:

    id, title, link, summary, source, category="local", cat="local", local=True, regions=[...], kind, tier,
    via="direct", ts, projects=[], slug  (+ source_key, homepage, paywalled, tags, fallback,
    event_start/event_end/venue for calendar feeds)

Public API:
    load_local_items(taxonomy=None, *, registry=None, offline_dir=None, now=None) -> list[dict]
    load_registry(path=None) -> dict
    normalize(entry, src, reg, now, taxonomy=None) -> dict | None
    split_publisher(title) -> (title, publisher | None)

Offline mode: when TRACKER_BASE is a local directory (tests, offline builds) feeds are read from
tests/fixtures/feeds/<key>.xml instead of the network. SOURCES_DISABLED=1 returns [] immediately.
"""
import os, re, sys, time, html, hashlib, pathlib, calendar, datetime as dt, zoneinfo
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests, yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import ROOT, SRC, BLOCK
from .text import clean, slugify

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None

UA = "GroundLevelNews/1.0 (+https://groundlevelnews.com; news@groundlevelnews.com)"
REGISTRY = ROOT / "content/sources.yaml"
FIXTURES = ROOT / "tests/fixtures/feeds"
TIMEOUT = 12          # seconds per feed (connect and read)
WORKERS = 8
BUDGET = 45           # seconds for the whole batch
MAX_AGE_DAYS = 14
EVENT_HORIZON_DAYS = 120
MIN_TITLE = 15
MAX_FALLBACK_ITEMS = 15   # per Google News query (tier 3), newest first; override per source with max_items
# DECISIONS section 12: split on the LAST " - " so hyphenated publishers ("Las Vegas Review-Journal") survive.
GNEWS_SPLIT = re.compile(r"^(.*\S)\s+[-–]\s+([^–]{2,60})$")
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
LOOSE_DATE = re.compile(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?")
US_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
LONG_DATE = re.compile(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})")
CLOCK = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp])\.?[Mm]\.?")
# Latin-script non-English gate (Spanish / French / German function words).
FOREIGN = {"el", "la", "los", "las", "del", "en", "para", "por", "una", "con", "que", "es", "un", "su", "sus", "más", "como",
           "pero", "este", "esta", "ser", "sobre", "también", "años", "le", "les", "des", "et", "est", "une", "pour", "dans", "qui",
           "sur", "avec", "pas", "aux", "der", "die", "das", "und", "nicht", "ist", "mit", "für", "auf", "dem", "den", "ein", "eine",
           "sich", "wird", "nach", "bei", "zu", "von"}
BOILER = [
    re.compile(r"\bcontinue reading\b.*$", re.I), re.compile(r"\bread (the )?(full|more|whole)\b.*$", re.I),
    re.compile(r"\[…\]|\[\.\.\.\]|…$"), re.compile(r"\bthe post\b.+?\bappeared first on\b.*$", re.I),
    re.compile(r"^\s*Home\s+Info\s+Press Releases\b.*$", re.I),            # BLM breadcrumb boilerplate
    re.compile(r"^(MOHAVE COUNTY|KINGMAN|BULLHEAD CITY|LAKE HAVASU CITY|LAUGHLIN|LAS VEGAS|BOULDER CITY|MESQUITE|PHOENIX|CARSON CITY)[A-Z ,.]*\s+[–-]\s+"),
    re.compile(r"\bclick (below|here)\b.*?\.", re.I),
]
HAS_LETTERS = re.compile(r"[A-Za-z]")
ACRONYMS = {"USA", "US", "U.S.", "AZ", "NV", "CA", "LHC", "BHC", "HOA", "P&Z", "ADOT", "NDOT", "BLM", "NPS", "USGS", "NWS", "FBI", "DUI", "DPS", "MCSO",
            "LHCPD", "BHCPD", "LVMPD", "CRUHSD", "LHUSD", "KUSD", "MCC", "COVID", "COVID-19", "HHW", "RSVP", "CPR", "AED", "RFP", "RFQ", "CDBG", "FEMA", "EPA",
            "TAB", "CCSD", "UNLV", "ASU", "NAU", "MVDN", "BITD", "SNORE", "UTV", "ATV", "OHV", "AM", "PM", "LLC", "PD", "FD", "SWAT", "K-9", "I-40", "I-11", "I-15", "US-95", "SR-95", "SR-68"}


# ----------------------------------------------------------------------------- registry
def _compile(spec, filters):
    if not spec: return None
    pats = []
    for p in (filters.get(spec, []) if isinstance(spec, str) else list(spec)):
        pats.extend(filters[p] if p in filters else [p])   # a list may name a shared filter
    parts = []
    for p in pats:
        if not p: continue
        parts.append(f"(?i:{p[4:]})" if p.startswith("(?i)") else f"(?:{p})")  # scoped flags: inline (?i) is illegal mid-pattern
    return re.compile("|".join(parts)) if parts else None


def load_registry(path=None):
    """Parse content/sources.yaml. Returns {"sources": [...], "disabled": [...], "denylist_hosts": set, "filters": {...}}."""
    raw = yaml.safe_load(pathlib.Path(path or REGISTRY).read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    filters = raw.get("filters") or {}
    out = []
    for s in raw.get("sources") or []:
        if not s or not s.get("key") or not s.get("url") or s.get("enabled", True) is False: continue
        s = {**defaults, **s}
        s.setdefault("name", s["key"]); s.setdefault("kind", "media"); s.setdefault("tier", 2); s.setdefault("region", None)
        s.setdefault("regions_extra", []); s.setdefault("paywalled", False); s.setdefault("homepage", None)
        s["_must"] = _compile(s.get("must_match"), filters)
        s["_drop"] = _compile(s.get("drop"), filters)
        s["_drop_link"] = _compile(s.get("drop_link"), filters)
        try: s["_tz"] = zoneinfo.ZoneInfo(s.get("tz") or "America/Phoenix")
        except Exception: s["_tz"] = dt.timezone(dt.timedelta(hours=-7))
        out.append(s)
    return {"sources": out, "disabled": raw.get("disabled") or [], "filters": filters,
            "denylist_hosts": {h.lower() for h in (raw.get("denylist_hosts") or [])}}


def fixture_dir():
    """Directory of saved feed XML when TRACKER_BASE is a local path, else None."""
    if "://" in SRC: return None
    for cand in (pathlib.Path(SRC) / "feeds", FIXTURES):
        if cand.is_dir(): return cand
    return FIXTURES


# ----------------------------------------------------------------------------- fetching
def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"})
    retry = Retry(total=1, connect=1, read=1, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504), raise_on_status=False)
    s.mount("https://", HTTPAdapter(max_retries=retry)); s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def _fetch_bytes(session, url):
    r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    if not r.content.strip(): raise ValueError("empty body")
    return r.content


def fetch_feed(src, session=None, offline=None):
    """Return (feed, meta). In offline mode missing fixtures give (None, "no fixture")."""
    if feedparser is None: raise RuntimeError("feedparser is not installed (pip install feedparser)")
    if offline is not None:
        f = pathlib.Path(offline) / f"{src['key']}.xml"
        if not f.exists(): return None, "no fixture"
        data = f.read_bytes()
    else:
        data = _fetch_bytes(session or _session(), src["url"])
    d = feedparser.parse(data)
    if d.bozo and not d.entries: raise ValueError(f"unparseable feed: {getattr(d, 'bozo_exception', '')}")
    return d, "ok"


# ----------------------------------------------------------------------------- normalisation helpers
def clean_link(url):
    """Resolve to a canonical absolute URL: drop utm_* / fbclid / tracking params and fragments."""
    url = (url or "").strip()
    if not url: return ""
    try:
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.netloc: return ""
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith(("utm_", "mc_", "ns_", "ref_")) and k.lower() not in {"fbclid", "gclid", "igshid", "cmpid", "ocid", "src", "ref"}]
        return urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", urlencode(q), ""))
    except Exception:
        return ""


def host_of(url):
    try: return (urlsplit(url).netloc or "").lower().removeprefix("www.")
    except Exception: return ""


def split_publisher(title):
    """Google News titles end in ' - Publisher'. Split on the LAST ' - '; hyphens inside the publisher survive."""
    m = GNEWS_SPLIT.match(title or "")
    if not m: return title, None
    head, pub = m.group(1).strip(), m.group(2).strip()
    # "Story – KLAS - KLAS 8 News Now": drop a dangling station/brand tag that is part of the publisher name
    t = re.match(r"^(.*\S)\s+[-–|]\s+([^-–|]{2,30})$", head)
    if t and t.group(2).strip().lower() in pub.lower(): head = t.group(1).strip()
    return head, pub


def _struct_to_epoch(st):
    try: return int(calendar.timegm(st)) if st else None
    except Exception: return None


def parse_loose_date(s, tz):
    """'Fri, 16 October 2026 16:30:00' (no offset) -> epoch in the feed's zone. None when unparseable."""
    m = LOOSE_DATE.search(s or "")
    if not m: return None
    mon = MONTHS.get(m.group(2).lower())
    if not mon: return None
    try:
        d = dt.datetime(int(m.group(3)), mon, int(m.group(1)), int(m.group(4) or 12), int(m.group(5) or 0), int(m.group(6) or 0), tzinfo=tz)
        return int(d.timestamp())
    except ValueError:
        return None


def entry_ts(entry, tz):
    for k in ("published_parsed", "updated_parsed", "created_parsed"):
        ts = _struct_to_epoch(entry.get(k))
        if ts: return ts
    for k in ("published", "updated", "created", "dc_date"):
        ts = parse_loose_date(entry.get(k), tz)
        if ts: return ts
    return None


def looks_foreign(text):
    words = re.findall(r"[a-záéíóúñüäöß]+", (text or "").lower())
    if len(words) < 6: return False
    hits = sum(1 for w in words if w in FOREIGN)
    return hits >= 3 and hits / len(words) >= 0.12


def recase(title):
    """Re-case ALL-CAPS headlines (city notices) while leaving normal titles alone."""
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 12 or sum(c.isupper() for c in letters) / len(letters) < 0.9: return title
    small = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
    out = []
    for i, w in enumerate(title.split(" ")):
        lw = w.lower()
        if w.strip("():,.") in ACRONYMS or re.fullmatch(r"(?:I|US|SR|AZ|NV|CA)-?\d+[A-Z]?|\d+[A-Z]{1,2}|[A-Z]\.[A-Z]\.", w.strip("():,.")): out.append(w); continue
        out.append(lw if (i and lw in small) else lw[:1].upper() + lw[1:])
    return " ".join(out)


def base_clean_summary(title, summary):
    """Trivial cleaner used before (or instead of) taxonomy.clean_summary: strip boilerplate, drop title echoes."""
    s = clean(summary, 2000)
    for rx in BOILER: s = rx.sub("", s).strip()
    s = re.sub(r"\s+", " ", s).strip(" -–|")
    if not HAS_LETTERS.search(s): return ""
    t = re.sub(r"\W", "", (title or "").lower())
    k = re.sub(r"\W", "", s.lower())
    if not k or k == t or k.startswith(t) and len(k) - len(t) < 25 or t.startswith(k): return ""
    return clean(s, 420)


def summarize(title, summary, taxonomy):
    s = base_clean_summary(title, summary)
    if taxonomy is not None and hasattr(taxonomy, "clean_summary"):
        try: s = taxonomy.clean_summary(title, s) or ""
        except Exception: pass
    return clean(s, 420) if s else ""


def detect(text, taxonomy):
    if taxonomy is None or not hasattr(taxonomy, "detect_regions"): return []
    try: return list(taxonomy.detect_regions(text) or [])
    except Exception: return []


# ----------------------------------------------------------------------------- events
def _local_dt(y, m, d, hh=12, mm=0, tz=None):
    try: return dt.datetime(y, m, d, hh, mm, tzinfo=tz)
    except ValueError: return None


def _clock(s):
    m = CLOCK.search(s or "")
    if not m: return 12, 0
    h, mi, ap = int(m.group(1)) % 12, int(m.group(2)), m.group(3).lower()
    return (h + 12 if ap == "p" else h), mi


def event_window(entry, src, summary_text):
    """Return (start_dt, end_dt, venue, summary) from CivicPlus calendarEvent:* elements or the
    Simpleview/Events Calendar 'MM/DD/YYYY to MM/DD/YYYY - ' summary prefix. Unparseable -> (None, None, None, summary)."""
    tz = src["_tz"]
    start = end = venue = None
    dates = entry.get("calendarevent_eventdates") or ""
    times = entry.get("calendarevent_eventtimes") or ""
    if not dates:  # fall back to the description: "Event date: October 21, 2026 Event Time: 05:00 PM - 07:30 PM"
        m = re.search(r"Event date:\s*([A-Za-z]+\.? \d{1,2}, \d{4})", summary_text or "")
        if m: dates = m.group(1)
        m = re.search(r"Event Time:\s*([^L]*?)(?:Location:|$)", summary_text or "")
        if m: times = m.group(1)
    m = LONG_DATE.search(dates)
    if m and MONTHS.get(m.group(1).lower()):
        hh, mm = _clock(times)
        start = _local_dt(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)), hh, mm, tz)
        loc = clean(entry.get("calendarevent_location") or "", 160)
        venue = re.sub(r"(?<=[a-z.])(?=[A-Z])", " ", loc) or None
        rest = re.sub(r"^.*?Location:\s*", "", summary_text or "", count=1, flags=re.S).strip() if "Location:" in (summary_text or "") else ""
        if rest and loc and re.sub(r"\W", "", rest) in re.sub(r"\W", "", loc): rest = ""
        return start, None, venue, rest
    m = re.match(r"^(?:Starting\s+)?(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+to\s+(\d{1,2})/(\d{1,2})/(\d{4}))?\s*[-–]?\s*", summary_text or "")
    if m:
        start = _local_dt(int(m.group(3)), int(m.group(1)), int(m.group(2)), 12, 0, tz)
        if m.group(4): end = _local_dt(int(m.group(6)), int(m.group(4)), int(m.group(5)), 23, 59, tz)
        summary_text = summary_text[m.end():].strip()
        if (summary_text or "").lower().startswith("starting"): summary_text = ""
    return start, end, venue, summary_text


# ----------------------------------------------------------------------------- normalisation
def normalize(entry, src, reg, now, taxonomy=None):
    """Turn one feedparser entry into a tracker-shaped item, or None when it should be dropped."""
    title = clean(entry.get("title"), 200)
    link = clean_link(entry.get("link") or (entry.get("links") or [{}])[0].get("href"))
    if not title or not link: return None
    publisher, is_gnews = src["name"], src["key"].startswith("gnews")
    homepage = src.get("homepage")
    if is_gnews:
        gsrc = entry.get("source") or {}
        title, suffix = split_publisher(title)
        publisher = clean(gsrc.get("title") or suffix or "", 60) or "Google News"
        if gsrc.get("href"): homepage = gsrc["href"]
    title = recase(title)
    if len(title) < MIN_TITLE: return None
    if host_of(link) in reg["denylist_hosts"]: return None
    if src["_drop_link"] and src["_drop_link"].search(link): return None
    raw_summary = entry.get("summary") or (entry.get("content") or [{}])[0].get("value") or entry.get("description") or ""
    if is_gnews: raw_summary = ""  # Google's description is the title + publisher again
    text_summary = clean(raw_summary, 2000)
    is_events = src["kind"] == "events"
    start = end = venue = None
    if is_events:
        start, end, venue, text_summary = event_window(entry, src, text_summary)
    summary = summarize(title, text_summary, taxonomy)
    blob = f"{title} {summary}"
    if BLOCK.search(f"{blob} {publisher} {link}"): return None
    if looks_foreign(blob): return None
    if src["_must"] and not src["_must"].search(blob): return None
    if src["_drop"] and src["_drop"].search(f"{blob} | {publisher}"): return None
    if len(re.findall(r"[Ѐ-ӿ؀-ۿ぀-ヿ一-鿿]", title)) > len(title) * .2: return None

    max_age = int(src.get("max_age_days") or MAX_AGE_DAYS) * 86400
    ts = entry_ts(entry, src["_tz"])
    kind = src["kind"]
    item = {}
    if is_events:
        today = dt.datetime.fromtimestamp(now, dt.timezone.utc)
        if start is not None:
            last = end or start
            if last < today - dt.timedelta(days=1): return None               # already happened
            if start > today + dt.timedelta(days=EVENT_HORIZON_DAYS): return None
            if start < today - dt.timedelta(days=1) and (last - start) > dt.timedelta(days=8): return None  # long-running show, not a dated event
            item["event_start"] = start.isoformat()
            if end: item["event_end"] = end.isoformat()
        elif ts is None or ts < now - max_age:
            return None
        if venue: item["venue"] = venue
        kind = src.get("item_kind") or ("meeting" if re.search(r"\b(meeting|commission|council|board|hearing|workshop|committee)\b", title, re.I) else "event")
        ts = ts if (ts and now - max_age < ts <= now) else now - 3600
    else:
        if ts is None: ts = now - 3600
        elif ts < now - max_age: return None
        ts = min(ts, now)

    key = hashlib.sha1(link.encode("utf-8")).hexdigest()[:14]
    regions = []
    for r in [src.get("region"), *(src.get("regions_extra") or []), *detect(f"{blob} {venue or ''}", taxonomy)]:
        if r and r not in regions: regions.append(r)
    tags = [clean(t.get("term"), 40) for t in (entry.get("tags") or []) if isinstance(t, dict) and t.get("term")][:6]
    item.update({
        "id": key, "title": title, "link": link, "summary": summary, "source": publisher,
        "category": "local", "cat": "local", "local": True, "regions": regions, "kind": kind, "tier": int(src.get("tier") or 2),
        "via": "direct", "ts": int(ts), "projects": [], "slug": f"{slugify(title)}-{key[:6]}",
        "source_key": src["key"], "homepage": homepage, "paywalled": bool(src.get("paywalled")),
    })
    if tags: item["tags"] = tags
    if is_gnews: item["fallback"] = True
    return item


def dedupe(items):
    """Drop duplicates by canonical link and by normalised title; the first occurrence (best tier, newest) wins."""
    seen_link, seen_title, out = set(), set(), []
    for it in items:
        lk = it["link"].lower().rstrip("/")
        tk = re.sub(r"\W", "", it["title"].lower())[:60]
        if lk in seen_link or tk in seen_title: continue
        seen_link.add(lk); seen_title.add(tk); out.append(it)
    return out


# ----------------------------------------------------------------------------- entry point
def load_local_items(taxonomy=None, *, registry=None, offline_dir=None, now=None, log=None):
    """Fetch all enabled regional feeds and return normalised, deduplicated local items (newest first).

    taxonomy: the gln.taxonomy module (optional; imported lazily when omitted). Without it, regions are the
    feed's configured region(s) only and summaries get the trivial cleaner.
    registry: parsed registry dict (default content/sources.yaml). offline_dir: directory of <key>.xml fixtures
    (default: automatic when TRACKER_BASE is a local path). now: epoch for deterministic tests.
    """
    log = log or (lambda m: print(m, file=sys.stderr))
    if os.environ.get("SOURCES_DISABLED") == "1":
        log("local sources: disabled (SOURCES_DISABLED=1)"); return []
    if feedparser is None:
        log("WARN local sources: feedparser not installed; skipping"); return []
    if taxonomy is None:
        try: from . import taxonomy as _tx; taxonomy = _tx
        except Exception: taxonomy = None
    reg = registry or load_registry()
    offline = offline_dir if offline_dir is not None else fixture_dir()
    now = int(now or time.time())
    session = None if offline is not None else _session()
    ok = failed = skipped = 0
    items = []

    def work(src):
        return src, fetch_feed(src, session=session, offline=offline)

    t0 = time.monotonic()
    ex = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="feed")
    futures = {ex.submit(work, s): s for s in reg["sources"]}
    pending = set(futures)
    try:
        while pending:
            left = BUDGET - (time.monotonic() - t0)
            if left <= 0: break
            done, pending = wait(pending, timeout=left, return_when=FIRST_COMPLETED)
            for fut in done:
                src = futures[fut]
                try:
                    src, (feed, meta) = fut.result()
                except Exception as e:
                    failed += 1; log(f"WARN source {src['key']}: {type(e).__name__}: {str(e)[:160]}"); continue
                if feed is None:
                    skipped += 1; continue
                ok += 1
                got = []
                for e in feed.entries:
                    try:
                        it = normalize(e, src, reg, now, taxonomy)
                    except Exception as ex_:  # one bad entry must not kill the feed
                        log(f"WARN source {src['key']} entry: {type(ex_).__name__}: {str(ex_)[:120]}"); continue
                    if it: got.append(it)
                cap = int(src.get("max_items") or (MAX_FALLBACK_ITEMS if src["key"].startswith("gnews") else 0))
                if cap and len(got) > cap: got = sorted(got, key=lambda i: -i["ts"])[:cap]
                items.extend(got)
        for fut in pending:
            failed += 1; log(f"WARN source {futures[fut]['key']}: timed out (batch budget {BUDGET}s)")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    items.sort(key=lambda i: (i["tier"], -i["ts"]))
    items = dedupe(items)
    items.sort(key=lambda i: -i["ts"])
    extra = f", {skipped} without fixture" if skipped else ""
    log(f"local sources: {ok} feeds ok, {failed} failed, {len(items)} items{extra} ({time.monotonic() - t0:.1f}s)")
    return items
