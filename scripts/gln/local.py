"""Local hubs, area pages, topic hubs and events: /local/, /local/<area>/, /local/events/ (+ .ics), /topic/<key>/, /topic/.
Owned by the local-hubs agent (DECISIONS §7, §10, §11).

Public API:
    render_local(c)                     writes every page above and registers them in c.urls
    events(originals, items=None, now=None) -> [event dict]   (pages.py uses it for the homepage module)
    region_entries(c, key), local_entries(c), hub_keys(), region_name(key), region_scope(key)

Every neighbouring module is imported defensively: taxonomy (REGIONS, TOPICS, detect_regions, area_to_region), head
(crumbs, collection_node, event_node, place_node), shell components (card, pr_card, events_list, cond_strip) and
conditions.render_strip. When one is missing the page still renders with a plain, accessible fallback."""
import re, sys, inspect, hashlib, datetime as dt
from zoneinfo import ZoneInfo
from .config import OUT, SITE, NAME, CONTACT, NOW, CAT_NAME
from . import config as CFG
from . import text as TXT
from .text import esc, clean
from . import shell as S
from .shell import page, write

try:
    from . import head as H
except Exception as e:                      # pragma: no cover
    H = None; print(f"WARN local: head unavailable: {e}", file=sys.stderr)
try:
    from . import taxonomy as T
except Exception:
    T = None
try:
    from . import conditions as COND
except Exception:
    COND = None
try:
    from . import images as IM
except Exception:
    IM = None
try:
    from . import pages as PG
except Exception:
    PG = None

TZ_NAME = getattr(CFG, "TZ_NAME", "America/Phoenix")
try:
    TZ = ZoneInfo(TZ_NAME)
except Exception:                           # pragma: no cover
    TZ = dt.timezone(dt.timedelta(hours=-7), "MST")
UTC = dt.timezone.utc
DAY = dt.timedelta(days=1)
HUB_TITLE = "Local news for the Colorado River region"
HUB_DESC = ("Local news for Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mesquite, Boulder City and the "
            "Colorado River: press releases, agency notices, meetings, events and the region's publishers.")
LATEST_CAP, RIVER_SHOW, RIVER_CAP = 12, 18, 60

# ----------------------------------------------------------------------------- regions (fallback table; taxonomy.REGIONS wins)
def _r(name, state, kind, parent=None, aliases=(), intro="", links=(), desc="", also=(), home=True):
    return {"name": name, "state": state, "kind": kind, "parent": parent, "aliases": list(aliases), "intro": intro,
            "links": [list(l) for l in links], "desc": desc, "also": list(also), "home": home}

FALLBACK_REGIONS = {
    "bullhead-city": _r("Bullhead City", "AZ", "city", "mohave-county", ["bullhead city", "bullhead"],
        "Bullhead City sits on the Arizona bank of the Colorado River across from Laughlin, just below Davis Dam and Lake Mohave. It is the largest city in the Bullhead City, Laughlin and Mohave Valley corridor.",
        [("City of Bullhead City", "https://www.bullheadcityaz.gov/"), ("Mohave County", "https://www.mohave.gov/"), ("Bullhead Area Chamber of Commerce", "https://www.bullheadareachamber.com/"), ("Mohave Daily News", "https://www.mohavedailynews.com/")],
        "Bullhead City, Arizona news: city hall, police and fire, schools, the riverfront and press releases from local agencies and businesses.", also=["colorado-river"]),
    "laughlin": _r("Laughlin", "NV", "area", "clark-county", ["laughlin"],
        "Laughlin is an unincorporated resort town in Clark County, Nevada, on the Colorado River opposite Bullhead City. Most public decisions about it run through the Clark County Commission and the Laughlin Town Advisory Board.",
        [("Clark County", "https://www.clarkcountynv.gov/"), ("Laughlin Chamber of Commerce", "https://www.laughlinchamber.com/"), ("Visit Laughlin", "https://www.visitlaughlin.com/")],
        "Laughlin, Nevada news: Clark County decisions, the Town Advisory Board, resorts and events along the Colorado River, plus local press releases.", also=["colorado-river"]),
    "mohave-valley": _r("Mohave Valley", "AZ", "area", "mohave-county", ["mohave valley", "mojave valley", "fort mohave", "fort mojave"],
        "Mohave Valley and Fort Mohave are unincorporated communities in Mohave County, Arizona, south of Bullhead City along the Colorado River. The area is served by the Mohave Valley and Fort Mojave Mesa fire districts and is home to the Fort Mojave Indian Tribe.",
        [("Mohave County", "https://www.mohave.gov/"), ("Fort Mojave Indian Tribe", "https://www.fortmojaveindiantribe.com/")],
        "Mohave Valley and Fort Mohave, Arizona news: fire districts, schools, Mohave County decisions and press releases from local agencies.", also=["colorado-river"]),
    "lake-havasu-city": _r("Lake Havasu City", "AZ", "city", "mohave-county", ["lake havasu", "havasu"],
        "Lake Havasu City is a lakeside city in Mohave County, Arizona, known for London Bridge and for boating on Lake Havasu, the reservoir behind Parker Dam.",
        [("Lake Havasu City", "https://www.lhcaz.gov/"), ("Lake Havasu Area Chamber of Commerce", "https://www.havasuchamber.com/"), ("Today's News-Herald", "https://www.havasunews.com/")],
        "Lake Havasu City, Arizona news: city hall notices, police and fire, road work, the lake and press releases from local agencies.", also=["colorado-river"]),
    "kingman": _r("Kingman", "AZ", "city", "mohave-county", ["kingman"],
        "Kingman is the Mohave County seat, at the junction of Interstate 40, U.S. 93 and historic Route 66 in northwestern Arizona.",
        [("City of Kingman", "https://www.cityofkingman.gov/"), ("Mohave County", "https://www.mohave.gov/"), ("Kingman Daily Miner", "https://kdminer.com/")],
        "Kingman, Arizona news: city council, Mohave County government, public safety, roads and press releases from local agencies."),
    "mohave-county": _r("Mohave County", "AZ", "county", "arizona", ["mohave county"],
        "Mohave County covers the northwestern corner of Arizona, from the Colorado River corridor to the Arizona Strip. The Board of Supervisors and most county departments are based in Kingman.",
        [("Mohave County", "https://www.mohave.gov/"), ("Arizona Department of Transportation", "https://azdot.gov/")],
        "Mohave County, Arizona news: Board of Supervisors, elections, sheriff, roads, planning and press releases from county departments."),
    "needles": _r("Needles", "CA", "city", "colorado-river", ["city of needles", "needles, calif", "needles, california"],
        "Needles is a small California city on the Colorado River at the Arizona line, on Interstate 40 and historic Route 66, and the nearest California town to Mohave Valley and Laughlin.",
        [("City of Needles", "https://www.cityofneedles.com/")],
        "Needles, California news: city council, the river, Interstate 40 and press releases from local agencies."),
    "boulder-city": _r("Boulder City", "NV", "city", "clark-county", ["boulder city", "hoover dam"],
        "Boulder City, Nevada, was built to house the workers who raised Hoover Dam and remains the gateway to the dam and Lake Mead National Recreation Area. It is one of the few Nevada communities that prohibits gambling.",
        [("Boulder City", "https://www.bcnv.org/"), ("Boulder City Chamber of Commerce", "https://www.bouldercitychamber.com/"), ("Boulder City Review", "https://bouldercityreview.com/")],
        "Boulder City, Nevada news: city council, Hoover Dam, Lake Mead, utilities, events and press releases from local agencies.", also=["colorado-river"]),
    "lake-mead": _r("Lake Mead", "NV", "area", "colorado-river", ["lake mead", "hoover dam"],
        "Lake Mead, the reservoir behind Hoover Dam, straddles the Nevada and Arizona line and anchors Lake Mead National Recreation Area, which also takes in Lake Mohave down to Davis Dam.",
        [("Lake Mead National Recreation Area", "https://www.nps.gov/lake/"), ("Bureau of Reclamation, Lower Colorado Basin", "https://www.usbr.gov/lc/")],
        "Lake Mead and Hoover Dam news: water levels, National Park Service notices, Reclamation operations, boating and recreation."),
    "mesquite": _r("Mesquite", "NV", "city", "clark-county", ["mesquite, nev", "mesquite, nv", "mesquite nevada", "city of mesquite", "mesquite police", "virgin valley"],
        "Mesquite is a city in the Virgin Valley of northeastern Clark County, Nevada, on Interstate 15 near the Arizona and Utah lines, known for golf and gaming.",
        [("City of Mesquite", "https://www.mesquitenv.gov/"), ("Mesquite Local News", "https://mesquitelocalnews.com/")],
        "Mesquite, Nevada news: city council, police, the Virgin Valley, golf and gaming, and press releases from local agencies."),
    "henderson": _r("Henderson", "NV", "city", "clark-county", ["henderson, nev", "henderson, nv", "city of henderson", "henderson nevada"],
        "Henderson is Nevada's second-largest city, southeast of Las Vegas in Clark County, and home to the Clark County Museum and Lake Las Vegas.",
        [("City of Henderson", "https://www.cityofhenderson.com/"), ("Clark County", "https://www.clarkcountynv.gov/")],
        "Henderson, Nevada news: city council, police and fire, parks and events, and press releases from local agencies."),
    "las-vegas": _r("Las Vegas", "NV", "city", "clark-county", ["las vegas", "unlv", "lvmpd"],
        "Las Vegas is the seat of Clark County and the center of Southern Nevada, where many of the state's agencies, courts and institutions make decisions that reach the Colorado River communities.",
        [("City of Las Vegas", "https://www.lasvegasnevada.gov/"), ("Clark County", "https://www.clarkcountynv.gov/")],
        "Las Vegas, Nevada news: city and county government, courts, public safety, the Strip and the agencies whose decisions reach the rest of Southern Nevada."),
    "north-las-vegas": _r("North Las Vegas", "NV", "city", "clark-county", ["north las vegas", "nellis air force base"],
        "North Las Vegas is a city in the northern Las Vegas Valley and home to Nellis Air Force Base.",
        [("City of North Las Vegas", "https://www.cityofnorthlasvegas.com/")],
        "North Las Vegas, Nevada news: city council, police, Nellis Air Force Base and press releases from local agencies."),
    "clark-county": _r("Clark County", "NV", "county", "nevada", ["clark county"],
        "Clark County, Nevada, governs the Las Vegas Valley and the outlying towns of Laughlin, Mesquite, Boulder City and Searchlight. The County Commission and its departments make most of the public decisions that reach Laughlin.",
        [("Clark County", "https://www.clarkcountynv.gov/"), ("Clark County Election Department", "https://www.clarkcountynv.gov/government/departments/elections/"), ("Las Vegas Review-Journal", "https://www.reviewjournal.com/")],
        "Clark County, Nevada news: County Commission, elections, public safety, parks and museums, and press releases from county departments."),
    "colorado-river": _r("Colorado River", "", "area", None, ["colorado river", "lake mohave", "davis dam"],
        "The lower Colorado River runs from Lake Mead through Hoover Dam, Lake Mohave and Davis Dam to Laughlin, Bullhead City, Needles and Lake Havasu, supplying water and power to Arizona, Nevada and California.",
        [("Bureau of Reclamation, Lower Colorado Basin", "https://www.usbr.gov/lc/"), ("USGS Water Data", "https://waterdata.usgs.gov/"), ("Lake Mead National Recreation Area", "https://www.nps.gov/lake/")],
        "Colorado River news for the corridor from Lake Mead to Lake Havasu: water, dams, river flows, recreation and the towns along both banks."),
    "nevada": _r("Nevada", "", "state", None, ["nevada"],
        "Nevada's state government in Carson City, its Legislature, courts and agencies set rules that reach Laughlin, Mesquite, Boulder City and the rest of Clark County.",
        [("State of Nevada", "https://nv.gov/"), ("Nevada Legislature", "https://www.leg.state.nv.us/"), ("Nevada Department of Transportation", "https://www.dot.nv.gov/")],
        "Nevada news: state government, the Legislature, courts, elections and statewide stories that reach Southern Nevada and the Colorado River.", home=False),
    "arizona": _r("Arizona", "", "state", None, ["arizona"],
        "Arizona's state government in Phoenix, the Legislature, the Arizona Corporation Commission and ADOT set rules that reach Bullhead City, Lake Havasu City, Kingman and Mohave County.",
        [("State of Arizona", "https://az.gov/"), ("Arizona Legislature", "https://www.azleg.gov/"), ("Arizona Department of Transportation", "https://azdot.gov/"), ("Arizona Corporation Commission", "https://www.azcc.gov/")],
        "Arizona news: state government, the Legislature, utilities regulation, elections and statewide stories that reach Mohave County.", home=False),
}
# "also": umbrella memberships that are not the parent (corridor towns belong to the Colorado River hub).
_STATE_NAME = {"AZ": "Arizona", "NV": "Nevada", "CA": "California", "UT": "Utah"}
_AREA_FALLBACK = {"bullhead city": "bullhead-city", "laughlin": "laughlin", "mohave valley": "mohave-valley", "mojave valley": "mohave-valley",
                  "fort mohave": "mohave-valley", "fort mojave": "mohave-valley", "lake havasu city": "lake-havasu-city", "lake havasu": "lake-havasu-city",
                  "kingman": "kingman", "mohave county": "mohave-county", "needles": "needles", "boulder city": "boulder-city", "lake mead": "lake-mead",
                  "mesquite": "mesquite", "henderson": "henderson", "las vegas": "las-vegas", "north las vegas": "north-las-vegas",
                  "clark county": "clark-county", "colorado river": "colorado-river", "nevada": "nevada", "arizona": "arizona"}
