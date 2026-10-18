"""Page renderers: homepage, section fronts, story pages, press-release index + pages (+ .ics), 404. Owned by UI.
/about/ and /submit/ live in editorial.py; /local/, /local/<area>/ and /topic/<key>/ in local.py (they reuse shell components)."""
import re, sys, collections, datetime as dt, importlib
from . import config as CFG
from .config import OUT, SITE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME
from . import text as T
from .text import esc, clean, iso
from .images import story_img, pr_img, img_tag, credit, figure, reset_recent, has_photo, cat_img
from . import head as H
from .shell import (page, card, pr_card, rows, section_header, chips, grid, write, og_for, OG_STORIES, events_list, cond_strip, crumbs_html,
                    region_name, item_area, pr_region, area_href, set_justin, fmt_date, time_tag, tile, KIND_LABEL, LOCAL_AREAS, TOPIC_LINKS, REGIONS, TX)

CAT_DESC = getattr(CFG, "CAT_DESC", {}) or {}
CAT_TITLE = getattr(CFG, "CAT_TITLE", {}) or {}
CAT_TABS = getattr(CFG, "CAT_TABS", {}) or {}
CAT_SHORT = getattr(CFG, "CAT_SHORT", None) or {**CAT_NAME, "tech": "Tech"}
NOINDEX = getattr(H, "NOINDEX", "noindex,follow,max-image-preview:large")
HOME_H1 = "Ground Level News: local news for Bullhead City, Laughlin and the Colorado River, plus U.S. and world headlines"
HOME_AREAS = [(l, h) for k, l, h in LOCAL_AREAS if k in ("bullhead-city", "laughlin", "mohave-valley", "lake-havasu-city", "kingman", "clark-county", "mesquite", "boulder-city")] or [(l, h) for _, l, h in LOCAL_AREAS[:8]]

def _opt(mod, attr):
    try: return getattr(importlib.import_module(f"gln.{mod}"), attr, None)
    except Exception: return None
_LOCAL_MOD = None
try:
    _LOCAL_MOD = importlib.import_module("gln.local")
except Exception:
    _LOCAL_MOD = None

# ---------- shared helpers ----------
def _originals(c): return list(getattr(c, "originals", None) or getattr(c, "real_prs", None) or [p for p in getattr(c, "prs", []) if not p.get("example")])
def _reg(c, loc, kind, title, lastmod=None, image=None, ts=None, summary="", area=None, cat=None):
    urls = getattr(c, "urls", None)
    if urls is None: return
    urls.append({"loc": loc, "kind": kind, "lastmod": lastmod or H.BUILD_ISO if hasattr(H, "BUILD_ISO") else iso(0), "title": title, "image": image,
                 "ts": int(ts or NOW.timestamp()), "summary": clean(summary or "", 300), "area": area, "cat": cat})
def _rank(items):
    fn = getattr(TX, "rank", None)
    if fn:
        try: return list(fn(list(items)))
        except Exception as e: print(f"WARN rank: {e}", file=sys.stderr)
    # fallback: recency with a boost for a real summary and a keyword-matched photo
    now = int(NOW.timestamp())
    def score(i):
        age = max(0, now - int(i.get("ts") or 0)) / 3600
        return -(age) + (6 if i.get("summary") else 0) + (4 if has_photo(i) else 0) + (3 if i.get("local") else 0) + 2 * min(3, len(i.get("also") or []))
    return sorted(items, key=score, reverse=True)
def _pr_ts(p): return p.get("ts") or T.to_ts(p.get("published_iso") or p.get("published") or p.get("date")) or int(NOW.timestamp())
def _pr_event(p):
    """Normalised event dict for an original ({start,end,all_day,venue,address,url}) or None."""
    e = p.get("event") if isinstance(p.get("event"), dict) else None
    start = (e or {}).get("start") or p.get("event_start")
    if not start: return None
    return {"start": start, "end": (e or {}).get("end") or p.get("event_end"), "all_day": bool((e or {}).get("all_day", p.get("event_all_day"))),
            "venue": (e or {}).get("venue") or p.get("venue"), "address": (e or {}).get("address") or p.get("address"), "url": (e or {}).get("url") or p.get("event_url")}
def _events(c):
    """Upcoming events: local.events(c.originals) when available, else derived from the originals' event fields."""
    fn = getattr(_LOCAL_MOD, "events", None)
    if fn:
        try:
            ev = fn(_originals(c))
            if ev: return [dict(e, area=e.get("area") or e.get("region")) for e in ev]
        except Exception as e: print(f"WARN local.events: {e}", file=sys.stderr)
    out = []
    for p in _originals(c):
        e = _pr_event(p)
        if not e: continue
        out.append({"title": p["title"], "start": e["start"], "end": e["end"], "all_day": e["all_day"], "venue": e["venue"], "area": pr_region(p),
                    "url": f"/press-releases/{p['slug']}/", "ics": f"/press-releases/{p['slug']}.ics"})
    return out
def _cond_html(c):
    cond = getattr(c, "conditions", None)
    if not cond: return ""
    for name in ("render_strip", "strip_html", "render_conditions", "render"):
        fn = _opt("conditions", name)
        if fn:
            try: return fn(cond) or ""
            except Exception as e: print(f"WARN conditions strip: {e}", file=sys.stderr); return ""
    return ""
