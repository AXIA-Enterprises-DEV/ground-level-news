"""Unit tests for scripts/gln/taxonomy.py: publisher split, categorization, quality gate, summaries, regions, ranking, language."""
import sys, pathlib, re, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from gln import taxonomy as T, config as C

GN = "Top stories - Google News"

# ---------------------------------------------------------------- titles / publisher split
def test_gn_split_keeps_hyphenated_publishers():
    assert T.normalize_title("Raiders fall to Chiefs in overtime - Las Vegas Review-Journal", GN) == ("Raiders fall to Chiefs in overtime", "Las Vegas Review-Journal")
    assert T.normalize_title("Small business owners brace for tariffs - WISH-TV", "Google News: small business owners") == ("Small business owners brace for tariffs", "WISH-TV")
    assert T.normalize_title("Markets wobble - ASHARQ AL-AWSAT English", GN)[1] == "ASHARQ AL-AWSAT English"

def test_gn_split_uses_last_dash_and_pipe():
    assert T.normalize_title("Stocks fall - what to know - The New York Times", GN) == ("Stocks fall - what to know", "The New York Times")
    assert T.normalize_title("Fed holds rates | CNBC", GN) == ("Fed holds rates", "CNBC")
    assert T.normalize_title("Office 2021 support ends this month – you have 5 options", "The Verge") == ("Office 2021 support ends this month – you have 5 options", None)

def test_title_label_and_caps():
    t, pub, kind = T.normalize_title_full("OPINION: Rent control will not fix Nevada housing costs", "Las Vegas Review-Journal")
    assert kind == "opinion" and t.startswith("Rent control") and pub is None
    assert T.normalize_title("HORIZON AIR TEAMSTERS TO PICKET IN IDAHO", "PR Newswire M&A")[0] == "Horizon Air Teamsters to Picket in Idaho"

# ---------------------------------------------------------------- publisher
def test_publisher_tiers_and_defaults():
    p = T.publisher({"source": GN, "title": "Something happened - Reuters", "link": "https://news.google.com/x"})
    assert p["name"] == "Reuters" and p["tier"] == 1 and p["domain"] == "reuters.com" and p["paywalled"] is False
    p = T.publisher({"source": "Las Vegas Review-Journal", "title": "x", "link": "https://www.reviewjournal.com/a"})
    assert p["tier"] == 2 and "regional" in p["flags"] and p["paywalled"] is True
    p = T.publisher({"source": "Some Unknown Feed", "title": "x", "link": "https://example.org/a"})
    assert p["tier"] == 4 and p["domain"] == "example.org"
    p = T.publisher({"source": GN, "title": "Options flow - MarketBeat", "link": "https://news.google.com/x"})
    assert p["tier"] == 5
    for k in ("name", "home", "tier", "domain", "paywalled"): assert k in p

# ---------------------------------------------------------------- categorize (taxonomy.md §3.3 clear wins)
CASES = [
    ("The Economic Times", "business", "Aegis Logistics shares rise 3% after firm acquires 90% stake in Vopak", "markets"),
    ("The New York Times", "world", "He's Played It Safe. But He Could Make California History as Governor", "politics"),
    ("AP News", "world", "Trump wants the midterms to be all about himself", "politics"),
    ("Daily Sun", "politics", "Bangladesh JSD condemns attack on GM Quader's residence", "world"),
    ("The Economic Times", "business", "BHEL shares fall 4% despite Q2 profit jumping 119%", "markets"),
    ("The New York Times", "world", "Justice Dept. Issues Subpoenas in Ilhan Omar Investigation", "politics"),
    ("Al Jazeera", "world", "Trump says oil, gas and mineral exploration to begin in Greenland", "politics"),
    ("EnergyNow", "markets", "Qatar Brings LNG Tankers Into Hormuz Despite Shipping Slowdown", "world"),
    ("CNBC", "markets", "Tesla plans next-generation Roadster reveal for December", "tech"),
    ("Inc.", "tech", "Former DHS Chief Napolitano Says the Biggest AI Risk Isn't Losing to China", "world"),
    ("Nevada Business Magazine", "business", "Rio Hotel & Casino Becomes First Las Vegas Resort to Launch ChatGPT Experience", "tech"),
    ("BBC News", "business", "Is it OK for jobseekers or employers to use AI?", "tech"),
    ("PennLive", "politics", "State police give some businesses more time to remove skill games", "us"),
    ("Inc.", "tech", "KFC Is Dropping Pepsi After 37 Years for Coca-Cola", "business"),
    ("The Economic Times", "business", "NY Fed President Williams sees no need for a rate hike in 2027", "markets"),
    ("Star Observer", "business", "Sydney's LGBTQ+ Small Business Fair Returns This Saturday", "world"),
    ("Bozeman Daily Chronicle", "world", "Madrid demands La Liga president resigns after Miami match fiasco", "sports"),
    ("MarketWatch", "markets", "Is Apple's foldable iPhone Duo worth $2,000? Here is what we know", "tech"),
    ("Las Vegas Review-Journal", "us", "Boulder City wins 3rd straight Class 3A girls golf state title", "sports"),
    ("thekabultribune.com", "markets", "Strait of Hormuz Disruption Chokes Trade and Aid Routes to Afghanistan", "world"),
]

