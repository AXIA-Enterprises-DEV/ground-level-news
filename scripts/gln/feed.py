"""Upstream feed loading (news-tracker JSON) and press-release loading.

load_items(): fetch latest.json + the two newest day files with retries; FeedError when the tracker is unreachable or
fewer than MIN_ITEMS tracker items survive (the build must fail rather than deploy an empty site); every item runs
through taxonomy.process (title hygiene, publisher, quality gate, clean summary, categorize, regions, topics, score);
direct regional items from gln.sources are merged, deduped by link and cluster key, clustered and returned newest first.

Every returned item carries: id, slug, title, link, source, summary, cat, section, kind, ts, ts_est, date, regions, local,
state_local, region, topics, publisher{name,home,domain,tier,paywalled}, tier, paywalled, lang, quality, demoted,
quality_reasons, score, also, cluster, cluster_size, cluster_rep, via, label, projects, category (upstream), tickers.

load_prs(): press releases / briefs / reports with validated front matter (hard, file-named errors), published_iso + ts,
kind, region/regions, nh3-sanitised body, Markdown twin text and an event dict when event_start is present."""
import re, sys, json, hashlib, pathlib, datetime as dt, inspect
import requests, yaml, markdown
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .config import ROOT, SRC, BLOCK, CAT_NAME, HIDE_CATS, MIN_ITEMS, MAX_ITEMS, SOURCES_DISABLED, FEED_TIMEOUT, NOW
from .text import clean, slugify, to_ts, iso
from . import taxonomy as T

try:
    import nh3
except ImportError:  # pragma: no cover - requirements.txt lists nh3; fail loudly at load_prs time
    nh3 = None

BUILD_TS = int(NOW.timestamp())


class FeedError(RuntimeError):
    """The upstream tracker could not be read, or too little survived: the build must stop (keep the last good deploy)."""


class PressReleaseError(ValueError):
    """A press-release file has invalid front matter; the message names the file."""


# ---------------------------------------------------------------- fetching
_session = None
def session():
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",), raise_on_status=False)
        s.mount("https://", HTTPAdapter(max_retries=retry)); s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers["User-Agent"] = "GroundLevelNews/1.0 (+https://groundlevelnews.com; news@groundlevelnews.com)"
        _session = s
    return _session