def _pub_name(i): return (i.get("publisher") or {}).get("name") or i.get("source") or "Wire report"
def _pub_domain(i):
    d = (i.get("publisher") or {}).get("domain")
    if d: return d
    m = re.match(r"https?://(?:www\.)?([^/]+)", i.get("link") or "")
    return m.group(1).lower() if m else ""
def _day_label(ts):
    d = T._dt(ts).astimezone(T.TZ).date(); today = NOW.astimezone(T.TZ).date()
    if d == today: return "Today"
    if d == today - dt.timedelta(days=1): return "Yesterday"
    return T._dt(ts).astimezone(T.TZ).strftime("%A, %b %-d")
def _crumb_nodes(*pairs):
    fn = getattr(H, "crumbs", None)
    return fn(*pairs) if fn else None
def _node(name, *a, **kw):
    fn = getattr(H, name, None)
    if not fn: return None
    try: return fn(*a, **kw)
    except Exception as e: print(f"WARN head.{name}: {e}", file=sys.stderr); return None

# ---------- homepage (DECISIONS §4, ux.md §18) ----------
def render_home(c):
    reset_recent()
    items = list(c.items); by = c.by; originals = _originals(c); man = getattr(c, "man", {}) or {}
    used = set()
    def take(lst, n, pred=None):
        out = []
        for i in lst:
            if i["id"] in used or (pred and not pred(i)): continue
            out.append(i); used.add(i["id"])
            if len(out) == n: break
        return out
    # Showcase slots (lead, secondary, briefs, top headlines, Latest): real news items from established publishers,
    # one representative per story cluster, never calendar listings or demoted items.
    _news = lambda i: (i.get("kind") not in ("event", "meeting") and not i.get("demoted") and i.get("cluster_rep", True)
                       and ((i.get("tier") or 4) <= 3 or i.get("local")))
    ranked = [i for i in _rank(items) if _news(i)]
    if ranked:   # the lead slot prefers a keyword-matched photo among the top three ranked items
        k_lead = next((i for i in ranked[:3] if has_photo(i)), ranked[0]); ranked.remove(k_lead); ranked.insert(0, k_lead)
    lead = take(ranked, 1)
    lead = lead[0] if lead else None
    secs = []
    if lead:
        for i in ranked:
            if i["id"] in used or i["cat"] == lead["cat"] or any(i["cat"] == s["cat"] for s in secs): continue
            secs.append(i); used.add(i["id"])
            if len(secs) == 2: break
    latest = take(items, 12, _news)
    local_items = [i for i in items if i.get("local")]
    # --- 1. lead package + Latest rail
    body = f'<h1 class="vh">{esc(HOME_H1)}</h1><div class="fp">'
    lead_pk = ""
    if lead:
        lim = story_img(lead, require_match=True)
        cap = credit(lim) if lim else ""
        lead_pk = card(lead, "lg", lazy=False).replace("<h3>", "<h2>", 1).replace("</h3>", "</h2>", 1) + (f'<p class="cap">{cap}</p>' if cap else "")
        lead_pk += f'<div class="grid g2">{"".join(card(s, "md") for s in secs)}</div>'
    body += f'<section class="lead-pk" aria-label="Top story">{lead_pk}</section>'
    rail = rows(latest[:8], "text") + (f'<details class="more"><summary><span class="mo">Show {len(latest[8:])} more</span><span class="less">Show less</span></summary>{rows(latest[8:], "text")}</details>' if latest[8:] else "")
    body += f'<aside class="rail" aria-labelledby="latest-h">{section_header("Latest", id="latest-h")}{rail}</aside>'
    # --- jump row (mobile)
    # --- 2. Local first
    feed = sorted(originals, key=_pr_ts, reverse=True) + local_items
    featured = next((p for p in originals), None) or (local_items[0] if local_items else None)
    if featured and "link" in featured: used.add(featured["id"])
    lrows = [x for x in feed if x is not featured and ("company" in x or x["id"] not in used)][:4]
    for x in lrows:
        if "link" in x: used.add(x["id"])
    events = _events(c)
    ev_html = events_list(events, 4)
    cond = cond_strip(_cond_html(c))
    if featured or lrows:
        col3 = f'<div class="levents"><h3 class="h3k">Happening this week</h3>{ev_html}</div>' if ev_html else f'<div class="levents"><h3 class="h3k">Happening this week</h3><div class="empty">No upcoming events on file. Organizations can <a href="/submit/">send us their dates</a>.</div></div>'
        lgrid = f'<div class="lgrid"><div>{card(featured, "lg") if featured else ""}</div><div class="list">{"".join(card(x, "row") for x in lrows)}</div>{col3}</div>'
    else:
        lgrid = f'<div class="empty"><p><b>Local news starts here.</b> Agencies, businesses and nonprofits in the Colorado River region can publish announcements on {NAME} for free; an editor reviews every submission.</p><a class="btn ghost" href="/submit/">Submit the first release</a></div>'
    body += (f'<section class="local" id="sec-local" aria-labelledby="local-h">{section_header("Around the Colorado River", "/local/", "local", "All local news", id="local-h")}'
             f'{chips(HOME_AREAS + [("All areas", "/local/")], scroll=True, label="Coverage areas")}{cond}{lgrid}'
             f'<div class="lfoot"><span>Have news from your town? Submissions are free and reviewed by an editor.</span><a class="btn ghost sm" href="/submit/">Submit news</a></div></section>')
    # --- 3. What you need to know + Markets box
    briefs = []
    for k in ("us", "world", "politics", "business", "tech"):
        sec = _rank(by.get(k) or [])   # best-ranked real news item in the section, preferring one with a summary
        b = take(sec, 1, lambda i: _news(i) and bool(i.get("summary"))) or take(sec, 1, _news) or take(sec, 1)
        briefs += b
    if briefs:
        def brief(i):
            dek = f'<p class="dek">{esc(clean(i["summary"], 170))}</p>' if i.get("summary") and not i["summary"].lower().startswith(i["title"].lower()[:30]) else ""
            return (f'<li class="t-{i["cat"]}"><div><span class="kick">{esc(CAT_SHORT.get(i["cat"], i["cat"]))}</span><h3><a href="/story/{i["slug"]}/">{esc(i["title"])}</a></h3>'
                    f'{dek}<span class="meta"><bdi>{esc(_pub_name(i))}</bdi> · {time_tag(i["ts"])}</span></div></li>')
        lis = "".join(brief(i) for i in briefs)
        body += f'<section class="briefs" aria-labelledby="briefs-h">{section_header("What you need to know", id="briefs-h")}<ol>{lis}</ol></section>'
    tickers = [str(t) for t in (man.get("tickers") or [])][:12]
    mk = take(by.get("markets") or [], 3)
    if tickers or mk:
        tk = f'<p class="kick">Trending tickers</p><div class="tickers">{"".join(f"<span>${esc(t)}</span>" for t in tickers)}</div>' if tickers else ""
        body += f'<aside class="numbers" aria-labelledby="num-h">{section_header("Markets", "/category/markets/", "markets", "More Markets", id="num-h")}{tk}{rows(mk, "text")}</aside>'
    else:
        pubs = collections.Counter(_pub_name(i) for i in items)
        body += f'<aside class="numbers" aria-labelledby="num-h">{section_header("Sources today", "/about/", None, "About our sources", id="num-h")}<p class="trust"><b>{len(pubs)} publishers</b> in today\'s edition, led by {", ".join(esc(n) for n, _ in pubs.most_common(5))}.</p></aside>'
    # --- 4. Top headlines: 1 lg + 4 rows
    top = take(ranked, 5)
    top.sort(key=lambda i: not has_photo(i))   # the lg slot goes to a keyword-matched photo when one exists
    if top:
        body += (f'<section class="full" id="sec-top" aria-labelledby="top-h">{section_header("Top headlines", id="top-h")}'
                 f'<div class="secpk" style="margin:0;padding:0;border:0"><div>{card(top[0], "lg")}</div>{rows(top[1:])}</div></section>')
    # --- 5. Bands
    def col(k, title, keys, n_rows=3, href=None):
        pool = [i for key in keys for i in (by.get(key) or [])]
        pool.sort(key=lambda i: -int(i.get("ts") or 0))
        first = take(pool, 1, has_photo) or take(pool, 1)
        rest = take(pool, n_rows)
        if not first and not rest: return ""
        return (f'<section id="sec-{k}" aria-labelledby="sec-{k}-h">{section_header(title, href or f"/category/{k}/", k, id=f"sec-{k}-h")}'
                f'{card(first[0], "md") if first else ""}{rows(rest, "text")}</section>')
    body += f'<div class="band">{col("us", "U.S.", ["us"])}{col("politics", "Politics", ["politics"])}</div>'
    body += f'<div class="band">{col("business", "Business & Markets", ["business", "markets"])}{col("tech", "Tech & Science", ["tech", "science"])}</div>'
    # --- World + Sports
    w = take(sorted(by.get("world") or [], key=lambda i: -int(i.get("ts") or 0)), 5)
    w.sort(key=lambda i: not has_photo(i))
    if w:
        body += f'<section class="full" id="sec-world" aria-labelledby="sec-world-h">{section_header("World", "/category/world/", "world", id="sec-world-h")}<div class="grid">{"".join(card(i, "md") for i in w[:3])}</div>{rows(w[3:], "text", cls="list river")}</section>'
    s = take(sorted(by.get("sports") or [], key=lambda i: -int(i.get("ts") or 0)), 5)
    if s:
        body += f'<section class="full" id="sec-sports" aria-labelledby="sec-sports-h">{section_header("Sports", "/category/sports/", "sports", id="sec-sports-h")}<div class="river">{card(s[0], "row")}{"".join(card(i, "text") for i in s[1:])}</div></section>'
    # --- 6. Topics + publishers
    topics = [(l, h) for _, l, h in TOPIC_LINKS]
    if topics:
        body += f'<section class="full" aria-labelledby="topics-h">{section_header("Topics", id="topics-h", soft=True)}{chips(topics, label="Topics")}</section>'
    pubs = collections.Counter(_pub_name(i) for i in items)
    if pubs:
        body += (f'<section class="full" aria-labelledby="pubs-h">{section_header("From the region\'s publishers and the wires", "/about/", None, "About our sources", id="pubs-h", soft=True)}'
                 f'<ul class="pubs">{"".join(f"<li><bdi>{esc(n)}</bdi><span>{k}</span></li>" for n, k in pubs.most_common(10))}</ul></section>')
    # --- 7. CTA pair
    body += ('<div class="full ctas"><div><h2>Have news to share?</h2><p>Agencies, businesses, schools and nonprofits along the river can publish announcements here for free. An editor reviews every submission.</p><a class="btn ghost" href="/submit/">Submit news</a></div>'
             '<div><h2>Get it by feed</h2><p>Every section and every area has its own feed. No account, no tracking.</p><div class="row"><a class="btn ghost" href="/rss.xml">RSS</a><a class="btn ghost" href="/feed.xml">Atom</a><a class="btn ghost" href="/press-releases/feed.xml">Local only</a></div></div></div>')
    body += "</div>"
    # head
    lim = story_img(lead, require_match=True) if lead else None
    pre = None
    if lim:
        from .images import _srcset
        pre = {"href": lim.get("sm") or lim["src"], "srcset": _srcset(lim).replace(' srcset="', "").rstrip('"'), "sizes": "(max-width:1024px) 100vw, 860px"} if lim.get("sm") else lim["src"]
    ld = [n for n in (_node("collection_node", "/", getattr(H, "HOME_TITLE", NAME), originals[:20], about="org", desc=getattr(H, "HOME_DESC", None)),) if n]
    write("/", page(NAME, body, getattr(H, "HOME_DESC", TAG), "/", ld=ld or None, preload_img=pre))
    _reg(c, "/", "page", getattr(H, "HOME_TITLE", NAME), summary=getattr(H, "HOME_DESC", ""), image=(SITE + lim["src"]) if lim else None)