def _gn(pub, upstream, title):
    return {"source": GN, "category": upstream, "title": f"{title} - {pub}", "summary": "", "link": "https://news.google.com/x", "projects": []}

def test_categorize_examples():
    wins = 0
    for pub, upstream, title, want in CASES:
        it = T.process(_gn(pub, upstream, title))
        if it["section"] == want: wins += 1
        else: print("MISS", pub, title, "->", it["section"], it["rule"], "want", want)
    assert wins >= 17, wins

def test_categorize_source_overrides_and_state_courts():
    assert T.categorize({"source": "Phys.org - latest science and technology news stories", "title": "AI model predicts protein folds", "summary": "", "projects": []}) == "science"
    assert T.categorize({"source": "SCOTUSblog", "title": "Court grants review in tariff case", "summary": ""}) == "politics"
    assert T.categorize(T.process(_gn("VTDigger", "politics", "Vermont Supreme Court upholds school funding law"))) == "us"
    assert T.categorize(T.process(_gn("Hindustan Times", "politics", "India Supreme Court stays Delhi stray dog order"))) == "world"
    assert T.categorize(T.process(_gn("The Hill", "world", "Supreme Court declines lobster-fisherman case"))) == "politics"
    assert T.categorize({"source": "Al Jazeera", "category": "world", "title": "Man City beat PSG in Champions League thriller", "summary": ""}) == "sports"
    assert T.categorize({"source": "All News", "category": "business", "title": "Russia hits Ukraine's energy sector 76 times in a week, Zelenskiy says", "summary": ""}) == "world"
    assert T.categorize({"source": "Las Vegas Review-Journal", "category": "us", "title": "Motorcyclist critical after crash on US-95 near Searchlight", "summary": ""}) == "us"
    assert T.categorize({"source": "Las Vegas Review-Journal", "category": "us", "title": "Golden Knights rout Penguins behind defensemen", "summary": ""}) == "sports"

def test_categorize_always_returns_section_key():
    for it in ({"source": "", "title": "", "summary": ""}, {"source": "Weird", "title": "Zzz", "summary": "", "category": "filings"}, {"source": "X", "title": "Y", "category": "local", "via": "direct"}):
        assert T.categorize(it) in C.CAT_NAME and T.categorize(it) != "local"

# ---------------------------------------------------------------- quality gate
def _q(source, title, summary="", **kw):
    it = {"source": source, "title": title, "summary": summary, "link": "https://example.com/x", "projects": [], **kw}
    return T.quality(T.process(it) | {"summary": summary})

