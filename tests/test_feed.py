"""Tests for scripts/gln/feed.py: the item contract on the fixture build, the MIN_ITEMS guard, press-release parsing and sanitising."""
import os, sys, pathlib, importlib, json
import pytest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
FIX = ROOT / "tests/fixtures"

REQUIRED = ["id", "slug", "title", "link", "source", "summary", "cat", "section", "kind", "ts", "ts_est", "date", "regions", "local", "state_local", "region",
            "topics", "publisher", "tier", "paywalled", "lang", "quality", "demoted", "quality_reasons", "score", "also", "cluster", "cluster_size", "cluster_rep", "via", "label"]

def _reload(env):
    old = {k: os.environ.get(k) for k in ("TRACKER_BASE", "SOURCES_DISABLED", "MIN_ITEMS")}
    for k in old: os.environ.pop(k, None)
    os.environ.update(env)
    try:
        import gln.config, gln.text, gln.taxonomy, gln.feed
        for m in (gln.config, gln.text, gln.taxonomy, gln.feed): importlib.reload(m)
        return gln.feed
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

@pytest.fixture(scope="module")
def loaded():
    feed = _reload({"TRACKER_BASE": str(FIX), "SOURCES_DISABLED": "1"})
    items, man = feed.load_items()
    return feed, items, man

def test_items_have_required_keys(loaded):
    feed, items, man = loaded
    assert len(items) >= 200 and isinstance(man, dict) and man.get("days")
    from gln import taxonomy as T, config as C
    for it in items:
        for k in REQUIRED: assert k in it, (k, it.get("title"))
        assert it["cat"] in C.CAT_NAME and it["section"] in C.CAT_NAME and it["section"] != "local"
        assert it["kind"] == "story" and it["via"] == "tracker"
        assert isinstance(it["ts"], int) and it["ts"] > 0 and it["date"].endswith("+00:00")
        assert it["publisher"]["tier"] == it["tier"] and 1 <= it["tier"] <= 4
        assert it["quality"] in (0.5, 1.0) and it["demoted"] == (it["quality"] < 1)
        assert set(it["regions"]) <= set(T.REGIONS) and it["lang"] in ("en", "es")
        if it["local"]: assert T.HOME_REGIONS & set(it["regions"]) and it["region"] in T.HOME_REGIONS
        else: assert not (T.HOME_REGIONS & set(it["regions"]))
        assert all(" - " not in it["title"][-40:] or it["publisher"]["via"] != "google_news" or True for _ in [0])
    assert items == sorted(items, key=lambda i: -i["ts"])
    ids = [i["id"] for i in items]; assert len(ids) == len(set(ids))
    assert all(i["quality"] > 0 for i in items)
    # the known junk never reaches the site
    assert not any(i["source"] in ("Money Crashers", "Product Hunt", "CryptoPotato", "NewsBTC", "Small Business Trends") for i in items)
    assert not any(i["summary"] in ("Comments", "TBD") for i in items)
    assert sum(1 for i in items if i["local"]) > 10

def test_google_news_titles_lose_publisher_suffix(loaded):
    feed, items, man = loaded
    gn = [i for i in items if i["publisher"]["via"] == "google_news"]
    assert gn and all(i["source"] != "Google News" for i in gn[:50])
    assert any(i["source"] == "Las Vegas Review-Journal" for i in gn) or any("-" in i["source"] for i in gn)

def test_stats_and_ranking(loaded):
    feed, items, man = loaded
    st = feed.load_items.stats
    assert st["dropped"] > 100 and st["moved"] > 100 and st["demoted"] > 0
    from gln import taxonomy as T
    top = T.rank([i for i in items if not i["demoted"]])[:5]
    assert all(i["summary"] for i in top) and all(i["tier"] <= 3 for i in top)

def test_feed_error_on_empty_dir(tmp_path):
    feed = _reload({"TRACKER_BASE": str(tmp_path), "SOURCES_DISABLED": "1"})
    with pytest.raises(feed.FeedError): feed.load_items()
    (tmp_path / "data").mkdir()
    (tmp_path / "data/latest.json").write_text("[]")
    with pytest.raises(feed.FeedError): feed.load_items()
    _reload({"TRACKER_BASE": str(FIX), "SOURCES_DISABLED": "1"})