# ---------- section fronts (DECISIONS §7) ----------
def _river(lst, show=18):
    """Cards with day dividers; the first `show` visible, the rest behind 'Show 18 more'."""
    out, day = [], None
    for i in lst:
        d = _day_label(i.get("ts") or 0)
        if d != day: out.append(f'<div class="day" role="heading" aria-level="2">{esc(d)}</div>'); day = d
        out.append(card(i, "row"))
    return grid(out, show, "river", 18, "Show 18 more", "stories")
def render_categories(c):
    by = c.by; originals = _originals(c)
    for k, v in CATS:
        reset_recent()
        lst = list(by.get(k) or [])
        if k == "local":
            lst = sorted([i for i in c.items if i.get("local")], key=lambda i: -int(i.get("ts") or 0))
        lst = lst[:60]
        if lst:   # the lead slot prefers a keyword-matched photo among the top five
            k_lead = next((i for i in lst[:5] if has_photo(i)), lst[0]); lst.remove(k_lead); lst.insert(0, k_lead)
        title = CAT_TITLE.get(k) or f"{v} News"
        desc = CAT_DESC.get(k) or f"The latest {v} headlines from {NAME}."
        tabs = CAT_TABS.get(k)
        sub = ""
        if tabs: sub = f'<nav class="subnav" aria-label="{esc(v)} sections">{"".join(f'<a href="{h}"{" aria-current=\"page\"" if kk == k else ""}>{esc(l)}</a>' for kk, l, h in tabs)}</nav>'
        if k == "local": sub = chips(HOME_AREAS + [("All areas", "/local/")], scroll=True, label="Coverage areas") + '<div style="height:24px"></div>'
        phead = (f'<div class="phead t-{k}"><h1><span class="bar"></span>{esc(title)}</h1><p class="lede">{esc(desc)}</p>'
                 f'<span class="meta">Updated {time_tag(int(NOW.timestamp()), "long")}</span></div>{sub}')
        if k == "local" and originals:
            lead_cards = f'<section aria-labelledby="orig-h">{section_header("Latest local originals", "/press-releases/", "local", "All press releases", id="orig-h")}<div class="grid">{"".join(pr_card(p) for p in originals[:3])}</div></section><div style="height:48px"></div>'
        else: lead_cards = ""
        if lst:
            body = phead + lead_cards + f'<section class="secpk" aria-labelledby="top-{k}"><h2 class="vh" id="top-{k}">Top {esc(v)} stories</h2><div>{card(lst[0], "lg")}</div>{rows(lst[1:5])}</section>'
            body += f'<section aria-labelledby="more-{k}"><h2 class="vh" id="more-{k}">More {esc(v)} stories</h2>{_river(lst[5:])}</section>' if lst[5:] else ""
        else:
            alts = [(CAT_NAME[a], f"/category/{a}/") for a in ("us", "world", "politics") if a != k][:2]
            body = phead + lead_cards + f'<div class="empty"><p>Nothing filed in {esc(v)} in the last 48 hours. Try {" or ".join(f"<a href={chr(34)}{h}{chr(34)}>{esc(n)}</a>" for n, h in alts)}.</p></div>'
        path = f"/category/{k}/"
        canon = True
        if k == "local" and _LOCAL_MOD is not None: canon = "/local/"
        ld = [n for n in (_crumb_nodes(("Home", "/"), (v, path)), _node("collection_node", path, title, lst[:50], desc=desc, breadcrumb_id=path)) if n]
        html = page(title, body, desc, path, ld=ld or None, canonical=canon)
        write(path, html)
        if canon is True: _reg(c, path, "section", title, summary=desc, cat=k)
        if k == "local" and _LOCAL_MOD is None:
            # local.py has not landed: serve the same front at /local/ so nav links resolve
            write("/local/", page(title, body, desc, "/local/", ld=[n for n in (_crumb_nodes(("Home", "/"), ("Local", "/local/")), _node("collection_node", "/local/", title, lst[:50], desc=desc, breadcrumb_id="/local/")) if n] or None))
            _reg(c, "/local/", "hub", title, summary=desc, cat="local")