def test_quality_drops_junk():
    assert _q("Money Crashers", "7 Best ETFs to Buy Now – Our Top Picks", "Long evergreen text " * 10)[0] is False
    assert _q("Money Saving Mom®", "*HOT* Beats Solo Buds only $54.99 shipped!", "deal text " * 10)[0] is False
    assert _q("Hacker News", "Show HN: A tiny Lisp in 400 lines", "Comments")[0] is False
    assert _q("Technical Information Security Content & Discussion", "Weekly discussion thread", "submitted by /u/someone [link] [comments]")[0] is False
    assert _q("Personal Finance", "Should I pay off my car?", "submitted by /u/x")[0] is False
    assert _q("PR Newswire M&A", "SHAREHOLDER ALERT: Law firm announces securities fraud lawsuit against ACME", "text " * 20)[0] is False
    assert _q("PR Newswire General Business", "Acme Corp announces pricing of public offering", "NEW YORK, Oct. 14, 2026 /PRNewswire/ -- " + "text " * 20)[0] is False  # no home dateline
    keep, score, reasons = _q("PR Newswire General Business", "Southwest Gas declares quarterly dividend", "LAS VEGAS, Oct. 14, 2026 /PRNewswire/ -- Southwest Gas Holdings " + "text " * 20)
    assert keep and score < 1 and "pr_local" in reasons
    assert _q("Google News: unusual options activity", "Unusual call options activity in NVDA - Barchart", "x " * 30)[0] is False
    assert _q("All News", "Why is Tesla stock surging today?", "")[0] is False

def test_quality_keeps_and_demotes():
    keep, score, reasons = _q("Guardian World", "France in shock after protests devolve into riots", "Paris saw a third night of violence as " + "words " * 20)
    assert keep and score == 1.0 and reasons == []
    keep, score, reasons = _q("SCOTUSblog", "Court grants review in tariff case", "")
    assert keep and score == 0.5 and "no_summary" in reasons
    keep, score, reasons = _q("Forbes - Business", "Netflix lays off 300 staff in restructuring", "Netflix said " + "words " * 20)
    assert keep and score == 0.5 and "tier4_source" in reasons
    keep, score, reasons = _q("Las Vegas Sun", "El nuevo centro de Boulder City abre sus puertas para los visitantes del lago", "La ciudad de Boulder City anuncia la apertura del centro para los visitantes con una exposición sobre la historia de la presa.")
    assert keep and "lang:es" in reasons
    assert _q("Business Wire", "Acme lanza una nueva plataforma para los clientes de la región", "Resumen: la compañía anuncia una plataforma para los clientes del mercado")[0] is False
    # direct regional items are never dropped for short summaries
    keep, score, _ = _q("Lake Havasu City", "Street sealing begins Oct. 18", "", via="direct", tier=1, regions=["lake-havasu-city"])
    assert keep

# ---------------------------------------------------------------- summaries
def test_clean_summary():
    assert T.clean_summary("Title here", "Title here") == ""
    assert T.clean_summary("Title here", "<p>Title here.</p>") == ""
    assert T.clean_summary("X", "Comments") == ""
    assert T.clean_summary("X", "Article URL: https://a.b Comments URL: https://c.d Points: 12 # Comments: 3") == ""
    s = T.clean_summary("Fed holds", "The Federal Reserve left interest rates unchanged on Wednesday, citing persistent inflation and a cooling labor market. Continue reading…")
    assert s.endswith("labor market.") and "Continue" not in s
    s = T.clean_summary("Fed holds", "The Federal Reserve left interest rates unchanged on Wednesday, citing persistent inflation. The post Fed holds rates appeared first on Money Blog.")
    assert "appeared first" not in s and s.endswith("inflation.")
    s = T.clean_summary("Fed holds", "The Federal Reserve left interest rates unchanged on Wednesday, citing persistent inflation and more [&hellip;]")
    assert "[" not in s
    s = T.clean_summary("Galaxy", "APOD: 2026 October 17 - Galaxy &lt; | Archive | Submissions | Index | Search | Calendar | RSS | Education | About APOD | Discuss | &gt; Explanation: A spiral galaxy seen edge-on shows dust lanes that stretch across thousands of light-years of space.")
    assert s.startswith("A spiral galaxy") and "Archive" not in s
    s = T.clean_summary("Fed holds", "Fed holds. The Federal Reserve left interest rates unchanged on Wednesday, citing persistent inflation and a cooling labor market.")
    assert s.startswith("The Federal Reserve")
    assert T.clean_summary("T", "Short blurb only.") == ""
    s = T.clean_summary("T", "The city council approved the measure late on Tuesday after a long and heated public comment period at city hall - Las Vegas Review-Journal")
    assert not s.endswith("Review-Journal")