_FALSE_FRIENDS = re.compile(r"\b(?:Franco-Nevada|Sierra Nevada|Nevada City|Las Vegas, New Mexico|Mesquite, (?:Tex|Texas)|Henderson, (?:Ky|Kentucky|N\.?C|Tex|Texas))\b", re.I)


def _regions():
    """Region table: taxonomy.REGIONS (any mapping) merged over the fallback so every key has name/intro/links/desc."""
    src = getattr(T, "REGIONS", None) if T else None
    if not src or not hasattr(src, "items"): return dict(FALLBACK_REGIONS)
    out = {}
    for k, v in src.items():
        v = dict(v) if isinstance(v, dict) else {"name": str(v)}
        base = dict(FALLBACK_REGIONS.get(k) or {})
        base.update({kk: vv for kk, vv in v.items() if vv not in (None, "", [], ())})
        base.setdefault("name", k.replace("-", " ").title()); base.setdefault("state", ""); base.setdefault("kind", "area")
        base.setdefault("parent", None); base.setdefault("aliases", []); base.setdefault("intro", ""); base.setdefault("links", [])
        base.setdefault("desc", ""); base.setdefault("also", [])
        out[k] = base
    for k, v in FALLBACK_REGIONS.items():        # keys the taxonomy does not know yet still get a page
        out.setdefault(k, dict(v))
    return out

REGIONS = _regions()

def region_name(key):
    r = REGIONS.get(key)
    return r["name"] if r else (key or "").replace("-", " ").title()

def region_full_name(key):
    r = REGIONS.get(key) or {}
    st = _STATE_NAME.get(r.get("state") or "", r.get("state") or "")
    return f"{r.get('name', region_name(key))}, {st}" if st and r.get("kind") != "state" else r.get("name", region_name(key))

def home_keys():
    """Home regions in display order: REGIONS[*].home when the taxonomy sets it, else config.LOCAL_AREAS, else the fallback."""
    if T and any(isinstance(v, dict) and "home" in v for v in (getattr(T, "REGIONS", None) or {}).values()):
        return [k for k, v in REGIONS.items() if v.get("home")]
    hr = getattr(T, "HOME_REGIONS", None)
    if hr:
        return [k for k in REGIONS if k in set(hr)]
    areas = [k for k, _, _ in (getattr(CFG, "LOCAL_AREAS", None) or []) if k in REGIONS]
    return areas or [k for k, v in FALLBACK_REGIONS.items() if v.get("home")]

def hub_keys():
    keys = list(home_keys())
    for k in ("colorado-river", "lake-mead", "nevada", "arizona"):
        if k in REGIONS and k not in keys: keys.append(k)
    return keys

def ancestors(key):
    out, seen, stack = [], set(), [key]
    while stack:
        k = stack.pop()
        r = REGIONS.get(k) or {}
        for p in [r.get("parent"), *(r.get("also") or [])]:
            if p and p in REGIONS and p not in seen and p != key:
                seen.add(p); out.append(p); stack.append(p)
    return out

def region_scope(key):
    """The key plus every region that rolls up to it (children count toward parents)."""
    return {key} | {k for k in REGIONS if key in ancestors(k)}

def _children(key): return [k for k in REGIONS if (REGIONS[k].get("parent") == key or key in (REGIONS[k].get("also") or []))]

