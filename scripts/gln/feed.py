"""Upstream feed loading (news-tracker JSON) and press-release loading, plus source normalization."""
import re, sys, json, hashlib, pathlib, requests, yaml, markdown
from .config import ROOT, SRC, BLOCK, CAT_NAME, LOCAL_PROJECTS, HIDE_CATS
from .text import clean, slugify

# Feed source names are often feed titles; show the publisher instead.
SOURCE_NAMES = {
    "World News, Today World News, Latest International News, World Breaking News, Trending News of World - Times of India": "Times of India",
    "Phys.org - latest science and technology news stories": "Phys.org", "www.theregister.com - Articles": "The Register",
    "Engadget - Technology News & Expert Reviews": "Engadget", "Fortune | FORTUNE": "Fortune", "Forbes - Business": "Forbes",
    "News - Cryptonews": "Cryptonews", "Cointelegraph.com News": "Cointelegraph", "NYT > Technology": "NYT Technology",
    "Money Saving Mom®": "Money Saving Mom", "FT Home": "Financial Times", "Seeking Alpha Market Currents": "Seeking Alpha",
    "MarketWatch Top Stories": "MarketWatch", "CNBC Top News": "CNBC", "Investing.com Stock Market": "Investing.com",
    "Investing.com Economic Indicators": "Investing.com", "START (UMD) Terrorism Research": "START (UMD)",
    "NY Fed Liberty Street Economics": "New York Fed", "All News": "Investing.com",
}
def tidy_source(it):
    """Clean up the source name; Google News items carry the publisher at the end of the title."""
    src = (it.get("source") or "").strip()
    if src.startswith(("Google News", "Top stories - Google News")):
        m = re.match(r"^(.*\S)\s+[-–]\s+([^-–]{2,60})$", it["title"])
        if m: it["title"], src = m.group(1), m.group(2).strip()
        else: src = "Google News"
    elif src.startswith("PR Newswire"): src = "PR Newswire"
    it["source"] = SOURCE_NAMES.get(src, src) or "Wire report"

def get_json(path):
    """Fetch a JSON document from the tracker. TRACKER_BASE may also be a local directory (offline builds, tests)."""
    try:
        if "://" not in SRC:
            f = pathlib.Path(SRC) / path
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        r = requests.get(f"{SRC}/{path}", timeout=30); r.raise_for_status(); return r.json()
    except Exception as e:
        print(f"WARN fetch {path}: {e}", file=sys.stderr); return None

def load_items():
    items = {}
    lst = get_json("data/latest.json") or []
    man = get_json("data/manifest.json") or {}
    for day in (man.get("days") or [])[:2]:
        d = get_json(f"data/days/{day}.json")
        if isinstance(d, dict): d = d.get("items", [])
        lst += d or []
    for it in lst:
        if not isinstance(it, dict) or not it.get("title") or not it.get("link"): continue
        if it.get("category") in HIDE_CATS: continue
        if re.search(r"\b(8-K|10-Q|10-K|S-1|424B|Form 4|SC 13)\b", it["title"]): continue
        key = it.get("id") or hashlib.sha1(it["link"].encode()).hexdigest()[:14]
        it["id"] = key
        it["ts"] = int(it.get("ts") or 0)
        it["title"] = clean(it["title"], 200)
        it["summary"] = clean(it.get("summary"), 420)
        tidy_source(it)
        if BLOCK.search(" ".join([it["title"], it["summary"], it["source"], it["link"]])): continue
        if len(re.findall(r"[\u0400-\u04ff\u0600-\u06ff\u3040-\u30ff\u4e00-\u9fff]", it["title"])) > len(it["title"]) * .2: continue  # non-English
        cat = it.get("category") or "us"
        if LOCAL_PROJECTS & set(it.get("projects") or []): it["local"] = True
        it["cat"] = cat if cat in CAT_NAME else "us"
        it["slug"] = f"{slugify(it['title'])}-{key[:6]}"
        items.setdefault(key, it)
    out = sorted(items.values(), key=lambda x: -x["ts"])
    # de-dup near identical titles
    seen, res = set(), []
    for it in out:
        k = re.sub(r"\W", "", it["title"].lower())[:60]
        if k in seen: continue
        seen.add(k); res.append(it)
    return res[:1500], man

def load_prs():
    prs = []
    for p in sorted((ROOT/"content/press-releases").glob("*.md"), reverse=True):
        txt = p.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", txt, re.S)
        if not m: print(f"WARN bad frontmatter {p.name}", file=sys.stderr); continue
        fm = yaml.safe_load(m.group(1)) or {}
        fm["body"] = markdown.markdown(m.group(2), extensions=["extra"])
        fm["md"] = m.group(2).strip()
        fm["slug"] = p.stem
        fm["date"] = str(fm.get("date", p.stem[:10]))
        prs.append(fm)
    prs.sort(key=lambda x: (bool(x.get("example")), x["date"]), reverse=False)
    real = sorted([x for x in prs if not x.get("example")], key=lambda x: x["date"], reverse=True)
    return real + [x for x in prs if x.get("example")]