# ---------------------------------------------------------------- regions
def test_detect_regions_parents_and_false_friends():
    r = T.detect_regions("Early voting opens in Laughlin on Saturday")
    assert r[0] == "laughlin" and {"clark-county", "nevada", "colorado-river"} <= set(r)
    assert "las-vegas" in T.detect_regions("Henderson, Nev., police arrest suspect") and "henderson" in T.detect_regions("Henderson, Nev., police arrest suspect")
    assert T.detect_regions("Henderson, Ky., man arrested") == []
    assert T.detect_regions("Mesquite tree removal in Texas") == []
    assert T.detect_regions("Sierra Nevada snowpack grows after storm") == []
    assert T.detect_regions("Franco-Nevada posts record quarter") == []
    assert T.detect_regions("Las Vegas, New Mexico, celebrates fiesta") == []
    assert T.detect_regions("Arizona Cardinals lose again") == []
    assert T.detect_regions("Israeli strikes hit Gaza Strip") == []
    assert T.detect_regions("Red Raiders upset Texas") == []
    assert "lake-mead" in T.detect_regions("Hoover Dam tours resume") and "boulder-city" in T.detect_regions("Hoover Dam tours resume")
    assert T.detect_regions("Lake Mead Blvd closed for repairs") == [] or "lake-mead" not in T.detect_regions("Lake Mead Blvd closed for repairs")
    assert "mohave-valley" in T.detect_regions("Fort Mojave Mesa Fire Department open house")
    assert "needles" in T.detect_regions("City of Needles approves budget")
    assert "needles" not in T.detect_regions("Pine needles cover the trail")
    assert "kingman" not in T.detect_regions("Kingman, Kan., tornado")
    assert "nevada" in T.detect_regions("Reno casino opens") and "lake-havasu-city" in T.detect_regions("Lake Havasu City street sealing")
    assert "arizona" in T.detect_regions("Lake Havasu City street sealing")

def test_detect_regions_dateline_and_regional_context():
    assert "las-vegas" in T.detect_regions("LAS VEGAS, Oct. 14, 2026 /PRNewswire/ -- Southwest Gas declares dividend")
    assert "bullhead-city" in T.detect_regions("BULLHEAD CITY, Ariz. -- The council met Tuesday")
    assert "las-vegas" in T.detect_regions("Metro investigates shooting on the Strip", "Las Vegas Review-Journal")
    assert "las-vegas" not in T.detect_regions("Metro investigates shooting on the Strip", "BBC News")
    assert "henderson" in T.detect_regions("Henderson council approves budget", "Las Vegas Sun")
    assert "henderson" not in T.detect_regions("Henderson scores twice", "ESPN")

def test_regions_table_shape():
    required = ["bullhead-city", "laughlin", "mohave-valley", "lake-havasu-city", "kingman", "mohave-county", "clark-county", "las-vegas", "henderson",
                "north-las-vegas", "mesquite", "boulder-city", "lake-mead", "colorado-river", "needles", "nevada", "arizona"]
    for k in required: assert k in T.REGIONS, k
    for k, r in T.REGIONS.items():
        for f in ("name", "state", "kind", "aliases", "parent", "intro", "links", "home"): assert f in r, (k, f)
        assert r["kind"] in ("city", "county", "area", "state", "river")
        assert r["parent"] is None or r["parent"] in T.REGIONS
        if r["home"]: assert len(r["intro"]) > 120, k
    assert T.REGIONS["bullhead-city"]["wikidata"] == "Q79432" and T.REGIONS["nevada"]["wikidata"] == "Q1227"
    assert any(re.search(a, "Mojave Valley", re.I) for a in T.REGIONS["mohave-valley"]["aliases"])
    assert "nevada" not in T.HOME_REGIONS and "laughlin" in T.HOME_REGIONS
    assert {k for k, _, _ in C.LOCAL_AREAS} <= T.HOME_REGIONS