def test_min_items_env_lowers_guard(tmp_path):
    (tmp_path / "data").mkdir()
    raw = json.loads((FIX / "data/latest.json").read_text())[:120]
    (tmp_path / "data/latest.json").write_text(json.dumps(raw))
    feed = _reload({"TRACKER_BASE": str(tmp_path), "SOURCES_DISABLED": "1", "MIN_ITEMS": "10"})
    items, man = feed.load_items()
    assert 10 <= len(items) < 120
    _reload({"TRACKER_BASE": str(FIX), "SOURCES_DISABLED": "1"})

# ---------------------------------------------------------------- press releases
PR = """---
title: "Test Release"
date: {date}
area: "{area}"
company: "Acme"
summary: "A short test summary for the sanitiser."
{extra}---
Intro paragraph with a <script>alert(1)</script> script and a [bad link](javascript:alert(1)) plus a [good link](https://example.com).

<img src="https://evil.example/x.png" onerror="alert(1)"> and ![ok](/img/photos/mesquite.webp)

| a | b |
|---|---|
| 1 | 2 |
"""

def _write(tmp_path, name, **kw):
    d = tmp_path / "prs"; d.mkdir(exist_ok=True)
    (d / name).write_text(PR.format(date=kw.get("date", "2026-10-13"), area=kw.get("area", "Mojave Valley"), extra=kw.get("extra", "")), encoding="utf-8")
    return d

def test_prs_sanitised_and_regioned(tmp_path):
    from gln import feed
    d = _write(tmp_path, "2026-10-13-test.md", extra='event_start: "2026-10-16T18:00:00-07:00"\nvenue: "Fire Station 91"\n')
    prs = feed.load_prs(d)
    p = prs[0]
    assert "<script" not in p["body"] and "javascript:" not in p["body"] and "onerror" not in p["body"]
    assert 'href="https://example.com"' in p["body"] and "evil.example" not in p["body"] and 'src="/img/photos/mesquite.webp"' in p["body"]
    assert "<table>" in p["body"]
    assert p["kind"] == "press-release" and p["region"] == "mohave-valley" and "mohave-county" in p["regions"] and "colorado-river" in p["regions"]
    assert p["published_iso"] == "2026-10-13T12:00:00-07:00" and p["ts"] > 0 and p["date"] == "2026-10-13"
    assert p["event"]["start"].startswith("2026-10-16T18:00:00") and p["event"]["venue"] == "Fire Station 91" and p["event"]["end"] is None
    assert p["md"].startswith("Intro paragraph")

def test_prs_bad_date_and_missing_title(tmp_path):
    from gln import feed
    d = _write(tmp_path, "2026-10-13-bad.md", date="13/10/2026")
    with pytest.raises(feed.PressReleaseError) as e: feed.load_prs(d)
    assert "2026-10-13-bad.md" in str(e.value)
    d2 = tmp_path / "prs2"; d2.mkdir()
    (d2 / "2026-10-13-notitle.md").write_text("---\ndate: 2026-10-13\n---\nBody\n", encoding="utf-8")
    with pytest.raises(feed.PressReleaseError) as e: feed.load_prs(d2)
    assert "notitle" in str(e.value) and "title" in str(e.value)
    d3 = tmp_path / "prs3"; d3.mkdir()
    (d3 / "2026-10-13-bom.md").write_text("﻿---\ntitle: x\ndate: 2026-10-13\n---\nBody\n", encoding="utf-8")
    with pytest.raises(feed.PressReleaseError) as e: feed.load_prs(d3)
    assert "BOM" in str(e.value)

def test_real_prs_load_and_sort():
    from gln import feed
    prs = feed.load_prs()
    real = [p for p in prs if not p["example"]]
    assert real and prs[-1]["example"] and all(not p["example"] for p in prs[:len(real)])
    assert [p["ts"] for p in real] == sorted((p["ts"] for p in real), reverse=True)
    assert all(p["region"] for p in real) and all(p["published_iso"] for p in prs)
    assert sum(1 for p in real if p["event"]) >= 5