def nearby(key):
    """(label, href) pairs: parent, siblings and children, in table order, without the key itself."""
    r = REGIONS.get(key) or {}
    keys, par = [], r.get("parent")
    if par in REGIONS: keys.append(par)
    keys += [k for k in REGIONS if REGIONS[k].get("parent") == par and k != key and par] if par else []
    keys += _children(key)
    keys += [k for k in (r.get("also") or []) if k in REGIONS]
    seen, out = set(), []
    for k in keys:
        if k in seen or k == key: continue
        seen.add(k); out.append(k)
    return out[:10]

# ---- region detection fallback (only when items do not carry `regions`)
_ALIAS_RX = None
def _alias_rx():
    global _ALIAS_RX
    if _ALIAS_RX is None:
        _ALIAS_RX = [(k, re.compile(r"\b(?:" + "|".join(re.escape(a) for a in sorted(set(v.get("aliases") or [v["name"].lower()]), key=len, reverse=True)) + r")\b", re.I))
                     for k, v in REGIONS.items()]
    return _ALIAS_RX

def _detect(text):
    if T and callable(getattr(T, "detect_regions", None)):
        try:
            hits = list(T.detect_regions(text) or [])
        except Exception:
            hits = []
    else:
        text = _FALSE_FRIENDS.sub(" ", text or "")
        hits = [k for k, rx in _alias_rx() if rx.search(text)]
    out = []
    for k in hits:
        for kk in [k, *ancestors(k)]:
            if kk not in out: out.append(kk)
    return out

def item_regions(it):
    if "regions" in it and isinstance(it["regions"], (list, tuple)): return list(it["regions"])
    cache = it.get("_regions")
    if cache is None:
        cache = it["_regions"] = _detect(f"{it.get('title', '')} {(it.get('summary') or '')[:400]}")
    return cache

def pr_region(p):
    if p.get("region"): return p["region"]
    area = str(p.get("area") or "").strip()
    if T and callable(getattr(T, "area_to_region", None)):
        try:
            k = T.area_to_region(area)
            if isinstance(k, (list, tuple)): k = k[0] if k else None
            if k: return k
        except Exception: pass
    return _AREA_FALLBACK.get(area.lower())

def pr_regions(p):
    if p.get("regions"): return list(p["regions"])
    k = pr_region(p)
    return [k, *ancestors(k)] if k else []

def is_local(it):
    if it.get("via") == "direct": return True
    if "local" in it: return bool(it.get("local")) and bool(item_regions(it))
    return any(k in set(home_keys()) for k in item_regions(it))

# ----------------------------------------------------------------------------- entries (one shape for originals and items)
def _ts(v):
    f = getattr(TXT, "to_ts", None)
    if f:
        t = f(v)
        if t: return t
    try: return int(v)
    except Exception: pass
    if H:
        try: return H.epoch(H.to_iso(v))
        except Exception: pass
    return int(NOW.timestamp())

def _published_ts(p):
    if H:
        try: return H.epoch(H.published(p))
        except Exception: pass
    return _ts(p.get("published_iso") or p.get("published") or p.get("date"))

def _kind_label(k): return {"press-release": "Press release", "brief": "Brief", "report": "Report", "gov": "Agency", "meeting": "Meeting", "event": "Event", "media": "", "agency": "Agency"}.get(k or "", "")

def _town(regions):
    """Most specific region name in a list (table order puts cities before counties and states)."""
    for k in REGIONS:
        if k in regions and REGIONS[k].get("kind") != "state": return REGIONS[k]["name"]
    for k in regions:
        if k in REGIONS: return REGIONS[k]["name"]
    return "Local"

def entry_pr(p):
    regs = pr_regions(p)
    return {"id": "pr-" + p["slug"], "title": p["title"], "url": f"/press-releases/{p['slug']}/", "summary": clean(p.get("summary") or "", 300),
            "source": p.get("company") or NAME, "ts": _published_ts(p), "kind": p.get("kind") or "press-release", "regions": regs,
            "original": True, "obj": p, "town": _town(regs) if regs else (p.get("area") or "Local")}

def entry_item(it):
    regs = item_regions(it)
    return {"id": it["id"], "title": it["title"], "url": f"/story/{it['slug']}/", "summary": clean(it.get("summary") or "", 300),
            "source": it.get("source") or "Wire report", "ts": int(it.get("ts") or 0) or int(NOW.timestamp()), "kind": it.get("kind") or "",
            "regions": regs, "original": False, "obj": it, "town": _town(regs) if regs else "Local"}

def _dedupe(entries):
    seen, out = set(), []
    for e in sorted(entries, key=lambda e: -e["ts"]):
        k1 = e["id"]; k2 = re.sub(r"\W", "", e["title"].lower())[:60]
        if k1 in seen or k2 in seen: continue
        seen.add(k1); seen.add(k2); out.append(e)
    return out

def _originals(c):
    o = getattr(c, "originals", None)
    if o is None: o = getattr(c, "real_prs", None)
    if o is None: o = [p for p in (getattr(c, "prs", None) or []) if not p.get("example")]
    return [p for p in o if not p.get("example")]

def _items(c): return list(getattr(c, "items", None) or [])

def local_entries(c):
    """Originals + items that are local (DECISIONS §2 rule), newest first, deduped."""
    cache = getattr(c, "_local_entries", None)
    if cache is None:
        cache = _dedupe([entry_pr(p) for p in _originals(c)] + [entry_item(i) for i in _items(c) if is_local(i)])
        try: c._local_entries = cache
        except Exception: pass
    return cache

def region_entries(c, key):
    """Entries whose regions intersect the key's scope (children count toward parents). Unknown keys give []."""
    if key not in REGIONS: return []
    scope = region_scope(key)
    out = [e for e in local_entries(c) if scope & set(e["regions"])]
    if key in ("nevada", "arizona", "colorado-river"):   # state/umbrella hubs also take non-local aggregated items that name them
        seen = {e["id"] for e in out}
        out += [entry_item(i) for i in _items(c) if i["id"] not in seen and scope & set(item_regions(i))]
        out = _dedupe(out)
    return out

def publishers(entries, n=12):
    cnt = {}
    for e in entries:
        if e["original"]: continue
        pub = e["obj"].get("publisher")
        name = (pub.get("name") if isinstance(pub, dict) else pub) or e["source"]
        if name: cnt[name] = cnt.get(name, 0) + 1
    return sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:n]

# ----------------------------------------------------------------------------- events + iCalendar
def _parse_dt(v):
    """Aware datetime (newsroom zone) from a date, datetime, ISO string or epoch; None when unparseable."""
    if v is None or v == "": return None
    if isinstance(v, dt.datetime): return (v if v.tzinfo else v.replace(tzinfo=TZ)).astimezone(TZ)
    if isinstance(v, dt.date): return dt.datetime(v.year, v.month, v.day, tzinfo=TZ)
    if isinstance(v, (int, float)): return dt.datetime.fromtimestamp(v, UTC).astimezone(TZ)
    s = str(v).strip()
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=TZ)).astimezone(TZ)

def _is_dateonly(v): return isinstance(v, dt.date) and not isinstance(v, dt.datetime) or (isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()) is not None)

def _event_fields(src):
    """(start, end, all_day, venue, address, url) from a press release or feed item; supports a nested `event` mapping."""
    ev = src.get("event") if isinstance(src.get("event"), dict) else {}
    g = lambda *ks: next((src[k] for k in ks if src.get(k) not in (None, "")), next((ev[k] for k in ks if ev.get(k) not in (None, "")), None))
    raw_start = g("event_start", "start")
    raw_end = g("event_end", "end")
    start, end = _parse_dt(raw_start), _parse_dt(raw_end)
    if not start: return None
    all_day = bool(g("event_all_day", "all_day")) or _is_dateonly(raw_start)
    if all_day:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        if end: end = end.replace(hour=0, minute=0, second=0, microsecond=0)   # inclusive last day
        if end and end <= start: end = None
    elif end and end <= start:
        end = None
    return start, end, all_day, g("venue", "location"), g("address"), g("event_url", "url")

def _event_end_effective(ev):
    if ev["all_day"]: return (ev["end"] or ev["start"]) + DAY
    return ev["end"] or ev["start"] + dt.timedelta(hours=2)

def _ev_from_pr(p):
    f = _event_fields(p)
    if not f: return None
    start, end, all_day, venue, address, url = f
    k = pr_region(p)
    return {"id": "pr-" + p["slug"], "title": p.get("event_name") or p["title"], "start": start, "end": end, "all_day": all_day,
            "venue": venue, "address": address, "area": k, "area_name": region_name(k) if k else (p.get("area") or ""),
            "url": f"/press-releases/{p['slug']}/", "source_url": url or p.get("source_url"), "ics": f"/press-releases/{p['slug']}.ics",
            "organizer": p.get("company") or NAME, "summary": clean(p.get("summary") or "", 300), "kind": "event", "original": True, "obj": p}

