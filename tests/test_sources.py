"""Offline tests for gln.sources and gln.conditions using saved feed XML in tests/fixtures/feeds/
(captured with curl on 2026-10-18). Run: python -m pytest tests/test_sources.py -q"""
import sys, os, re, json, hashlib, pathlib, types, datetime as dt
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures/feeds"
sys.path.insert(0, str(ROOT / "scripts"))
from gln import sources, conditions  # noqa: E402

# The fixtures were captured on 2026-10-18; freeze "now" so the 14-day window and event horizon are stable.
NOW = int(dt.datetime(2026, 10, 18, 13, 0, tzinfo=dt.timezone.utc).timestamp())


@pytest.fixture(scope="module")
def items():
    return sources.load_local_items(taxonomy=None, offline_dir=FIX, now=NOW, log=lambda m: None)


def by_key(items, key): return [i for i in items if i["source_key"] == key]


# ----------------------------------------------------------------------------- registry
def test_registry_loads_and_is_consistent():
    reg = sources.load_registry()
    keys = [s["key"] for s in reg["sources"]]
    assert len(keys) == len(set(keys)) and len(keys) >= 30
    for s in reg["sources"]:
        assert s["url"].startswith("https://") and s["name"] and s["kind"] in {"gov", "media", "events", "agency", "college", "tourism"}
        assert s["region"] and 1 <= int(s["tier"]) <= 3 and isinstance(s["paywalled"], bool)
        assert s["_tz"] is not None
    assert {d["key"] for d in reg["disabled"]} >= {"thebee", "kingman-city", "adot"}
    assert all(d.get("reason") for d in reg["disabled"])
    assert {s["key"] for s in reg["sources"] if s["paywalled"]} >= {"mohavedailynews", "havasunews", "kdminer", "reviewjournal-local"}
    assert "facebook.com" in reg["denylist_hosts"]


# ----------------------------------------------------------------------------- normalisation
def test_items_have_tracker_shape(items):
    assert len(items) > 60
    for it in items:
        assert it["id"] == hashlib.sha1(it["link"].encode()).hexdigest()[:14]
        assert it["cat"] == "local" and it["category"] == "local" and it["local"] is True and it["via"] == "direct"
        assert it["kind"] in {"gov", "media", "events", "agency", "college", "tourism", "event", "meeting"}
        assert 1 <= it["tier"] <= 3 and it["projects"] == [] and it["slug"]
        assert len(it["title"]) >= 15 and len(it["summary"]) <= 421
        assert it["regions"] and it["regions"][0] and isinstance(it["regions"], list)
        assert it["link"].startswith("https://") and "utm_" not in it["link"] and "#" not in it["link"]
        assert NOW - 14 * 86400 <= it["ts"] <= NOW, (it["source_key"], it["title"], it["ts"])
        assert it["source"] and it["source"] != "Google News" or not it.get("fallback")
    # newest first, and the title echo is not used as a summary
    assert [i["ts"] for i in items] == sorted((i["ts"] for i in items), reverse=True)
    assert all(re.sub(r"\W", "", i["summary"].lower()) != re.sub(r"\W", "", i["title"].lower()) for i in items if i["summary"])


def test_dedupe_by_link_and_title():
    a = {"title": "Council approves budget", "link": "https://x.test/a", "tier": 1, "ts": 10}
    b = {"title": "Council approves budget!", "link": "https://x.test/b", "tier": 2, "ts": 9}      # same normalised title
    c = {"title": "Something else entirely", "link": "https://x.test/A/", "tier": 2, "ts": 8}        # same link (case/slash)
    d = {"title": "A different story here", "link": "https://x.test/d", "tier": 3, "ts": 7}
    out = sources.dedupe([a, b, c, d])
    assert out == [a, d]


def test_no_duplicates_in_batch(items):
    links = [i["link"].lower().rstrip("/") for i in items]
    titles = [re.sub(r"\W", "", i["title"].lower())[:60] for i in items]
    assert len(links) == len(set(links)) and len(titles) == len(set(titles))