def test_area_to_region_covers_press_releases():
    import yaml
    areas = set()
    for f in (ROOT / "content/press-releases").glob("*.md"):
        m = re.match(r"^---\s*\n(.*?)\n---", f.read_text(encoding="utf-8"), re.S)
        fm = yaml.safe_load(m.group(1)) or {}
        if fm.get("area"): areas.add(str(fm["area"]))
    for a in areas:
        key = T.area_to_region(a)
        if a == "Example": assert key is None
        else: assert key in T.REGIONS, (a, key)
    assert T.area_to_region("Mojave Valley") == "mohave-valley" and T.area_to_region("Mohave Valley") == "mohave-valley"
    assert T.area_to_region("Lake Mead") == "lake-mead" and T.area_to_region("Fort Mohave, AZ") == "mohave-valley"
    assert T.area_to_region("Searchlight") == "laughlin" and T.area_to_region("Hoover Dam area") == "lake-mead"
    assert T.area_to_region("Timbuktu") is None and T.area_to_region("") is None

# ---------------------------------------------------------------- topics, ranking, language
def test_topics():
    t = T.detect_topics({"title": "Arizona joins Nevada to fight proposed cuts to their shares of Colorado River water", "summary": "", "projects": ["oil"]})
    assert "water" in t and "energy" in t
    for k, v in T.TOPICS.items():
        assert v["color"] in C.brand.CAT_COLORS if C.brand else True
        assert v["name"] and v["intro"]
    assert {k for k, _, _ in C.TOPIC_LINKS} <= set(T.TOPICS)

def test_rank_prefers_fresh_tier1_with_summary_and_local():
    now = int(time.time())
    base = {"summary": "x" * 60, "section": "us", "tier": 1, "regions": [], "local": False}
    fresh = {**base, "title": "Fresh story", "ts": now - 600}
    old = {**base, "title": "Old story", "ts": now - 86400}
    demoted = {**base, "title": "Fresh demoted", "ts": now - 600, "demoted": True}
    tier4 = {**base, "title": "Fresh aggregator", "ts": now - 600, "tier": 4, "demoted": True}
    local = {**base, "title": "Fresh local", "ts": now - 3600 * 6, "tier": 2, "local": True, "regions": ["bullhead-city"]}
    ranked = T.rank([old, demoted, tier4, fresh, local], now)
    assert ranked[0]["title"] == "Fresh local" and ranked[1]["title"] == "Fresh story" and ranked[-1]["title"] == "Old story"
    assert T.score(fresh, now) > T.score(demoted, now) > T.score(tier4, now) and T.score(local, now) > T.score(fresh, now)

def test_cluster_groups_same_day_near_duplicates():
    now = int(time.time())
    a = {"title": "Guilfoyle resigns as ambassador amid probe", "ts": now, "score": 50, "tier": 1}
    b = {"title": "Kimberly Guilfoyle resigns as ambassador amid ethics probe", "ts": now - 100, "score": 40, "tier": 2}
    c = {"title": "Fed holds rates steady", "ts": now, "score": 30, "tier": 1}
    groups = T.cluster([a, b, c])
    assert len(groups) == 2 and a["cluster_size"] == 2 and b in a["also"] and a["cluster_rep"] and not b["cluster_rep"] and c["also"] == []

def test_lang():
    assert T.lang({"title": "Fed holds rates steady as inflation cools", "summary": ""}) == "en"
    assert T.lang({"title": "La policía escolar del Condado Clark anuncia nuevas medidas para los estudiantes", "summary": ""}) == "es"
    assert T.lang({"title": "Die Bundesregierung hat die Pläne für das neue Gesetz auf Eis gelegt", "summary": ""}) == "de"
    assert T.lang({"title": "Le gouvernement annonce des mesures pour les entreprises dans le pays", "summary": ""}) == "fr"
    assert T.lang({"title": "Нефть подорожала на фоне новостей из Ормузского пролива", "summary": ""}) == "ru"
    assert T.lang({"title": "日本の首相が新たな経済対策を発表", "summary": ""}) == "ja" or T.lang({"title": "日本の首相が新たな経済対策を発表", "summary": ""}) == "zh"
