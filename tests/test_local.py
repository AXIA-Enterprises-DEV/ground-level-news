"""Tests for gln.local: /local/ hub, area hubs, topic pages, events() and the .ics files.
The render runs once per module in a subprocess (so OUT_DIR is honoured regardless of import order) against the
saved tracker fixture; events() is also exercised in-process with a pinned "now".
Run: python -m pytest tests/test_local.py -q"""
import os, re, sys, json, subprocess, pathlib, datetime as dt, types
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
ENV = {"TRACKER_BASE": str(FIX), "SOURCES_DISABLED": "1", "OG_STORIES": "0"}
PIN = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)   # fixtures were captured on 2026-10-18

DRIVER = r"""
import sys, json, pathlib
sys.path.insert(0, sys.argv[1])
import build
from gln import local
c = build.build_context()
if not hasattr(c, "urls") or c.urls is None: c.urls = []
res = local.render_local(c)
out = pathlib.Path(sys.argv[2])
json.dump({"urls": c.urls, "events": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in e.items() if k != "obj"} for e in res["events"]],
           "areas": res["areas"], "topics": res["topics"]}, (out / "local-report.json").open("w"), default=str)
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    env = {**os.environ, **ENV, "OUT_DIR": str(out)}
    r = subprocess.run([sys.executable, "-c", DRIVER, str(ROOT / "scripts"), str(out)], env=env, capture_output=True, text=True, timeout=600, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-3000:]
    return out


@pytest.fixture(scope="module")
def report(site):
    return json.loads((site / "local-report.json").read_text())


def _ld(html):
    scripts = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert len(scripts) == 1, "exactly one JSON-LD graph per page"
    return json.loads(scripts[0])["@graph"]


# ----------------------------------------------------------------------------- pages
def test_hub_and_area_pages_exist(site, report):
    assert (site / "local/index.html").exists()
    hubs = [p for p in site.glob("local/*/index.html") if p.parent.name != "events"]
    assert len(hubs) >= 8, [p.parent.name for p in hubs]
    for key in ("bullhead-city", "laughlin", "mohave-valley", "clark-county", "mesquite", "boulder-city", "nevada", "arizona", "colorado-river", "lake-mead"):
        assert (site / f"local/{key}/index.html").exists(), key
    assert (site / "local/events/index.html").exists()
    assert (site / "topic/index.html").exists() and (site / "topics/index.html").exists()


def test_every_hub_has_canonical_breadcrumbs_and_no_cadence_claim(site):
    pages = [site / "local/index.html"] + list(site.glob("local/*/index.html"))
    for p in pages:
        html = p.read_text(encoding="utf-8")
        assert html.count('rel="canonical"') == 1, p
        assert "every 15 minutes" not in html, p
        types = [n.get("@type") for n in _ld(html)]
        assert "BreadcrumbList" in types and "CollectionPage" in types, (p, types)
        if p.parent.name not in ("local",):                # area hubs and the events page carry a visible breadcrumb trail
            assert 'aria-label="Breadcrumb"' in html and "Home" in html and ">Local<" in html, p


def test_area_hub_contract(site):
    html = (site / "local/laughlin/index.html").read_text(encoding="utf-8")
    assert "<title>Laughlin News and Press Releases | Ground Level News</title>" in html
    m = re.search(r'<meta name="description" content="([^"]*)"', html)
    assert m and 0 < len(m.group(1)) <= 155
    g = _ld(html)
    cp = next(n for n in g if n.get("@type") == "CollectionPage")
    assert cp["url"].endswith("/local/laughlin/") and cp["mainEntity"]["@type"] == "ItemList"
    assert cp.get("about", {}).get("name", "").startswith("Laughlin")
    bc = next(n for n in g if n.get("@type") == "BreadcrumbList")
    assert [x["name"] for x in bc["itemListElement"]] == ["Home", "Local", "Laughlin"]
    # the intro block is 120-200 words and links to agencies
    intro = re.search(r'<div class="prose">(.*?)</div></aside>', html, re.S).group(1)
    words = len(re.sub(r"<[^>]+>", " ", intro).split())
    assert 110 <= words <= 220, words
    assert "clarkcountynv.gov" in intro


def test_empty_state_still_gives_value(site):
    html = (site / "local/needles/index.html").read_text(encoding="utf-8")   # nothing in the fixture names Needles
    assert "No new items in the last 48 hours" in html and "submit news free" in html.lower()
    assert "About Needles" in html


def test_urls_registered(report):
    hubs = [u for u in report["urls"] if u["kind"] == "hub"]
    assert any(u["loc"] == "/local/" and u["area"] is None for u in hubs)
    assert {u["area"] for u in hubs if u["area"]} >= {"bullhead-city", "laughlin", "clark-county", "nevada", "arizona"}
    for u in hubs:
        assert re.match(r"\d{4}-\d{2}-\d{2}T", u["lastmod"]) and u["title"]
    assert any(u["kind"] == "section" and u["loc"].startswith("/topic/") for u in report["urls"])
    assert any(u["loc"] == "/topic/" for u in report["urls"])


# ----------------------------------------------------------------------------- events + ics
def test_events_from_fixture_press_releases(monkeypatch):
    monkeypatch.setenv("TRACKER_BASE", str(FIX))      # scoped to this test: never leak SOURCES_DISABLED into other modules
    from gln import local, feed
    prs = [p for p in feed.load_prs() if not p.get("example")]
    evs = local.events(prs, [], now=PIN)
    by = {e["url"].rsplit("/", 2)[-2]: e for e in evs}
    oh = by["2026-10-13-fort-mojave-mesa-fire-station-91-open-house"]
    assert oh["all_day"] is True and oh["start"].date() == dt.date(2026, 10, 17)
    assert oh["area"] == "mohave-valley" and oh["ics"] == "/press-releases/2026-10-13-fort-mojave-mesa-fire-station-91-open-house.ics"
    car = by["2026-10-04-mohave-valley-fire-halloween-carnival"]
    assert car["all_day"] is False and (car["start"].year, car["start"].month, car["start"].day, car["start"].hour, car["start"].minute) == (2026, 10, 23, 17, 0)
    assert car["end"].hour == 20 and car["venue"] == "Mohave Valley Fire Department"
    assert [e["start"] for e in evs] == sorted(e["start"] for e in evs)
    assert "2026-10-12-clark-county-foster-casa-info-night" not in by       # Oct 14: more than a day in the past
    assert all(e["ics_path"] == e["ics"] for e in evs)


def test_ics_files_parse(site, report):
    assert report["events"], "fixture has events"
    agg = (site / "local/events.ics").read_bytes().decode("utf-8")   # bytes: keep the CRLF line ends
    assert agg.startswith("BEGIN:VCALENDAR\r\n") and agg.rstrip().endswith("END:VCALENDAR")
    assert agg.count("BEGIN:VEVENT") == agg.count("END:VEVENT") == len(report["events"])
    assert "BEGIN:VTIMEZONE" in agg and "TZID:America/Phoenix" in agg
    for e in report["events"]:
        f = site / e["ics"].lstrip("/")
        assert f.exists(), e["ics"]
        txt = f.read_bytes().decode("utf-8")
        body = txt.split("BEGIN:VEVENT", 1)[1]
        for key in ("UID:", "DTSTAMP:", "DTSTART", "SUMMARY:", "URL:", "DESCRIPTION:", "END:VEVENT"):
            assert key in body, (e["ics"], key)
        assert re.search(r"DTSTART;VALUE=DATE:\d{8}|DTSTART;TZID=America/Phoenix:\d{8}T\d{6}", body)
        assert all(len(line.encode("utf-8")) <= 75 for line in txt.split("\r\n")), "lines folded at 75 octets"
    oh = (site / "press-releases/2026-10-13-fort-mojave-mesa-fire-station-91-open-house.ics").read_text()
    assert "DTSTART;VALUE=DATE:20261017" in oh and "DTEND;VALUE=DATE:20261018" in oh
    car = (site / "press-releases/2026-10-04-mohave-valley-fire-halloween-carnival.ics").read_text()
    assert "DTSTART;TZID=America/Phoenix:20261023T170000" in car


def test_events_page_has_event_jsonld(site):
    html = (site / "local/events/index.html").read_text(encoding="utf-8")
    g = _ld(html)
    assert any(n.get("@type") == "Event" for n in g)
    assert 'href="/local/events.ics"' in html


# ----------------------------------------------------------------------------- robustness
def test_unknown_region_never_crashes(monkeypatch):
    monkeypatch.setenv("TRACKER_BASE", str(FIX))
    from gln import local
    c = types.SimpleNamespace(items=[], originals=[], prs=[], urls=[])
    assert local.render_area(c, "atlantis") is None
    assert local.region_entries(c, "atlantis") == []
    assert local.region_scope("atlantis") == {"atlantis"}
    assert local.nearby("atlantis") == [] and local.ancestors("atlantis") == []
    assert local.region_name("atlantis") == "Atlantis"
    assert local.events([], [{"id": "x", "title": "Meeting", "link": "https://example.com", "slug": "m", "kind": "meeting", "event_start": "not a date"}]) == []