# ---------- story pages (DECISIONS §6) ----------
_STOP = set("the a an and of to in for on with at by from as is are was be has have will after over into says said about new more than its their who how what why up out this that it with without your they them been were from than into onto also just".split())
def _toks(s): return {w for w in re.findall(r"[a-z0-9]{4,}", (s or "").lower()) if w not in _STOP}
def _related_index(items):
    """{id: [related items]} via shared title tokens within the same section (inverted index; cheap)."""
    by_cat = collections.defaultdict(list)
    for i in items: by_cat[i["cat"]].append(i)
    rel = {}
    for cat, lst in by_cat.items():
        toks = {i["id"]: _toks(i["title"]) for i in lst}
        inv = collections.defaultdict(list)
        for i in lst:
            for w in toks[i["id"]]: inv[w].append(i["id"])
        byid = {i["id"]: i for i in lst}
        for i in lst:
            cnt = collections.Counter()
            for w in toks[i["id"]]:
                ids = inv[w]
                if len(ids) > 60: continue   # too common within the section to mean anything
                for j in ids:
                    if j != i["id"]: cnt[j] += 1
            rel[i["id"]] = [byid[j] for j, n in cnt.most_common(8) if n >= 2]
    return rel
def render_stories(c):
    items = c.items; by = c.by; originals = _originals(c)
    rel_idx = _related_index(items)
    by_src = collections.defaultdict(list)
    for i in items: by_src[_pub_name(i)].append(i)
    byid = {i["id"]: i for i in items}
    (OUT/"story").mkdir(parents=True, exist_ok=True)
    for n_i, i in enumerate(items):
        reset_recent()
        cat = i["cat"]; sec = CAT_NAME.get(cat, cat)
        area = item_area(i) if i.get("local") else None
        pub = _pub_name(i); dom = _pub_domain(i)
        path = f"/story/{i['slug']}/"; url = SITE + path
        sim = story_img(i, require_match=True)
        summary = clean(i.get("summary") or "")
        if summary.lower().startswith(i["title"].lower()[:40]): summary = ""
        # related: cluster siblings first, then keyword overlap in the section
        also = [byid[a] if not isinstance(a, dict) else a for a in (i.get("also") or []) if (isinstance(a, dict) or a in byid)]
        rel = []
        for r in also + rel_idx.get(i["id"], []):
            if r is i or r["id"] in {x["id"] for x in rel}: continue
            rel.append(r)
            if len(rel) == 5: break
        if len(rel) < 3:
            for r in by.get(cat) or []:
                if r is i or any(r["id"] == x["id"] for x in rel): continue
                rel.append(r)
                if len(rel) == 3: break
        more_src = [r for r in by_src.get(pub) or [] if r is not i][:3]
        kicks = f'<div class="kicks"><span class="kick t-{cat}"><a href="/category/{cat}/">{esc(sec)}</a></span>' + (f'<span class="kick t-local"><a href="{area_href(area)}">{esc(region_name(area))}</a></span>' if area else "") + "</div>"
        when = time_tag(i.get("ts"), "long")
        srcbar = (f'<div class="srcbar"><span class="av" aria-hidden="true">{esc(pub[:1].upper())}</span><div class="pub"><b><bdi>{esc(pub)}</bdi></b><span class="meta">{f"<span class={chr(34)}dom{chr(34)}>{esc(dom)}</span> · " if dom else ""}Published {when}</span></div>'
                  f'<div class="acts"><button class="share" type="button" data-url="{esc(url)}" data-title="{esc(i["title"])}">Share</button><a class="btn ghost sm" href="{esc(i["link"])}" rel="noopener nofollow" target="_blank">Read original <span aria-hidden="true">↗</span><span class="vh"> (opens in new tab)</span></a></div></div>')
        brief = f'<div class="summary"><h2>In brief</h2><p>{esc(summary)}</p></div>' if summary else ""
        media = figure(sim, False) if sim else tile(pub, sec)
        cta = f'<p><a class="cta" href="{esc(i["link"])}" rel="noopener nofollow" target="_blank">Read the full story at {esc(pub)} <span aria-hidden="true">↗</span><span class="vh"> (opens in new tab)</span></a></p>'
        attr = f'<p class="attr">Summary only. Reporting and rights: <bdi>{esc(pub)}</bdi>. {NAME} gathers headlines from publishers\' public feeds; <a href="/editorial-policy/">how we aggregate</a>.</p>'
        b = f'<article class="story">{kicks}<h1>{esc(i["title"])}</h1>{srcbar}{brief}{media}{cta}{attr}</article>'
        rel_html = ""
        if rel: rel_html += f'<section aria-labelledby="rel-h">{section_header("Related coverage", id="rel-h", soft=True)}{rows(rel, "text")}</section>'
        if more_src: rel_html += f'<section aria-labelledby="src-h">{section_header(f"More from {pub}", id="src-h", soft=True)}{rows(more_src, "text")}</section>'
        if rel_html: b += f'<div class="related"><div class="rel2">{rel_html}</div></div>'
        if i.get("local"):
            near = [p for p in originals if area and pr_region(p) == area][:3] or originals[:3]
            if near or area:
                b += (f'<div class="related"><section class="near" aria-labelledby="near-h">{section_header("Near you", area_href(area), "local", f"More from {region_name(area)}" if area else "All local news", id="near-h")}'
                      f'<div class="grid">{"".join(pr_card(p, "md") for p in near)}</div></section></div>')
        # markdown twin
        (OUT/f"story/{i['slug']}.md").write_text(f"# {i['title']}\n\n- Source: {pub}\n- Published: {iso(i.get('ts'))}\n- Category: {sec}\n" + (f"- Area: {region_name(area)}\n" if area else "") + f"- Original: {i['link']}\n- Canonical: {url}\n\n{summary or 'Read the full report from the original publisher.'}\n\n_{NAME} shows a short summary only; the full article and all rights belong to {pub}._\n", encoding="utf-8")
        crumb = _crumb_nodes(("Home", "/"), (sec, f"/category/{cat}/"), (i["title"], path))
        nodes = [crumb, _node("story_node", i, sim, path), _node("image_node", sim, path) if sim else None,
                 _node("webpage_node", path, i["title"], path, iso(i.get("ts")), "ItemPage", summary or i["title"], (url + "#primaryimage") if sim else None, iso(i.get("ts")))]
        og = og_for(i["slug"], i["title"], "local" if i.get("local") else cat, sim, source=pub, date=T._dt(i.get("ts")).date() if i.get("ts") else None, kicker=region_name(area) if area else None) if n_i < OG_STORIES else None
        write(path, page(i["title"], b, summary or f"{i['title']} ({pub})", path, "article", og_img=og, md=f"/story/{i['slug']}.md", robots=NOINDEX,
                         ld=[n for n in nodes if n] or None, article={"published": iso(i.get("ts")), "modified": iso(i.get("ts")), "section": sec, "author": pub}))
        _reg(c, path, "story", i["title"], lastmod=iso(i.get("ts")), image=(SITE + sim["src"]) if sim else None, ts=i.get("ts"), summary=summary, area=area, cat=cat)