def _ev_from_item(it):
    if it.get("kind") not in ("event", "meeting"): return None
    f = _event_fields(it)
    if not f: return None
    start, end, all_day, venue, address, url = f
    regs = item_regions(it)
    k = next((r for r in REGIONS if r in regs and REGIONS[r].get("kind") != "state"), regs[0] if regs else None)
    eid = it.get("id") or hashlib.sha1(it["link"].encode()).hexdigest()[:14]
    return {"id": eid, "title": it["title"], "start": start, "end": end, "all_day": all_day, "venue": venue, "address": address,
            "area": k, "area_name": region_name(k) if k else "", "url": f"/story/{it['slug']}/" if it.get("slug") else it["link"],
            "source_url": url or it.get("link"), "ics": f"/local/events/{eid}.ics", "organizer": it.get("source") or NAME,
            "summary": clean(it.get("summary") or "", 300), "kind": it["kind"], "original": False, "obj": it}

def events(originals, items=None, now=None):
    """Upcoming events (and ones that ended within the last day) from press releases with event fields and from direct
    feed items of kind event/meeting, sorted by start. Each: {title, start, end, all_day, venue, address, area, area_name,
    url, source_url, ics (= ics_path), organizer, summary, kind, original}."""
    now = _parse_dt(now) if now is not None else NOW.astimezone(TZ)
    out = []
    for p in originals or []:
        if p.get("example"): continue
        try: ev = _ev_from_pr(p)
        except Exception as e: print(f"WARN local event {p.get('slug')}: {e}", file=sys.stderr); ev = None
        if ev: out.append(ev)
    for it in items or []:
        try: ev = _ev_from_item(it)
        except Exception: ev = None
        if ev: out.append(ev)
    keep = [e for e in out if _event_end_effective(e) >= now - DAY]
    seen, res = set(), []
    for e in sorted(keep, key=lambda e: (e["start"], e["title"])):
        if e["id"] in seen: continue
        seen.add(e["id"]); e["ics_path"] = e["ics"]; res.append(e)
    return res

def region_events(evs, key):
    scope = region_scope(key)
    return [e for e in evs if e.get("area") in scope or (e.get("area") and scope & set(ancestors(e["area"]) + [e["area"]]))]

def _ics_text(s):
    return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")

def _fold(line):
    b = line.encode("utf-8")
    if len(b) <= 75: return line
    out, cur = [], b""
    for ch in line:
        cb = ch.encode("utf-8")
        if len(cur) + len(cb) > (75 if not out else 74):
            out.append(cur.decode("utf-8")); cur = b""
        cur += cb
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)

VTIMEZONE = ["BEGIN:VTIMEZONE", f"TZID:{TZ_NAME}", "BEGIN:STANDARD", "DTSTART:19700101T000000", "TZOFFSETFROM:-0700", "TZOFFSETTO:-0700", "TZNAME:MST", "END:STANDARD", "END:VTIMEZONE"]

def ics_event(ev):
    """VEVENT lines for one event dict."""
    stamp = NOW.strftime("%Y%m%dT%H%M%SZ")
    url = SITE + ev["url"] if ev["url"].startswith("/") else ev["url"]
    lines = ["BEGIN:VEVENT", f"UID:{ev['id']}@{SITE.split('//')[-1]}", f"DTSTAMP:{stamp}"]
    if ev["all_day"]:
        lines.append(f"DTSTART;VALUE=DATE:{ev['start']:%Y%m%d}")
        lines.append(f"DTEND;VALUE=DATE:{(ev['end'] or ev['start']) + DAY:%Y%m%d}")
    else:
        s = ev["start"].astimezone(TZ)
        lines.append(f"DTSTART;TZID={TZ_NAME}:{s:%Y%m%dT%H%M%S}")
        if ev["end"]: lines.append(f"DTEND;TZID={TZ_NAME}:{ev['end'].astimezone(TZ):%Y%m%dT%H%M%S}")
    lines.append(f"SUMMARY:{_ics_text(ev['title'])}")
    loc = ", ".join(x for x in (ev.get("venue"), ev.get("address")) if x)
    if loc: lines.append(f"LOCATION:{_ics_text(loc)}")
    lines.append(f"URL:{url}")
    desc = " ".join(x for x in (ev.get("summary"), f"Details: {url}", f"Source: {ev['source_url']}" if ev.get("source_url") else "") if x)
    lines.append(f"DESCRIPTION:{_ics_text(desc)}")
    if ev.get("organizer"): lines.append(f"ORGANIZER;CN={_ics_text(ev['organizer'])}:mailto:{CONTACT}")
    lines += ["STATUS:CONFIRMED", "TRANSP:TRANSPARENT", "END:VEVENT"]
    return lines

def ics_calendar(evs, name):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{NAME}//Events//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_ics_text(name)}", f"X-WR-TIMEZONE:{TZ_NAME}", *VTIMEZONE]
    for ev in evs: lines += ics_event(ev)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"

def _write_raw(path, text):
    f = OUT / path.lstrip("/")
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(text, encoding="utf-8", newline="")

def write_ics(evs):
    for ev in evs: _write_raw(ev["ics"], ics_calendar([ev], ev["title"]))
    _write_raw("/local/events.ics", ics_calendar(evs, f"{NAME}: events along the Colorado River"))

# ----------------------------------------------------------------------------- formatting helpers
def _time(ts, style="rel"):
    f = getattr(TXT, "time_tag", None)
    if f:
        try: return f(ts, style)
        except Exception: pass
    d = dt.datetime.fromtimestamp(ts, UTC)
    return f'<time datetime="{d.replace(microsecond=0).isoformat()}">{d.strftime("%b %d, %Y %H:%M UTC")}</time>'

def _updated(): return f'<p class="meta">Updated {_time(int(NOW.timestamp()), "long")} · refreshed around the clock</p>'
def _iso(ts): return dt.datetime.fromtimestamp(ts, UTC).replace(microsecond=0).isoformat()

def _day_label(d, today):
    if d == today: return "Today"
    if d == today - DAY: return "Yesterday"
    if d == today + DAY: return "Tomorrow"
    return d.strftime("%A, %b %-d") if abs((d - today).days) < 7 else d.strftime("%b %-d, %Y")

def ev_when(ev):
    s, e = ev["start"], ev["end"]
    if ev["all_day"]:
        if e and e.date() != s.date(): return f"{s:%a, %b %-d} – {e:%a, %b %-d} · All day"
        return f"{s:%a, %b %-d} · All day"
    t = lambda x: x.strftime("%-I:%M %p").replace(":00", "")
    if e and e.date() == s.date(): return f"{s:%a, %b %-d} · {t(s)}–{t(e)}"
    if e: return f"{s:%a, %b %-d}, {t(s)} – {e:%a, %b %-d}, {t(e)}"
    return f"{s:%a, %b %-d} · {t(s)}"

# ----------------------------------------------------------------------------- components (shell first, fallback second)
_PK = set(inspect.signature(page).parameters)

def _ldj(n):
    if H and hasattr(H, "ldj"): return H.ldj(n)
    import json
    return '<script type="application/ld+json">' + json.dumps(n, ensure_ascii=False).replace("</", "<\\/") + "</script>"

def _page(c, title, body, desc, path, ld=None, og_img=None, kicker=None, robots=None):
    kw = {"desc": desc, "path": path}
    if "ticker" in _PK: kw["ticker"] = getattr(c, "ticker", "")
    if og_img and "og_img" in _PK: kw["og_img"] = og_img
    if kicker and "kicker" in _PK: kw["kicker"] = kicker
    if robots and "robots" in _PK: kw["robots"] = robots
    if ld:
        if "ld" in _PK: kw["ld"] = ld
        else: kw["extra_head"] = "".join(_ldj(n) for n in ld)
    return page(title, body, **kw)

def _sig_has(fn, name):
    try: return name in inspect.signature(fn).parameters
    except (TypeError, ValueError): return False

def _img_for(e, size):
    if not IM: return ""
    try:
        im = IM.pr_img(e["obj"]) if e["original"] else IM.story_img(e["obj"])
        if not im: return ""
        sizes = "(max-width:640px) 100vw, (max-width:1024px) 66vw, 860px" if size == "lg" else "(max-width:640px) 100vw, (max-width:1024px) 50vw, 420px"
        return IM.img_tag(im, sizes=sizes, small=(size != "lg"), lazy=(size != "lg"))
    except Exception:
        return ""