def test_region_tagging_from_registry(items):
    for it in by_key(items, "mohave-county"): assert it["regions"] == ["mohave-county", "arizona"]
    for it in by_key(items, "lhc-meetings"): assert it["regions"][:2] == ["lake-havasu-city", "mohave-county"]
    for it in by_key(items, "visitlaughlin-events"): assert it["regions"] == ["laughlin", "bullhead-city", "colorado-river"]


def test_region_tagging_uses_taxonomy_when_available():
    fake = types.SimpleNamespace(detect_regions=lambda text: ["kingman"] if "Kingman" in text else [],
                                 clean_summary=lambda title, s: s.replace("Fire Rescue", "Fire-Rescue"))
    reg = sources.load_registry()
    reg["sources"] = [s for s in reg["sources"] if s["key"] in {"lhc-meetings", "mesquitelocalnews"}]
    out = sources.load_local_items(fake, registry=reg, offline_dir=FIX, now=NOW, log=lambda m: None)
    tri = [i for i in out if i["title"].startswith("Tri-City Council")]
    assert tri and tri[0]["regions"] == ["lake-havasu-city", "mohave-county", "kingman"]  # venue is in Kingman
    assert any("Fire-Rescue" in i["summary"] for i in out if i["source_key"] == "mesquitelocalnews")


def test_date_parsing_loose_and_rfc(items):
    tz = sources.zoneinfo.ZoneInfo("America/Phoenix")
    assert sources.parse_loose_date("Fri, 16 October 2026 16:30:00", tz) == int(dt.datetime(2026, 10, 16, 23, 30, tzinfo=dt.timezone.utc).timestamp())
    assert sources.parse_loose_date("garbage", tz) is None
    county = by_key(items, "mohave-county")
    assert county and all(NOW - 14 * 86400 <= i["ts"] <= NOW for i in county)
    assert any(i["title"].startswith("Notice of Attendance") and i["ts"] == int(dt.datetime(2026, 10, 16, 23, 30, tzinfo=dt.timezone.utc).timestamp()) for i in county)
    bc = by_key(items, "bouldercityreview")
    assert any(i["ts"] == int(dt.datetime(2026, 10, 16, 2, 8, 22, tzinfo=dt.timezone.utc).timestamp()) for i in bc)  # RFC 822 +0000


def test_old_entries_are_skipped(items):
    # Lake Mead NRA's newest release in the fixture is from February 2026: nothing survives the 14-day window.
    assert by_key(items, "lake-mead-nra") == []


def test_google_news_publisher_split(items):
    assert sources.split_publisher("New hotel opening in North Las Vegas - Las Vegas Review-Journal") == \
        ("New hotel opening in North Las Vegas", "Las Vegas Review-Journal")
    assert sources.split_publisher("Laughlin police reports (Nov. 25 - Dec. 1) - Mohave Valley News") == \
        ("Laughlin police reports (Nov. 25 - Dec. 1)", "Mohave Valley News")
    assert sources.split_publisher("No publisher here") == ("No publisher here", None)
    assert sources.split_publisher("Body found in barrel at Lake Mead identified – KLAS - KLAS 8 News Now") == \
        ("Body found in barrel at Lake Mead identified", "KLAS 8 News Now")
    g = [i for i in items if i["source_key"].startswith("gnews")]
    assert g and all(i.get("fallback") and i["tier"] == 3 for i in g)
    assert all(i["source"] != "Google News" and not i["title"].endswith(i["source"]) for i in g), [i["title"] for i in g]
    assert any(" - " in i["title"] for i in g)   # a hyphenated date range inside the title survives; only the trailing publisher is cut
    assert any(i["source"] == "The Bee" for i in g)                       # The Bee reaches us through the fallback
    assert all(i["homepage"] and "google" not in i["homepage"] for i in g)  # publisher homepage from <source>


def test_google_news_noise_is_filtered(items):
    g = by_key(items, "gnews-bullhead") + by_key(items, "gnews-bouldercity")
    titles = " | ".join(i["title"] for i in g)
    assert "Obituary" not in titles and "Trinidad" not in titles and "Enfield" not in titles and "Football Videos" not in titles
    assert all(i["source"] not in {"MaxPreps", "NFHS Network", "Boulder Daily Camera"} for i in g)
    assert any("Bullhead City" in i["title"] for i in by_key(items, "gnews-bullhead"))


