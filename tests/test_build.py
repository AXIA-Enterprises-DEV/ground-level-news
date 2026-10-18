"""Smoke tests: an offline build from the saved feed fixture must succeed and produce the key files.
Run: python -m pytest tests/  (takes ~20s; set OG_STORIES=0 to skip share cards)"""
import os, subprocess, sys, pathlib, re, json
ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests/fixtures"

def build(tmp_path):
    out = tmp_path / "site"
    env = {**os.environ, "TRACKER_BASE": str(FIX), "OUT_DIR": str(out), "OG_STORIES": os.environ.get("OG_STORIES", "5")}
    r = subprocess.run([sys.executable, str(ROOT / "scripts/build.py")], env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return out

def test_offline_build(tmp_path):
    out = build(tmp_path)
    for f in ["index.html", "rss.xml", "feed.xml", "sitemap.xml", "news-sitemap.xml", "robots.txt", "llms.txt", "llms-full.txt",
              "agents.txt", "ai.txt", "404.html", "press-releases/index.html", "about/index.html", "llm-info/index.html", "identity/index.html"]:
        assert (out / f).exists(), f
    assert len(list((out / "story").glob("*/index.html"))) > 100
    home = (out / "index.html").read_text()
    assert "<title>" in home and 'rel="canonical"' in home and "application/ld+json" in home
    # every story page has a Markdown twin and an isBasedOn link
    st = next((out / "story").glob("*/index.html"))
    assert (out / "story" / (st.parent.name + ".md")).exists()
    assert "isBasedOn" in st.read_text()
    # LLM layer checker passes on the fixture build
    r = subprocess.run([sys.executable, str(ROOT / "scripts/check_llm_layer.py"), str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]

def test_no_blocked_names(tmp_path):
    out = build(tmp_path)
    rx = re.compile(r"\b(axia|clem)\b", re.I)
    bad = [p for p in out.rglob("*.html") if rx.search(p.read_text(errors="ignore"))]
    assert not bad, bad[:5]