def _fallback_card(e, size):
    kick = esc(e["town"]) + (f" · {esc(_kind_label(e['kind']))}" if _kind_label(e["kind"]) else "")
    meta = f'<p class="meta"><bdi>{esc(e["source"])}</bdi> · {_time(e["ts"])}</p>'
    if size == "row":
        return f'<article class="card card--row noimg"><div class="cb"><span class="kick t-local">{kick}</span><h3><a href="{esc(e["url"])}">{esc(e["title"])}</a></h3>{meta}</div></article>'
    img = _img_for(e, size)
    thumb = f'<a class="thumb" href="{esc(e["url"])}" tabindex="-1" aria-hidden="true">{img}</a>' if img else ""
    dek = f'<p class="dek">{esc(clean(e["summary"], 200 if size == "lg" else 140))}</p>' if e["summary"] and clean(e["summary"], 60).lower() not in e["title"].lower() else ""
    return f'<article class="card card--{size}">{thumb}<div class="cb"><span class="kick t-local">{kick}</span><h3><a href="{esc(e["url"])}">{esc(e["title"])}</a></h3>{dek}{meta}</div></article>'

def card(e, size="md"):
    """Card for an entry. Originals go through shell/pages.pr_card, items through shell.card (the new shell takes a
    size= keyword and handles originals itself); anything older or missing falls back to plain valid markup."""
    try:
        if e["original"]:
            fn = getattr(S, "pr_card", None) or getattr(PG, "pr_card", None)
            if fn and _sig_has(fn, "size"): return fn(e["obj"], size=size)
            if fn and size != "row": return fn(e["obj"])
        else:
            fn = getattr(S, "card", None)
            if fn and _sig_has(fn, "size"): return fn(e["obj"], size=size)
            if fn and size != "row": return fn(e["obj"])
    except Exception as ex:
        print(f"WARN local card {e['id']}: {ex}", file=sys.stderr)
    return _fallback_card(e, size)

def _more(html, n, step, lid, noun="more"):
    """Hidden-until-clicked tail: items after `n` get .more-item; the button uses app.js's Show N more hook."""
    return f'<div class="more-wrap"><button class="loadmore" type="button" aria-controls="{lid}">Show {min(step, n)} {noun}</button></div>' if n > 0 else ""

def _hide(html): return html.replace('class="card', 'class="card more-item', 1) if 'class="card' in html else html.replace("<article", '<article class="more-item"', 1)

def river(entries, show=RIVER_SHOW, cap=RIVER_CAP, lid="river", cols=True, dividers=True):
    """Chronological list with day dividers (newsroom time) and a Show-more tail. Empty -> ''."""
    entries = entries[:cap]
    if not entries: return ""
    today = NOW.astimezone(TZ).date()
    parts, last, hidden = [], None, 0
    for n, e in enumerate(entries):
        d = dt.datetime.fromtimestamp(e["ts"], UTC).astimezone(TZ).date()
        if dividers and d != last:
            last = d
            parts.append(f'<div class="day{" more-item" if n >= show else ""}">{esc(_day_label(d, today))}</div>')
        h = card(e, "row")
        if n >= show: h = _hide(h); hidden += 1
        parts.append(h)
    cls = "river list" if cols else "list"
    return f'<div class="{cls}" id="{lid}" data-step="{show}" data-noun="more">{"".join(parts)}</div>{_more("", hidden, show, lid)}'

def rows(entries, lid=None):
    if not entries: return ""
    return f'<div class="list"{f" id={chr(34)}{lid}{chr(34)}" if lid else ""}>{"".join(card(e, "row") for e in entries)}</div>'

def _h2id(html, hid):
    """Give the first h2 in a section-header fragment an id (used when the shell header has no id parameter)."""
    return html if f'id="{hid}"' in html else html.replace("<h2>", f'<h2 id="{hid}">', 1)

def chips(pairs, current=None, scroll=False):
    fn = getattr(S, "chips", None)
    if fn:
        try: return fn(pairs, current=current) if _sig_has(fn, "current") else fn(pairs)
        except Exception: pass
    li = "".join(f'<li><a href="{esc(h)}"{" aria-current=" + chr(34) + "page" + chr(34) if h == current else ""}>{esc(l)}</a></li>' for l, h in pairs)
    return f'<ul class="chips{" scroll" if scroll else ""}">{li}</ul>'

def sh(title, href=None, link="More", level=2, color="local", id=None):
    fn = getattr(S, "section_header", None)
    if fn and _sig_has(fn, "tag"):
        try: return fn(title, href, cat=color, more_label=link, tag=f"h{level}", id=id)
        except Exception: pass
    a = f'<a class="link" href="{esc(href)}">{esc(link)}</a>' if href else ""
    idattr = f' id="{esc(id)}"' if id else ""
    return f'<div class="sh t-{color}"><h{level}{idattr}><span class="bar"></span>{esc(title)}</h{level}>{a}</div>'

def crumbs_html(pairs):
    fn = getattr(S, "crumbs_html", None)
    if fn:
        try: return fn(pairs)
        except Exception: pass
    li = "".join(f'<li><a href="{esc(h)}">{esc(l)}</a></li>' if n < len(pairs) - 1 else f'<li aria-current="page">{esc(l)}</li>' for n, (l, h) in enumerate(pairs))
    return f'<nav aria-label="Breadcrumb"><ol class="crumbs">{li}</ol></nav>'

def crumbs_node(pairs):
    if H and hasattr(H, "crumbs"): return H.crumbs(*pairs)
    return {"@type": "BreadcrumbList", "@id": SITE + pairs[-1][1] + "#breadcrumb",
            "itemListElement": [{"@type": "ListItem", "position": n + 1, "name": clean(l, 110), "item": SITE + h} for n, (l, h) in enumerate(pairs)]}

def place_node(key):
    n = None
    if H and hasattr(H, "place_node"):
        try: n = H.place_node(key)
        except Exception: n = None
    if n: return n
    r = REGIONS.get(key)
    if not r: return None
    typ = {"city": "City", "county": "AdministrativeArea", "state": "State"}.get(r.get("kind"), "Place")
    n = {"@type": typ, "name": region_full_name(key)}
    if r.get("wikidata"): n["sameAs"] = "https://www.wikidata.org/wiki/" + str(r["wikidata"]).rsplit("/", 1)[-1]
    if r.get("parent") in REGIONS: n["containedInPlace"] = {"@type": "AdministrativeArea" if REGIONS[r["parent"]].get("kind") in ("county", "state") else "Place", "name": region_full_name(r["parent"])}
    return n

def collection_node(path, name, entries, about=None, desc=None, date_mod=None):
    items = [(e["title"], e["url"]) for e in entries[:50]]
    if H and hasattr(H, "collection_node"):
        try:
            n = H.collection_node(path, name, items, about=about, desc=desc, breadcrumb_id=path, date_mod=date_mod)
            if about and not n.get("about"):
                pl = place_node(about)
                if pl: n["about"] = pl; n["spatialCoverage"] = pl
            return n
        except Exception as ex:
            print(f"WARN local collection_node: {ex}", file=sys.stderr)
    url = SITE + path
    n = {"@type": "CollectionPage", "@id": url + "#webpage", "url": url, "name": clean(name, 110), "isPartOf": {"@id": SITE + "/#website"},
         "breadcrumb": {"@id": url + "#breadcrumb"}, "dateModified": date_mod or NOW.replace(microsecond=0).isoformat(), "inLanguage": "en-US",
         "mainEntity": {"@type": "ItemList", "itemListOrder": "https://schema.org/ItemListOrderDescending", "numberOfItems": len(items),
                        "itemListElement": [{"@type": "ListItem", "position": k + 1, "name": clean(t, 110), "url": SITE + u} for k, (t, u) in enumerate(items)]}}
    if desc: n["description"] = clean(desc, 300)
    pl = place_node(about) if isinstance(about, str) else about
    if pl: n["about"] = pl; n["spatialCoverage"] = pl
    return n