def test_junk_and_language_gate(items):
    assert all(sources.host_of(i["link"]) not in {"facebook.com", "legacy.com"} for i in items)
    assert not any(i["title"].startswith("El nuevo centro") for i in items)      # Spanish Sun story dropped
    assert any("Boulder City hub" in i["title"] for i in by_key(items, "lasvegassun-bouldercity"))
    assert sources.looks_foreign("Un nuevo centro en Boulder City está diseñado para conectar a residentes y visitantes con las empresas")
    assert not sources.looks_foreign("Early voting ahead of the Nov. 3 midterm election kicked off in Clark County and statewide")
    assert sources.recase("GENERAL PLAN UPDATE 2026 – PUBLIC HEARINGS") == "General Plan Update 2026 – Public Hearings"
    assert sources.recase("Mohave County Recorder Provides Update") == "Mohave County Recorder Provides Update"


def test_blox_feed_drops_paid_releases(items):
    mdn = by_key(items, "mohavedailynews")
    assert len(mdn) >= 15 and all("/online_features/" not in i["link"] for i in mdn)
    assert all(i["source"] == "Mohave Valley Daily News" and i["paywalled"] for i in mdn)


def test_metro_feed_is_filtered_to_region(items):
    k = by_key(items, "ktnv")
    assert k and all(re.search(r"Colorado River|Lake Mead|Laughlin|Boulder City|Mesquite|Hoover", i["title"] + " " + i["summary"]) for i in k)
    assert not any("Sunrise Manor" in i["title"] for i in k)


# ----------------------------------------------------------------------------- events
def test_civicplus_meetings(items):
    m = by_key(items, "lhc-meetings")
    assert len(m) >= 3 and all(i["kind"] == "meeting" for i in m)
    council = next(i for i in m if i["title"] == "City Council Meeting")
    assert council["event_start"] == "2026-10-27T17:30:00-07:00" and "Acoma" in council["venue"]
    assert council["summary"] == "" and NOW - 7200 <= council["ts"] <= NOW   # stale pubDate replaced by fetch time
    bc = by_key(items, "bc-meetings")
    assert bc and all(i["event_start"].startswith("2026-10-2") and i["kind"] == "meeting" for i in bc)  # pubDate was 2024


def test_events_calendar_dates(items):
    ev = by_key(items, "visitlaughlin-events")
    assert len(ev) >= 10 and all(i["kind"] == "event" for i in ev)
    cruise = next(i for i in ev if i["title"].startswith("Line Dancing"))
    assert cruise["event_start"] == "2026-10-20T12:00:00-07:00" and cruise["event_end"].startswith("2026-10-20T23:59")
    assert cruise["summary"].startswith("This unique Colorado River cruise") and "10/20/2026" not in cruise["summary"]
    assert not any(i["title"] in {"Roxy Gunn Project", "L.A. Comedy Club"} for i in ev)   # open-ended runs are not dated events
    # nothing that already ended; a multi-day event that started a few days ago (BITD Desert Classic, Oct 15-19) stays
    assert all(dt.datetime.fromisoformat(i.get("event_end") or i["event_start"]) >= dt.datetime(2026, 10, 17, tzinfo=dt.timezone.utc) for i in ev)
    assert any(i["title"].startswith("Best in the Desert") and i["event_start"].startswith("2026-10-15") for i in ev)


# ----------------------------------------------------------------------------- robustness
def test_failing_feed_does_not_raise(monkeypatch):
    reg = sources.load_registry()
    reg["sources"] = [s for s in reg["sources"] if s["key"] in {"mohave-county", "ktnv", "bouldercityreview"}]
    reg["sources"].append({**reg["sources"][0], "key": "no-such-fixture", "name": "Nowhere"})
    real = sources.fetch_feed
    def boom(src, session=None, offline=None):
        if src["key"] == "ktnv": raise ConnectionError("simulated outage")
        return real(src, session=session, offline=offline)
    monkeypatch.setattr(sources, "fetch_feed", boom)
    logs = []
    out = sources.load_local_items(None, registry=reg, offline_dir=FIX, now=NOW, log=logs.append)
    assert out and by_key(out, "mohave-county") and not by_key(out, "ktnv")
    assert any("WARN source ktnv" in l and "simulated outage" in l for l in logs)
    assert any(l.startswith("local sources: 2 feeds ok, 1 failed") for l in logs)