def get_json(path, required=False):
    """JSON document from the tracker. TRACKER_BASE may be a local directory (offline builds, tests). Returns None on a
    missing optional document; raises FeedError when a required one cannot be read."""
    try:
        if "://" not in SRC:
            f = pathlib.Path(SRC) / path
            if not f.exists():
                if required: raise FeedError(f"{f} does not exist")
                return None
            return json.loads(f.read_text(encoding="utf-8"))
        r = session().get(f"{SRC}/{path}", timeout=FEED_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except FeedError:
        raise
    except Exception as e:
        if required: raise FeedError(f"cannot fetch {SRC}/{path}: {e}") from e
        print(f"WARN fetch {path}: {e}", file=sys.stderr); return None


# ---------------------------------------------------------------- items
def _coerce_ts(it):
    ts = to_ts(it.get("ts"))
    if ts is None or ts <= 0 or ts > BUILD_TS + 86400:
        it["ts"], it["ts_est"] = BUILD_TS, True
    else:
        it["ts"], it["ts_est"] = int(ts), False
    it["date"] = iso(it["ts"])

def _finish(it):
    """Keys every item must have, whatever its origin."""
    it.setdefault("kind", "story")
    it.setdefault("via", "tracker")
    it.setdefault("projects", []); it.setdefault("tickers", [])
    it.setdefault("label", None); it.setdefault("also", [])
    it.setdefault("cluster", None); it.setdefault("cluster_size", 1); it.setdefault("cluster_rep", True)
    it["title"] = clean(it["title"], 200)
    it["summary"] = clean(it.get("summary"), 420)
    if it["cat"] not in CAT_NAME: it["cat"] = it.get("section") if it.get("section") in CAT_NAME else "us"
    it["id"] = str(it.get("id") or hashlib.sha1(it["link"].encode()).hexdigest()[:14])
    it["slug"] = it.get("slug") or f"{slugify(it['title'])}-{it['id'][:6]}"
    return it

def _blocked(it):
    return bool(BLOCK.search(" ".join(str(it.get(k) or "") for k in ("title", "summary", "source", "link"))))

def _process_tracker(raw, now_ts):
    """Raw tracker rows -> annotated, kept items (dropped ones are returned separately for reporting)."""
    kept, dropped = {}, []
    for it in raw:
        if not isinstance(it, dict) or not it.get("title") or not it.get("link"): continue
        if it.get("category") in HIDE_CATS: continue
        it = dict(it)
        it["id"] = str(it.get("id") or hashlib.sha1(it["link"].encode()).hexdigest()[:14])
        if it["id"] in kept: continue
        _coerce_ts(it)
        out = T.process(it, now_ts)
        if _blocked(out) or not out["keep"]:
            dropped.append(out); continue
        kept[out["id"]] = _finish(out)
    return list(kept.values()), dropped

def _process_direct(raw, now_ts):
    out = []
    for it in raw:
        if not isinstance(it, dict) or not it.get("title") or not it.get("link"): continue
        it = dict(it); it["via"] = "direct"; it.setdefault("cat", "local")
        _coerce_ts(it)
        if it.get("ts_est") and it.get("published"): it["ts"] = to_ts(it["published"]) or it["ts"]; it["ts_est"] = False; it["date"] = iso(it["ts"])
        a = T.process(it, now_ts)
        if _blocked(a) or not a["keep"]: continue
        a["cat"] = "local"; a["local"] = True if a.get("regions") else a.get("local", False)
        if not a.get("regions"):  # a direct feed with no region config and no mention: keep but it is not Local
            a["local"] = False; a["cat"] = a["section"]
        out.append(_finish(a))
    return out

def load_local_items():
    """Direct regional items from gln.sources (another agent's module); [] when disabled, missing or failing."""
    if SOURCES_DISABLED: return []
    try:
        from . import sources
    except Exception as e:
        print(f"WARN sources module unavailable: {e}", file=sys.stderr); return []
    try:
        fn = sources.load_local_items
        params = inspect.signature(fn).parameters
        items = fn(T) if params else fn()
        return [i for i in (items or []) if isinstance(i, dict)]
    except Exception as e:
        print(f"WARN local sources failed: {e}", file=sys.stderr); return []

def load_items(now_ts=None):
    """(items newest first, manifest). See the module docstring for the per-item contract."""
    now_ts = int(now_ts or BUILD_TS)
    lst = get_json("data/latest.json", required=True)
    if not isinstance(lst, list): raise FeedError("latest.json is not a list")
    man = get_json("data/manifest.json") or {}
    if not isinstance(man, dict): man = {}
    for day in (man.get("days") or [])[:2]:
        d = get_json(f"data/days/{day}.json")
        if isinstance(d, dict): d = d.get("items", [])
        lst += d or []
    items, dropped = _process_tracker(lst, now_ts)
    if len(items) < MIN_ITEMS:
        raise FeedError(f"only {len(items)} tracker items survived (MIN_ITEMS={MIN_ITEMS}; {len(lst)} raw, {len(dropped)} dropped): refusing to build an empty site")
    local = _process_direct(load_local_items(), now_ts)
    # dedupe across both pools by link, id and exact cluster key (same day); direct regional items win over tracker copies
    seen_link, seen_key, seen_id, merged = set(), set(), set(), []
    for it in local + items:
        link = re.sub(r"[?#].*$", "", (it.get("link") or "").strip().lower().rstrip("/"))
        day = dt.datetime.fromtimestamp(it["ts"], dt.timezone.utc).date().isoformat()
        key = (day, T.cluster_key(it["title"]))
        if link in seen_link or it["id"] in seen_id or (key[1] and key in seen_key): continue
        seen_link.add(link); seen_id.add(it["id"]); seen_key.add(key); merged.append(it)
    merged.sort(key=lambda x: -x["ts"])
    tracker = [i for i in merged if i["via"] != "direct"][:MAX_ITEMS]
    direct = [i for i in merged if i["via"] == "direct"]
    merged = sorted(tracker + direct, key=lambda x: -x["ts"])
    T.cluster(merged)
    for it in merged: it["score"] = T.score(it, now_ts, it.get("cluster_size") or 1)
    for it in merged:  # representative = best score inside the cluster after the final scoring pass
        grp = [it] + it["also"]
        best = max(grp, key=lambda i: (i["score"], -i["tier"], i["ts"]))
        it["cluster_rep"] = it is best
    load_items.stats = {"raw": len(lst), "dropped": len(dropped), "kept": len(items), "direct": len(local), "merged": len(merged),
                        "demoted": sum(1 for i in merged if i["demoted"]), "local": sum(1 for i in merged if i["local"]),
                        "drop_reasons": _count(r for d in dropped for r in (d.get("quality_reasons") or ["blocked"])),
                        "sections": _count(i["section"] for i in merged), "upstream": _count(i.get("category") or "?" for i in merged),
                        "moved": sum(1 for i in merged if i.get("category") and i["category"] != i["section"] and i["via"] != "direct")}
    return merged, man

def _count(seq):
    out = {}
    for k in seq: out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ---------------------------------------------------------------- press releases
PR_DIR = ROOT / "content/press-releases"
KINDS = {"press-release", "brief", "report"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Allowlist per DECISIONS §12 (+ code/pre/sup so fenced code and footnote markers survive); img only for /img/ paths.
ALLOWED_TAGS = {"p", "a", "strong", "em", "ul", "ol", "li", "h2", "h3", "blockquote", "br", "hr", "table", "thead", "tbody", "tr", "th", "td", "img", "code", "pre", "sup"}
ALLOWED_ATTRS = {"a": {"href", "title"}, "img": {"src", "alt"}, "th": {"align"}, "td": {"align"}}
MD_EXT = ["tables", "footnotes", "fenced_code", "sane_lists"]   # no attr_list, no md_in_html

def _attr_filter(tag, attr, value):
    if tag == "img" and attr == "src":
        return value if re.match(r"^/img/[\w\-./]+$", value or "") else None
    if tag == "a" and attr == "href" and re.match(r"^\s*(?:javascript|data|vbscript):", value or "", re.I):
        return None
    return value

def sanitize_html(raw):
    """Press-release body HTML through nh3 with the DECISIONS §12 allowlist; javascript: URLs and scripts are removed."""
    if nh3 is None: raise RuntimeError("nh3 is required to sanitise press-release bodies (pip install nh3)")
    out = nh3.clean(raw or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, url_schemes={"http", "https", "mailto", "tel"},
                    link_rel="noopener", strip_comments=True, attribute_filter=_attr_filter)
    return re.sub(r"<img(?![^>]*\bsrc=)[^>]*>", "", out)   # an <img> whose src was rejected is removed entirely

def _parse_dt(v, name, fname, fallback_date=None):
    """ISO datetime -> (iso string with offset, epoch). Naive values are Arizona time (-07:00)."""
    if v is None or v == "":
        if fallback_date is None: return None, None
        v = f"{fallback_date}T12:00:00-07:00"
    if isinstance(v, dt.datetime): d = v
    elif isinstance(v, dt.date): d = dt.datetime(v.year, v.month, v.day, 12)
    else:
        try: d = dt.datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        except ValueError: raise PressReleaseError(f"{fname}: invalid {name} {v!r} (use ISO 8601, e.g. 2026-10-13T09:00:00-07:00)")
    if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone(dt.timedelta(hours=-7)))
    return d.isoformat(), int(d.timestamp())

def parse_pr(path):
    """One press-release file -> dict. Raises PressReleaseError (naming the file) for a BOM, missing title or a bad date."""
    fname = path.name
    txt = path.read_text(encoding="utf-8")
    if txt.startswith("﻿"): raise PressReleaseError(f"{fname}: file starts with a UTF-8 BOM; save it without one")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
    if not m: raise PressReleaseError(f"{fname}: missing YAML front matter (--- block)")
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise PressReleaseError(f"{fname}: front matter is not valid YAML: {e}")
    if not isinstance(fm, dict): raise PressReleaseError(f"{fname}: front matter must be a mapping")
    p = dict(fm)
    title = clean(p.get("title"))
    if not title: raise PressReleaseError(f"{fname}: missing title")
    p["title"] = title
    date = p.get("date", path.stem[:10])
    date_s = date.isoformat() if isinstance(date, (dt.date, dt.datetime)) else str(date).strip()
    if isinstance(date, dt.datetime): date_s = date.date().isoformat()
    if not _DATE.match(date_s): raise PressReleaseError(f"{fname}: invalid date {date!r} (use YYYY-MM-DD)")
    try: dt.date.fromisoformat(date_s)
    except ValueError: raise PressReleaseError(f"{fname}: invalid date {date!r}")
    p["date"] = date_s
    kind = str(p.get("kind") or "press-release").strip().lower()
    if kind not in KINDS:
        print(f"WARN {fname}: unknown kind {kind!r}; using press-release", file=sys.stderr); kind = "press-release"
    p["kind"] = kind
    p["published_iso"], p["ts"] = _parse_dt(p.get("published"), "published", fname, fallback_date=date_s)
    p["published"] = p["published_iso"]
    p["ts_est"] = False
    upd_iso, upd_ts = _parse_dt(p.get("updated"), "updated", fname)
    if upd_iso: p["updated_iso"], p["updated_ts"] = upd_iso, upd_ts
    p["example"] = bool(p.get("example"))
    p["slug"] = path.stem
    p["summary"] = clean(p.get("summary"))
    p["company"] = clean(p.get("company")); p["contact"] = clean(p.get("contact")); p["area"] = clean(p.get("area"))
    p["author"] = clean(p.get("author")) or None
    tags = p.get("tags") or []
    p["tags"] = [clean(t) for t in (tags if isinstance(tags, list) else [tags]) if clean(t)]
    body_md = m.group(2).strip()
    p["md"] = body_md
    p["body"] = sanitize_html(markdown.markdown(body_md, extensions=MD_EXT))
    # regions: area -> key, plus anything the title/summary/venue names, plus parents
    p["region"] = T.area_to_region(p["area"])
    text = " ".join(str(p.get(k) or "") for k in ("title", "summary", "area", "venue", "address"))
    regions = ([p["region"]] if p["region"] else []) + T.detect_regions(text)
    for k in list(regions): regions += T.region_parents(k)
    p["regions"] = T._ordered(k for k in regions if k in T.REGIONS)
    p["local"] = True; p["cat"] = "local"; p["section"] = "local"
    p["topics"] = T.detect_topics({"title": p["title"], "summary": p["summary"], "projects": []})
    p["lang"] = "en"
    # event
    if p.get("event_start"):
        s_iso, s_ts = _parse_dt(p["event_start"], "event_start", fname)
        e_iso, e_ts = _parse_dt(p.get("event_end"), "event_end", fname)
        p["event"] = {"start": s_iso, "end": e_iso, "start_ts": s_ts, "end_ts": e_ts, "all_day": bool(p.get("event_all_day")),
                      "venue": clean(p.get("venue")) or None, "address": clean(p.get("address")) or None, "url": (str(p.get("event_url") or "").strip() or None)}
        p["event_start"], p["event_end"] = s_iso, e_iso
    else:
        p["event"] = None
    return p

def load_prs(directory=None):
    """All press releases / briefs / reports: real originals newest first (by published), example templates last."""
    prs = []
    for f in sorted(pathlib.Path(directory or PR_DIR).glob("*.md")):
        prs.append(parse_pr(f))
    real = sorted([p for p in prs if not p["example"]], key=lambda p: -p["ts"])
    examples = sorted([p for p in prs if p["example"]], key=lambda p: -p["ts"])
    return real + examples