def event_node(ev):
    p = ev["obj"] if ev["original"] else {"slug": ev["id"], "title": ev["title"], "event_start": ev["start"].isoformat(), "event_end": ev["end"].isoformat() if ev["end"] else None,
                                           "venue": ev.get("venue"), "address": ev.get("address"), "summary": ev.get("summary"), "company": ev.get("organizer"), "event_url": ev.get("source_url")}
    if H and hasattr(H, "event_node"):
        try:
            n = H.event_node(p, url=SITE + ev["url"] if ev["url"].startswith("/") else ev["url"])
            if n: return n
        except Exception: pass
    url = SITE + ev["url"] if ev["url"].startswith("/") else ev["url"]
    n = {"@type": "Event", "@id": url + "#event", "name": clean(ev["title"], 110), "startDate": ev["start"].date().isoformat() if ev["all_day"] else ev["start"].isoformat(),
         "url": url, "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
         "location": {"@type": "Place", "name": ev.get("venue") or ev.get("area_name") or NAME}, "organizer": {"@type": "Organization", "name": ev.get("organizer") or NAME}}
    if ev["end"]: n["endDate"] = ev["end"].date().isoformat() if ev["all_day"] else ev["end"].isoformat()
    if ev.get("address"): n["location"]["address"] = ev["address"]
    if ev.get("summary"): n["description"] = ev["summary"]
    return n

def pick_lead(entries, days=7):
    """Lead for a hub: the newest original from the last `days`, else the newest entry (Local is the product)."""
    if not entries: return None
    cut = int(NOW.timestamp()) - days * 86400
    return next((e for e in entries if e["original"] and e["ts"] >= cut), entries[0])

def _empty_events(empty):
    return f'<div class="empty"><p>{empty}</p><a class="btn sm ghost" href="/submit/">Submit an event</a></div>' if empty else ""

def events_html(evs, empty="", limit=8):
    fn = getattr(S, "events_list", None)
    if fn and evs:
        # the shell reads `end` as an instant; for all-day events hand it the end of the last day so today's events survive
        adj = [{**e, "end": ((e["end"] or e["start"]) + DAY - dt.timedelta(minutes=1)) if e["all_day"] else e["end"]} for e in evs[:limit]]
        try:
            html = fn(adj, limit) if _sig_has(fn, "limit") else fn(adj)
            return html or _empty_events(empty)
        except Exception as ex: print(f"WARN local events_list: {ex}", file=sys.stderr)
    if not evs: return _empty_events(empty)
    li = []
    for ev in evs[:limit]:
        where = " · ".join(esc(x) for x in (ev.get("venue"), ev.get("area_name")) if x)
        li.append(f'<li><div class="d" aria-hidden="true"><small>{ev["start"]:%b}</small>{ev["start"].day}</div><div><h3><a href="{esc(ev["url"])}">{esc(ev["title"])}</a></h3>'
                  f'<p class="meta"><time datetime="{ev["start"].date().isoformat() if ev["all_day"] else ev["start"].isoformat()}">{esc(ev_when(ev))}</time>{" · " + where if where else ""}</p>'
                  f'<a class="ics" href="{esc(ev["ics"])}" type="text/calendar">Add to calendar</a></div></li>')
    return f'<ul class="events">{"".join(li)}</ul>'

def cond_strip(c, key=None):
    """conditions.render_strip builds the fragment (classes prefixed cond); shell.cond_strip wraps it in a labelled region."""
    cond = getattr(c, "conditions", None)
    render = getattr(COND, "render_strip", None) if COND else None
    if not cond or not render: return ""
    try: html = render(cond, key) or ""
    except Exception as ex:
        print(f"WARN local cond_strip {key}: {ex}", file=sys.stderr); return ""
    if not html: return ""
    wrap = getattr(S, "cond_strip", None)
    if wrap:
        try: return wrap(html) or html
        except Exception: pass
    return html

def pubs_html(pairs, intro=None):
    if not pairs: return ""
    li = "".join(f'<li><bdi>{esc(n)}</bdi><span>{k}</span></li>' for n, k in pairs)
    return f'<section class="full" aria-labelledby="pubs-h">{sh("From the region’s publishers", "/about/", "About our sources", id="pubs-h")}' \
           f'{f"<p class={chr(34)}meta{chr(34)}>{esc(intro)}</p>" if intro else ""}<ul class="pubs">{li}</ul></section>'

def cta_html(area=None):
    who = f"Agencies, businesses, schools and nonprofits in {area}" if area else "Agencies, businesses, schools and nonprofits along the river"
    return f"""<section class="full ctas" aria-label="Submit news and feeds"><div><h2>Have news to share?</h2><p>{esc(who)} can publish announcements here free of charge. An editor reviews every submission.</p><a class="btn" href="/submit/">Submit news</a></div>
<div><h2>Take the local news with you</h2><p>Follow local originals by RSS or add the events calendar to your phone or desktop calendar app.</p><div class="row"><a class="btn ghost" href="/press-releases/feed.xml">Local RSS</a><a class="btn ghost" href="/local/events.ics" type="text/calendar">Events calendar (.ics)</a></div></div></section>"""

def empty_html(text):
    return f'<div class="empty"><p>{text}</p><a class="btn sm" href="/submit/">Submit news free</a></div>'

def _hub_img(key):
    pick = {"bullhead-city": "bullhead-city", "laughlin": "laughlin-riverfront", "mohave-valley": "bullhead-laughlin", "lake-havasu-city": "lake-havasu", "kingman": "kingman-downtown",
            "mohave-county": "desert-thunderstorm", "needles": "desert-highway", "boulder-city": "boulder-city", "lake-mead": "lake-mead-2", "mesquite": "mesquite", "henderson": "clark-county-govt-center",
            "las-vegas": "las-vegas-strip", "north-las-vegas": "las-vegas-aerial", "clark-county": "clark-county-govt-center", "colorado-river": "davis-dam", "nevada": "hoover-dam", "arizona": "bullhead-colorado-river"}
    imgs = (getattr(IM, "IMG_CFG", None) or {}).get("images") or {} if IM else {}
    im = imgs.get(pick.get(key, ""))
    if not im and IM:
        try: im = IM.pick_img(region_name(key), "local", "hub-" + key)
        except Exception: im = None
    return im

def _figure(im):
    if not im or not IM: return ""
    try: return IM.figure(im, lazy=True)
    except Exception: return ""

def _og(key, title, im):
    fn = getattr(S, "og_for", None)
    if not fn: return None
    try: return fn(f"hub-{key}", title, "local", im)
    except Exception: return None

def _register(c, loc, kind, title, summary, area=None, ts=None, image=None, cat="local"):
    urls = getattr(c, "urls", None)
    if urls is None:
        try: c.urls = urls = []
        except Exception: return
    ts = int(ts or NOW.timestamp())
    urls.append({"loc": loc, "kind": kind, "lastmod": _iso(ts), "title": title, "image": image, "ts": ts, "summary": clean(summary or "", 300), "area": area, "cat": cat})

# ----------------------------------------------------------------------------- intro copy (120-200 words per area)
def intro_html(key, n_items, n_orig):
    r = REGIONS[key]; name = r["name"]; full = region_full_name(key)
    par = r.get("parent")
    kind = r.get("kind")
    where = f" in {region_full_name(par)}" if par in REGIONS and kind in ("city", "area") else ""
    p1 = r.get("intro") or f"{full} is part of the Colorado River region covered by {NAME}."
    what = {"state": f"This page gathers statewide {name} stories that matter to the Colorado River communities: state agencies, the Legislature, courts, elections and utilities, alongside anything the region's own newsrooms report.",
            "county": f"This page gathers news from {name} government and the communities inside it{where}: board and commission decisions, elections, public safety, roads and planning, plus press releases from county departments and local organizations.",
            }.get(kind, f"This page gathers everything {NAME} has about {name}{where}: official notices from city hall, fire and police, schools and utilities, press releases from local organizations, public meetings and events, and headlines from the regional publishers that cover the area.")
    how = (f"Right now it lists {n_items} item{'s' if n_items != 1 else ''}, including {n_orig} local original{'s' if n_orig != 1 else ''} published here. " if n_items else "")
    how += ("Each aggregated headline links to the publisher that reported it; our own press releases, briefs and reports carry the issuing organization and its source. "
            "Items are refreshed around the clock, and the Updated time above shows the last build.")
    links = r.get("links") or []
    lk = ""
    if links:
        lk = "<p>Useful official links: " + ", ".join(f'<a href="{esc(u)}" rel="noopener">{esc(l)}</a>' for l, u in links) + ".</p>"
    submit = f'<p>Agencies, businesses, schools and nonprofits in {esc(name)} can <a href="/submit/">submit news free</a>; an editor reviews every release before it is published.</p>'
    return f"<p>{esc(p1)}</p><p>{esc(what)}</p><p>{esc(how)}</p>{lk}{submit}"