def test_unparseable_fixture_does_not_raise(tmp_path):
    (tmp_path / "mohave-county.xml").write_bytes(b"\x00\x01 this is not xml")
    reg = sources.load_registry(); reg["sources"] = [s for s in reg["sources"] if s["key"] == "mohave-county"]
    logs = []
    assert sources.load_local_items(None, registry=reg, offline_dir=tmp_path, now=NOW, log=logs.append) == []
    assert any("WARN source mohave-county" in l for l in logs)


def test_sources_disabled_env(monkeypatch):
    monkeypatch.setenv("SOURCES_DISABLED", "1")
    assert sources.load_local_items(None, offline_dir=FIX, now=NOW, log=lambda m: None) == []
    assert conditions.fetch_conditions() == {}


# ----------------------------------------------------------------------------- conditions
@pytest.fixture(scope="module")
def cond():
    return json.loads((FIX / "conditions.json").read_text(encoding="utf-8"))


def test_conditions_offline_fixture(monkeypatch, cond):
    monkeypatch.setattr(conditions, "SRC", str(ROOT / "tests/fixtures"))
    c = conditions.fetch_conditions()
    assert c == cond and c["fetched"] and set(c["cities"]) == {x["key"] for x in conditions.CITIES}
    assert all("alerts" in city and "regions" in city for city in c["cities"].values())
    assert any(city.get("forecast") for city in c["cities"].values())
    assert all(r["site"] in conditions.SITES for r in c["rivers"])


def test_aqi_label():
    assert conditions.aqi_label(34) == "Good" and conditions.aqi_label(75) == "Moderate" and conditions.aqi_label(320) == "Hazardous"
    assert conditions.aqi_label(None) == ""


def test_render_strip(cond):
    assert conditions.render_strip({}) == "" and conditions.render_strip(cond, "no-such-region") == ""
    html = conditions.render_strip(cond)
    assert html.startswith('<ul class="cond"') and 'aria-label' in html and "Bullhead City" in html and "AQI" in html
    assert all(cls.startswith("cond") for cls in re.findall(r'class="([^"]+)"', html) for cls in cls.split())
    assert "<script" not in html
    mesq = conditions.render_strip(cond, "mesquite")
    assert "Mesquite" in mesq and "Bullhead City" not in mesq
    if any(r["site"] == "09415000" for r in cond["rivers"]): assert "Virgin River" in mesq
    strip = conditions.render_strip(cond, "colorado-river")
    assert "Bullhead City" in strip and "Lake Havasu City" in strip and "Kingman" not in strip


def test_render_strip_alerts_first():
    c = {"fetched": "x", "cities": {"k": {"key": "k", "name": "Kingman", "regions": ["kingman"], "alerts": ["a1"],
                                          "forecast": [{"name": "Today", "temperature": 71, "unit": "F", "shortForecast": "Sunny"}],
                                          "aqi": {"value": 34, "category": "Good"}}},
         "alerts": [{"id": "a1", "event": "Red Flag Warning", "severity": "Severe", "areas": "Northwest Plateau", "link": "https://api.weather.gov/alerts/a1"}],
         "rivers": [{"site": "09423000", "name": "Colorado River below Davis Dam", "regions": ["kingman"], "flow_cfs": 9870, "link": "https://waterdata.usgs.gov/monitoring-location/09423000/"}]}
    html = conditions.render_strip(c, "kingman")
    assert html.index("cond-alert--severe") < html.index("cond-wx") < html.index("cond-aqi") < html.index("cond-river")
    assert "Red Flag Warning" in html and "71°F" in html and "Sunny" in html and "AQI</span> <span class=\"cond-val\">34</span>" in html and "9,870 cfs" in html
    assert 'href="https://api.weather.gov/alerts/a1"' in html


def test_write_conditions(tmp_path):
    out = conditions.write_conditions(tmp_path, cond={"fetched": "2026-10-18T13:00:00+00:00", "cities": {}, "alerts": [], "rivers": []})
    assert out["fetched"] and json.loads((tmp_path / "data/conditions.json").read_text())["cities"] == {}