# ---------- press releases: index + pages (ux.md §8) ----------
def _ics_text(s): return str(s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
def _ics(p, e):
    """Minimal VCALENDAR for an original's event (all-day dates or UTC timestamps)."""
    st = T.to_ts(e["start"]); en = T.to_ts(e.get("end")) if e.get("end") else None
    if not st: return None
    uid = f"{p['slug']}@{SITE.split('//')[-1]}"
    stamp = NOW.strftime("%Y%m%dT%H%M%SZ")
    if e.get("all_day") or (isinstance(e["start"], str) and len(e["start"]) == 10):
        d0 = T._dt(st).astimezone(T.TZ).date(); d1 = (T._dt(en).astimezone(T.TZ).date() if en else d0) + dt.timedelta(days=1)
        when = f"DTSTART;VALUE=DATE:{d0.strftime('%Y%m%d')}\r\nDTEND;VALUE=DATE:{d1.strftime('%Y%m%d')}"
    else:
        f = lambda t: T._dt(t).strftime("%Y%m%dT%H%M%SZ")
        when = f"DTSTART:{f(st)}\r\nDTEND:{f(en or st + 7200)}"
    loc = ", ".join(x for x in (e.get("venue"), e.get("address")) if x)
    url = e.get("url") or f"{SITE}/press-releases/{p['slug']}/"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//{NAME}//EN", "CALSCALE:GREGORIAN", "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", when,
             f"SUMMARY:{_ics_text(p['title'])}"] + ([f"LOCATION:{_ics_text(loc)}"] if loc else []) + [f"DESCRIPTION:{_ics_text((p.get('summary') or '') + chr(10) + SITE + '/press-releases/' + p['slug'] + '/')}", f"URL:{url}", "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"
def _maps(e):
    q = ", ".join(x for x in (e.get("venue"), e.get("address")) if x)
    from urllib.parse import quote
    return f"https://www.google.com/maps/search/?api=1&query={quote(q)}" if q else None
def _contact(p):
    ct = (p.get("contact") or "").strip()
    if ct and (("@" in ct) or re.search(r"\d", ct)):
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", ct)
        ct_html = esc(ct).replace(esc(m.group(0)), f'<a href="mailto:{esc(m.group(0))}">{esc(m.group(0))}</a>') if m else esc(ct)
        return f'<p class="note">Media contact: {ct_html}</p>'
    org = p.get("company") or ct
    if not org: return ""
    return f'<p class="note">Contact: <a href="{esc(p["source_url"])}" rel="noopener" target="_blank">{esc(org)}<span class="vh"> (opens in new tab)</span></a></p>' if p.get("source_url") else f'<p class="note">Contact: {esc(org)}</p>'
def render_press_releases(c):
    prs = list(getattr(c, "prs", []) or []); originals = _originals(c)
    local_events = {}
    fn = getattr(_LOCAL_MOD, "events", None)
    if fn:
        try:
            for e in fn(originals) or []:
                s = (e.get("url") or "").strip("/").split("/")[-1]
                if e.get("ics") or e.get("ics_path"): local_events[s] = e.get("ics") or e.get("ics_path")
        except Exception: pass
    # index
    reset_recent()
    areas = sorted({pr_region(p) for p in originals if pr_region(p)}, key=lambda k: region_name(k))
    idx_desc = "Press releases, briefs and reports from Bullhead City, Laughlin, Mohave Valley, Lake Havasu City, Kingman, Mesquite, Boulder City and the rest of the Colorado River region."
    body = (f'<div class="phead t-local"><h1><span class="bar"></span>Local news</h1><p class="lede">{esc(idx_desc)} <a href="/submit/">Submit a release</a>.</p>'
            f'<span class="meta">Updated {time_tag(int(NOW.timestamp()), "long")}</span></div>'
            + (chips([(region_name(a), area_href(a)) for a in areas] + [("All areas", "/local/")], scroll=True, label="Coverage areas") + '<div style="height:24px"></div>' if areas else ""))
    if originals: body += f'<section aria-labelledby="pri-h"><h2 class="vh" id="pri-h">All local originals</h2>{grid([pr_card(p) for p in originals], 9, "grid", 9, "Show 9 more", "releases")}</section>'
    else: body += f'<div class="empty"><p><b>No releases yet.</b> Be the first: submissions are free and reviewed by an editor.</p><a class="btn ghost" href="/submit/">Submit a release</a></div>'
    ld = [n for n in (_crumb_nodes(("Home", "/"), ("Local", "/local/"), ("Press releases", "/press-releases/")), _node("collection_node", "/press-releases/", "Local news: press releases, briefs and reports", originals, about="org", desc=idx_desc, breadcrumb_id="/press-releases/")) if n]
    write("/press-releases/", page("Local News: Press Releases, Briefs & Reports", body, idx_desc, "/press-releases/", ld=ld or None))
    _reg(c, "/press-releases/", "page", "Local news: press releases, briefs and reports", summary=idx_desc, cat="local")
    # pages
    for p in prs:
        reset_recent()
        reg = pr_region(p); area_nm = region_name(reg) if reg else (p.get("area") or "")
        kind = p.get("kind") or "press-release"; klabel = KIND_LABEL.get(kind, "Press release")
        path = f"/press-releases/{p['slug']}/"; url = SITE + path
        pim = pr_img(p); ts = _pr_ts(p)
        e = _pr_event(p)
        ics_href = local_events.get(p["slug"])
        if e and not ics_href:
            txt = _ics(p, e)
            if txt:
                (OUT/"press-releases").mkdir(parents=True, exist_ok=True)
                (OUT/f"press-releases/{p['slug']}.ics").write_text(txt, encoding="utf-8"); ics_href = f"/press-releases/{p['slug']}.ics"
        evbox = ""
        if e:
            st = T.to_ts(e["start"]); en = T.to_ts(e.get("end")) if e.get("end") else None
            allday = e.get("all_day") or (isinstance(e["start"], str) and len(e["start"]) == 10)
            if st:
                d0 = T._dt(st).astimezone(T.TZ); d1 = T._dt(en).astimezone(T.TZ) if en else None
                if d1 and d1.date() != d0.date(): when = f"{d0.strftime('%a, %b %-d')} to {d1.strftime('%a, %b %-d, %Y')}"
                else: when = d0.strftime("%A, %b %-d, %Y") + ("" if allday else d0.strftime(", %-I:%M %p").replace(":00", "") + (f"–{d1.strftime('%-I:%M %p').replace(':00', '')}" if d1 else "") + " MST")
                rows_ = f'<dt>When</dt><dd><time datetime="{esc(T.iso(st))}">{esc(when)}</time></dd>'
                if e.get("venue"): rows_ += f'<dt>Where</dt><dd>{esc(e["venue"])}</dd>'
                if e.get("address"): rows_ += f'<dt>Address</dt><dd>{esc(e["address"])}</dd>'
                if area_nm: rows_ += f'<dt>Area</dt><dd><a href="{area_href(reg)}">{esc(area_nm)}</a></dd>'
                acts = (f'<a class="btn ghost sm" href="{esc(ics_href)}">Add to calendar</a>' if ics_href else "") + (f'<a class="btn ghost sm" href="{esc(_maps(e))}" rel="noopener" target="_blank">Map<span class="vh"> (opens in new tab)</span></a>' if _maps(e) else "") + (f'<a class="btn ghost sm" href="{esc(e["url"])}" rel="noopener" target="_blank">Event details<span class="vh"> (opens in new tab)</span></a>' if e.get("url") else "")
                evbox = f'<div class="evbox"><h2>Event details</h2><dl>{rows_}</dl><div class="acts">{acts}</div></div>'
        kicks = f'<div class="kicks"><span class="chip">{esc(klabel)}</span>' + (f'<span class="kick t-local"><a href="{area_href(reg)}">{esc(area_nm)}</a></span>' if area_nm else "") + (' <span class="chip red">Example</span>' if p.get("example") else "") + "</div>"
        author = p.get("author") if kind != "press-release" else None
        byline = f'<b><bdi>{esc(p.get("company") or NAME)}</bdi></b>' if kind == "press-release" else f'<b>{esc(author or f"{NAME} staff")}</b>'
        srcbar = (f'<div class="srcbar"><div class="pub">{byline}<span class="meta">{"Issued" if kind == "press-release" else "Published"} {time_tag(ts, "long")}' + (f' · {esc(p.get("company"))}' if kind != "press-release" and p.get("company") else "") + "</span></div>"
                  f'<div class="acts"><button class="share" type="button" data-url="{esc(url)}" data-title="{esc(p["title"])}">Share</button></div></div>')
        brief = f'<div class="summary"><h2>In brief</h2><p>{esc(p.get("summary"))}</p></div>' if p.get("summary") else ""
        src = ""
        if p.get("source_url"):
            src = f'<p class="note">{"Rewritten from public reporting; check the source for times and details. " if kind != "press-release" else "Source: "}<a href="{esc(p["source_url"])}" rel="noopener" target="_blank">{esc(p.get("source_name") or p["source_url"])}<span class="vh"> (opens in new tab)</span></a></p>'
        body = f'<article class="story">{crumbs_html([("Home", "/"), ("Local", "/local/")] + ([(area_nm, area_href(reg))] if area_nm else []) + [(p["title"], path)])}{kicks}<h1>{esc(p["title"])}</h1>{srcbar}{brief}{evbox}{figure(pim, False)}<div class="prose">{p["body"]}</div>{src}{_contact(p)}</article>'
        more = [q for q in originals if q is not p and reg and pr_region(q) == reg][:3]
        more += [q for q in originals if q is not p and q not in more and p.get("company") and q.get("company") == p.get("company")][:3 - len(more)]
        more += [q for q in originals if q is not p and q not in more][:3 - len(more)]
        if more: body += f'<section class="related" aria-labelledby="morel-h">{section_header("More local news", "/local/", "local", "All local news", id="morel-h")}<div class="grid">{"".join(pr_card(q) for q in more)}</div></section>'
        im = pim or {}
        p["md_full"] = f"# {p['title']}\n\n- Kind: {klabel}\n- Date: {p['date']}\n- From: {p.get('company')}\n- Area: {p.get('area') or ''}\n- Canonical: {url}\n" + (f"- Source: {p['source_url']}\n" if p.get("source_url") else "") + (f"- Event: {e['start']}" + (f" to {e['end']}" if e.get("end") else "") + (f" at {e['venue']}" if e.get("venue") else "") + "\n" if e else "") + (f"- Image: {H.absimg(im)} ({im.get('label')}; {im.get('credit')}; {im.get('license')}; {im.get('source')})\n" if im and not im.get("brand") else "") + f"\n> {p.get('summary') or ''}\n\n{p['md']}\n\n" + (f"Media contact: {p.get('contact')}\n" if p.get("contact") else "")
        (OUT/"press-releases").mkdir(parents=True, exist_ok=True)
        (OUT/f"press-releases/{p['slug']}.md").write_text(p["md_full"], encoding="utf-8")
        crumb = _crumb_nodes(("Home", "/"), ("Local", "/local/"), *([(area_nm, area_href(reg))] if area_nm else []), (p["title"], path))
        nodes = [crumb, _node("article_node", p, pim, path), _node("image_node", pim, path) if pim else None, _node("event_node", p, path),
                 _node("webpage_node", path, p["title"], path, H.modified(p) if hasattr(H, "modified") else None, "ItemPage", p.get("summary"), (url + "#primaryimage") if pim else None, H.published(p) if hasattr(H, "published") else None)]
        og = og_for("pr-" + p["slug"], p["title"], "pr", pim, source=p.get("company"), date=T._dt(ts).date(), kicker=klabel if not area_nm else f"{klabel} · {area_nm}") or H.absimg(pim)
        pub_iso = H.published(p) if hasattr(H, "published") else iso(ts)
        write(path, page(p["title"], body, p.get("summary") or p["title"], path, "article", og_img=og, md=f"/press-releases/{p['slug']}.md",
                         robots=(NOINDEX if p.get("example") else None), ld=[n for n in nodes if n] or None,
                         article={"published": pub_iso, "modified": H.modified(p) if hasattr(H, "modified") else pub_iso, "section": "Local", "tags": [t for t in (p.get("area"), p.get("company")) if t], "author": p.get("company") if kind == "press-release" else (author or f"{NAME} staff")}))
        if not p.get("example"):
            _reg(c, path, "original", p["title"], lastmod=H.modified(p) if hasattr(H, "modified") else pub_iso, image=H.absimg(pim) if pim else None, ts=ts, summary=p.get("summary"), area=reg, cat="local")

# ---------- 404 (ux.md §11) ----------
def render_404(c):
    reset_recent()
    items = list(c.items); originals = _originals(c)
    secs = [(CAT_NAME[k], f"/category/{k}/") if k != "local" else ("Local", "/local/") for k, _ in CATS if k not in ("markets", "science")]
    body = (f'<div class="nf"><h1>Page not found</h1><p class="lede">This story may have rolled off the wire, or the address has a typo. Here is where to go next.</p>'
            f'{chips(secs + [("Homepage", "/")], label="Sections")}'
            + (f'<section aria-labelledby="nf-latest">{section_header("Latest headlines", "/", None, "Homepage", id="nf-latest", soft=True)}{rows(items[:5], "text")}</section>' if items else "")
            + (f'<section aria-labelledby="nf-local" style="margin-top:48px">{section_header("Around the Colorado River", "/local/", "local", "All local news", id="nf-local")}<div class="grid">{"".join(pr_card(p) for p in originals[:3])}</div></section>' if originals else "")
            + f'<p class="attr" style="margin-top:32px">Think this is our mistake? <a href="/corrections/">Tell us</a> or email <a href="mailto:{CONTACT}">{CONTACT}</a>.</p></div>')
    write("/404.html", page("Page not found", body, "The page you asked for is not here.", "/404.html", robots=NOINDEX, canonical=False))

def render_all(c):
    set_justin(c.items)
    render_home(c); render_categories(c); render_stories(c); render_press_releases(c); render_404(c)