# ----------------------------------------------------------------------------- pages
def render_hub(c, evs):
    homes = home_keys()
    entries = local_entries(c)
    direct = [e for e in entries if not e["original"] and e["obj"].get("via") == "direct"]
    gov = [e for e in direct if e["kind"] in ("gov", "agency")][:8]
    meetings = [e for e in entries if e["kind"] == "meeting"][:6]
    week = [e for e in evs if e["start"] <= NOW.astimezone(TZ) + 7 * DAY]
    lead = pick_lead(entries)
    rest = [e for e in entries if e is not lead][:LATEST_CAP - 1]
    body = [f'<header class="phead"><span class="kick t-local">Local</span><h1><span class="bar t-local"></span>{HUB_TITLE}</h1>'
            f'<p class="lede">Press releases, agency notices, meetings and events from Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mesquite, Boulder City and the rest of the Colorado River corridor, plus the headlines the region’s own publishers are reporting. Pick a community or read the latest below.</p>{_updated()}</header>',
            chips([(region_name(k), f"/local/{k}/") for k in homes]), cond_strip(c, None), '<div class="fp">']
    # Latest local: lead package + events rail
    left = ""
    if lead:
        left = card(lead, "lg") + rows(rest[:7], "latest-rows")
    else:
        left = empty_html("No local items in the last 48 hours. Agencies and businesses along the river can submit news free.")
    right = f'<div class="h3k">Happening this week</div>{events_html(week, "No events listed for the coming week. Know of one? Send it in.")}' \
            + (f'<p class="meta"><a class="link" href="/local/events/">All upcoming events</a></p>' if evs else "")
    body.append(f'<section class="full" aria-labelledby="latest-h">{sh("Latest local", "/press-releases/", "All local originals", id="latest-h")}<div class="secpk"><div>{left}</div><aside>{right}</aside></div></section>')
    if gov or meetings:
        cols = ""
        if gov: cols += f'<div>{sh("From city halls and agencies", level=3)}{rows(gov, "gov-rows")}</div>'
        if meetings: cols += f'<div>{sh("Meetings & agendas", level=3)}{rows(meetings, "meeting-rows")}</div>'
        body.append(f'<section class="full band" aria-label="Official notices and meetings">{cols}</section>')
    # Around the region
    blocks = []
    for k in homes:
        re_ = [e for e in region_entries(c, k) if e is not lead][:3]
        inner = rows(re_) if re_ else f'<p class="meta">Nothing new in {esc(region_name(k))} yet. <a href="/submit/">Submit news</a>.</p>'
        blocks.append(f'<div><div class="h3k"><a href="/local/{k}/">{esc(region_name(k))}</a></div>{inner}</div>')
    body.append(f'<section class="full" aria-labelledby="around-h">{sh("Around the region", id="around-h")}<div class="grid">{"".join(blocks)}</div></section>')
    pubs = publishers(entries)
    body.append(pubs_html(pubs, "Publishers whose headlines appear in the local items above. Every aggregated headline links to the publisher that reported it."))
    body.append(cta_html())
    body.append("</div>")
    ld = [crumbs_node([("Home", "/"), ("Local", "/local/")]), collection_node("/local/", HUB_TITLE, entries, about="colorado-river", desc=HUB_DESC, date_mod=_iso(entries[0]["ts"]) if entries else None)]
    ld += [event_node(e) for e in week[:10]]
    im = _hub_img("colorado-river")
    write("/local/", _page(c, HUB_TITLE, "".join(body), HUB_DESC, "/local/", ld, og_img=_og("local", HUB_TITLE, im), kicker="Local"))
    _register(c, "/local/", "hub", HUB_TITLE, HUB_DESC, None, entries[0]["ts"] if entries else None, (SITE + im["src"]) if im and im.get("src", "").startswith("/") else None)

def render_area(c, key, evs=None):
    """One /local/<key>/ page. Unknown keys render nothing and return None."""
    if key not in REGIONS: return None
    r = REGIONS[key]; name = r["name"]; full = region_full_name(key)
    evs = evs if evs is not None else events(_originals(c), _items(c))
    entries = region_entries(c, key)
    origs = [e for e in entries if e["original"]]
    agg = [e for e in entries if not e["original"]]
    revs = region_events(evs, key)
    title = f"{name} News and Press Releases"
    desc = r.get("desc") or f"{full} news: press releases, agency notices, meetings, events and headlines from local publishers, updated around the clock."
    path = f"/local/{key}/"
    near = nearby(key)
    kick = "Local" + (f" · {region_full_name(key)}" if r.get("kind") != "state" else " · State")
    lede = (r.get("intro") or "").split(". ")[0].rstrip(".") + "." if r.get("intro") else f"News and announcements from {full}."
    body = [crumbs_html([("Home", "/"), ("Local", "/local/"), (name, path)]),
            f'<header class="phead"><span class="kick t-local">{esc(kick)}</span><h1><span class="bar t-local"></span>{esc(name)}</h1><p class="lede">{esc(lede)}</p>{_updated()}</header>']
    if near:
        body.append(f'<nav aria-label="Nearby areas">{chips([(region_name(k), f"/local/{k}/") for k in [key] + near], current=path)}</nav>')
    body.append(cond_strip(c, key))
    body.append('<div class="fp">')
    about = f'<aside class="near" aria-labelledby="about-h"><div class="h3k" id="about-h">About {esc(name)}</div>{_figure(_hub_img(key))}<div class="prose">{intro_html(key, len(entries), len(origs))}</div></aside>'
    lead = pick_lead(entries)
    rest = [e for e in entries if e is not lead][:6]
    if entries:
        left = card(lead, "lg") + rows(rest, "latest-rows")
    else:
        left = empty_html(f"No new items in the last 48 hours. Agencies and businesses in {esc(name)} can submit news free.")
    body.append(f'<section class="full" aria-labelledby="latest-h">{sh(f"Latest in {name}", id="latest-h")}<div class="secpk"><div>{left}</div>{about}</div></section>')
    more_origs = [e for e in origs if e is not lead][:6]
    if more_origs:
        body.append(f'<section class="full" aria-labelledby="orig-h">{sh(f"From {name}", "/press-releases/", "All local originals", id="orig-h")}<div class="grid">{"".join(card(e, "md") for e in more_origs)}</div></section>')
    body.append(f'<section class="full" aria-labelledby="ev-h">{sh("Happening in " + name, "/local/events/", "All events", id="ev-h")}'
                f'{events_html(revs, f"No upcoming events listed for {esc(name)}. Organizers can send one in and it will appear here with an add-to-calendar link.")}</section>')
    tail = [e for e in agg if e is not lead and e not in rest]
    if tail:
        body.append(f'<section class="full" aria-labelledby="hl-h">{sh("Headlines about " + name, id="hl-h")}{river(tail, lid="river")}</section>')
    body.append(pubs_html(publishers(entries), f"Publishers whose headlines mention {name}. Each headline links to the newsroom that reported it."))
    body.append(cta_html(name))
    body.append("</div>")
    ld = [crumbs_node([("Home", "/"), ("Local", "/local/"), (name, path)]),
          collection_node(path, title, entries, about=key, desc=desc, date_mod=_iso(entries[0]["ts"]) if entries else None)]
    ld += [event_node(e) for e in revs[:10]]
    im = _hub_img(key)
    write(path, _page(c, title, "".join(body), desc, path, ld, og_img=_og(key, title, im), kicker="Local"))
    _register(c, path, "hub", title, desc, key, entries[0]["ts"] if entries else None, (SITE + im["src"]) if im and im.get("src", "").startswith("/") else None)
    return path

def render_events_page(c, evs):
    path = "/local/events/"
    title = "Events along the Colorado River"
    desc = "Upcoming public events, open houses, meetings and festivals in Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mesquite, Boulder City and Lake Mead, with add-to-calendar links."
    groups, order = {}, []
    for ev in evs:
        d = ev["start"].date()
        if d not in groups: groups[d] = []; order.append(d)
        groups[d].append(ev)
    today = NOW.astimezone(TZ).date()
    body = [crumbs_html([("Home", "/"), ("Local", "/local/"), ("Events", path)]),
            f'<header class="phead"><span class="kick t-local">Local · Events</span><h1><span class="bar t-local"></span>Events</h1><p class="lede">What is coming up along the river: open houses, meetings, festivals, voting dates and community events from local agencies and organizers. Every listing has an add-to-calendar link; <a href="/local/events.ics" type="text/calendar">subscribe to the whole calendar</a>.</p>{_updated()}</header>']
    if not evs:
        body.append(empty_html("No upcoming events are listed right now. Organizers along the river can submit events free and they appear here with calendar links."))
    for d in order:
        body.append(f'<section aria-labelledby="d-{d.isoformat()}"><h2 class="h3k" id="d-{d.isoformat()}">{esc(_day_label(d, today))} <span class="meta">{d:%b %-d, %Y}</span></h2>{events_html(groups[d], limit=50)}</section>')
    body.append(cta_html())
    ld = [crumbs_node([("Home", "/"), ("Local", "/local/"), ("Events", path)]),
          collection_node(path, title, [{"title": e["title"], "url": e["url"]} for e in evs], about="colorado-river", desc=desc)]
    ld += [event_node(e) for e in evs[:30]]
    write(path, _page(c, title, "".join(body), desc, path, ld, kicker="Local"))
    _register(c, path, "page", title, desc, None, evs[0]["start"].timestamp() if evs else None)

# ----------------------------------------------------------------------------- topics
FALLBACK_TOPICS = {
    "energy": {"label": "Energy & Oil", "projects": ["oil"], "intro": "Oil, gas, electricity and the grid: prices, pipelines, utilities and the power deals, including the data-center agreements reaching Mohave County."},
    "realestate": {"label": "Real Estate & Housing", "projects": ["realestate"], "intro": "Home sales, mortgage rates, rents, construction and zoning, with an eye on the Las Vegas Valley and the Colorado River communities."},
    "smallbiz": {"label": "Small Business", "projects": ["smallbiz"], "intro": "Owners, startups, Main Street and the policies that shape running a business, from chambers of commerce to the SBA."},
    "fed": {"label": "Economy & Fed", "projects": ["fed"], "intro": "The Federal Reserve, interest rates, inflation and the economic data that moves markets and mortgage rates."},
    "ai": {"label": "Artificial Intelligence", "projects": ["ai"], "intro": "AI models, chips, the companies building them and how the technology is reaching work, schools and government."},
    "water": {"label": "Colorado River & Water", "projects": [], "intro": "The river that sustains the region: Lake Mead and Lake Powell levels, Reclamation operations, shortages, negotiations and conservation.",
              "rx": r"\b(?:Colorado River|Lake Mead|Lake Powell|Lake Mohave|water (?:rights|allocation|shortage|cuts|conservation)|drought|Bureau of Reclamation|SNWA|groundwater|aquifer)\b"},
    "elections": {"label": "Elections 2026", "projects": [], "intro": "The Nov. 3 general election and the races, ballot questions, deadlines and voting sites that matter in Nevada and Arizona.",
                  "rx": r"\b(?:election|ballot|voters?|early voting|midterms?|campaign|candidate|polls?|redistricting)\b"},
    "cannabis": {"label": "Cannabis", "projects": ["cannabis"], "intro": "Cannabis policy, dispensaries, rescheduling and the industry in Nevada, Arizona and nationally."},
    "golf": {"label": "Golf", "projects": ["golf"], "intro": "The tours, the majors and the courses, including Mesquite, Laughlin and Las Vegas golf."},
    "media": {"label": "Media & Journalism", "projects": ["media"], "intro": "Newsrooms, press freedom, platforms and the business of news."},
}

def _topics():
    src = getattr(T, "TOPICS", None) if T else None
    labels = {k: l for k, l, _ in (getattr(CFG, "TOPIC_LINKS", None) or [])}
    out = {}
    if src and hasattr(src, "items"):
        for k, v in src.items():
            v = dict(v) if isinstance(v, dict) else {"rx": v} if isinstance(v, str) else {}
            base = dict(FALLBACK_TOPICS.get(k) or {})
            base.update({kk: vv for kk, vv in v.items() if vv not in (None, "", [], ())})
            base.setdefault("label", labels.get(k) or v.get("name") or k.replace("-", " ").title())
            base.setdefault("intro", ""); base.setdefault("projects", [])
            out[k] = base
    else:
        for k, v in FALLBACK_TOPICS.items(): out[k] = dict(v)
        for k, l, _ in (getattr(CFG, "TOPIC_LINKS", None) or []):
            out.setdefault(k, {"label": l, "intro": "", "projects": []})
    return out

def topic_items(c, key, topic, days=7):
    cut = int(NOW.timestamp()) - days * 86400
    rx = re.compile(topic["rx"], re.I) if topic.get("rx") and not T else None
    projs = set(topic.get("projects") or [])
    if T and hasattr(T, "PROJECT_TOPIC"):
        projs |= {p for p, t in T.PROJECT_TOPIC.items() if t == key}
    out = []
    for it in _items(c):
        if int(it.get("ts") or 0) < cut: continue
        if "topics" in it and isinstance(it["topics"], (list, tuple)):
            hit = key in it["topics"] or bool(projs & set(it.get("projects") or []))
        else:
            hit = bool(projs & set(it.get("projects") or [])) or bool(rx and rx.search(f"{it['title']} {(it.get('summary') or '')[:300]}"))
        if hit: out.append(entry_item(it))
    return _dedupe(out)

def render_topics(c):
    topics = _topics()
    counts, built = {}, []
    for key, t in topics.items():
        ents = topic_items(c, key, t)
        counts[key] = len(ents)
        if not ents: continue
        path = f"/topic/{key}/"; label = t["label"]
        desc = clean(t.get("intro") or f"{label} headlines on {NAME}.", 155)
        body = [crumbs_html([("Home", "/"), ("Topics", "/topic/"), (label, path)]),
                f'<header class="phead"><span class="kick t-{esc(key)}">Topic</span><h1><span class="bar t-{esc(key)}"></span>{esc(label)}</h1>'
                + (f'<p class="lede">{esc(t["intro"])}</p>' if t.get("intro") else "") + _updated() + "</header>",
                f'<p class="meta">{len(ents)} headline{"s" if len(ents) != 1 else ""} from the last 7 days. Each links to the publisher that reported it.</p>',
                river(ents, lid="river"),
                f'<nav aria-label="Other topics">{chips([(tt["label"], f"/topic/{k}/") for k, tt in topics.items() if counts.get(k, 1)], current=path)}</nav>']
        ld = [crumbs_node([("Home", "/"), ("Topics", "/topic/"), (label, path)]), collection_node(path, label, ents, desc=desc, date_mod=_iso(ents[0]["ts"]))]
        write(path, _page(c, label, "".join(body), desc, path, ld, kicker="Topic"))
        _register(c, path, "section", label, desc, None, ents[0]["ts"], None, cat=key)
        built.append(key)
    # index at /topic/ (nav target) and /topics/ (same page, canonical /topic/)
    title, desc = "Topics", "Topic pages on Ground Level News: energy, housing, small business, the Fed, AI, water, elections and more, each with the last week of headlines."
    li = "".join((f'<li><a href="/topic/{k}/">{esc(t["label"])}</a> <span class="meta">{counts[k]} this week</span>' if counts.get(k) else f'<li>{esc(t["label"])} <span class="meta">nothing this week</span>')
                 + (f'<p class="meta">{esc(t["intro"])}</p>' if t.get("intro") else "") + "</li>" for k, t in topics.items())
    body = [crumbs_html([("Home", "/"), ("Topics", "/topic/")]),
            f'<header class="phead"><span class="kick">Topics</span><h1><span class="bar"></span>Topics</h1><p class="lede">Cross-section topic pages built from the last seven days of headlines. Topics cut across sections: energy shows up in Markets and World, housing in Business and Politics.</p>{_updated()}</header>',
            f'<ul class="aside-list">{li}</ul>']
    ld = [crumbs_node([("Home", "/"), ("Topics", "/topic/")]), collection_node("/topic/", title, [{"title": topics[k]["label"], "url": f"/topic/{k}/"} for k in built], desc=desc)]
    html = _page(c, title, "".join(body), desc, "/topic/", ld)
    write("/topic/", html); write("/topics/", html)
    _register(c, "/topic/", "page", title, desc, None, None, None, cat=None)
    return built

# ----------------------------------------------------------------------------- entry point
def render_local(c):
    """Writes /local/, every area hub, /local/events/ (+ .ics files), /topic/<key>/ and /topic/. Never fetches."""
    evs = events(_originals(c), _items(c))
    write_ics(evs)
    render_hub(c, evs)
    built = []
    for key in hub_keys():
        try:
            if render_area(c, key, evs): built.append(key)
        except Exception as e:
            print(f"WARN local hub {key}: {e}", file=sys.stderr)
    render_events_page(c, evs)
    topics = render_topics(c)
    print(f"local: hub + {len(built)} area hubs, {len(evs)} events, {len(topics)} topic pages")
    return {"areas": built, "events": evs, "topics": topics}
