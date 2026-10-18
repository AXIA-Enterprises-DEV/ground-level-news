"""Content architecture: title hygiene, publisher table, quality gate, categorization, regions, topics, ranking.
Ported from the audited prototype (scratchpad/audits/taxonomy.md, tested on 18,214 real items). Everything is
deterministic: ordered regex tables, source overrides, project hints. Pure functions over item dicts; the only
package imports are config (section keys) and text (helpers). Interface per DECISIONS §2.

Item fields read: title, summary, source, link, category (upstream), projects, regions (direct sources), via, tier.
`process(item, now_ts)` runs the whole per-item pipeline and returns a new annotated dict (used by feed.load_items)."""
import re, html, math, hashlib, datetime as dt
from collections import OrderedDict
from urllib.parse import urlparse
from .config import CAT_NAME
from .text import title_case_if_caps

SECTIONS = ["local", "us", "world", "politics", "business", "markets", "tech", "science", "sports"]

def _rx(p, flags=re.I): return re.compile(p, flags)
def _text(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(s or "")))).strip()

# ====================================================================== 1. TITLE HYGIENE
# Google News titles end in " - Publisher". Split on the LAST " - " (greedy left) so hyphenated publishers survive
# ("Las Vegas Review-Journal", "WISH-TV"); the publisher may contain hyphens but no further spaced dash or pipe.
_GN_SPLIT = _rx(r"^(?P<t>.*\S)\s+[-–—]\s+(?P<p>[^|–—]{2,70})$", 0)
_GN_SPLIT_PIPE = _rx(r"^(?P<t>.*\S)\s+\|\s+(?P<p>[^|]{2,70})$", 0)
_SITE_TAIL = _rx(r"\s*\|\s*(?:Homes|Provided Content|New Homes|The Vergecast|One More Thing|Quantum Marketing|The Pay Check)\s*$")
_PREFIX_LABEL = _rx(r"^(?:WATCH|Video|LIVE|BREAKING|Photos?|Exclusive|Opinion|Analysis|Column|Editorial|Op-Ed|Letter|Cartoon|Review|Commentary|Explainer|Podcast|Q&A|Live updates)\s*[:|\-–]\s*")
_GN_SOURCES = ("Google News", "Top stories - Google News")

def is_google_news(source): return str(source or "").startswith(_GN_SOURCES)

def normalize_title_full(title, source=""):
    """(clean title, publisher taken from a Google News suffix or None, label kind such as 'opinion' or None)."""
    t = _text(title); pub = None
    if is_google_news(source):
        m = _GN_SPLIT.match(t) or _GN_SPLIT_PIPE.match(t)
        if m: t, pub = m.group("t").strip(), m.group("p").strip()
        t = _SITE_TAIL.sub("", t)
        if t.count("|") == 1: t = re.sub(r"\s*\|\s*[^|]{2,40}$", "", t)
    kind = None
    m = _PREFIX_LABEL.match(t)
    if m and len(t) - m.end() > 12: kind = m.group(0).strip(" :|-–").lower(); t = t[m.end():]
    t = title_case_if_caps(t)
    t = t.rstrip(" .") if not t.endswith("...") else t
    return t, pub, kind

def normalize_title(title, source=""):
    """(clean title, publisher from the Google News suffix or None). See normalize_title_full for the label kind."""
    t, pub, _ = normalize_title_full(title, source)
    return t, pub

# ====================================================================== 2. PUBLISHERS
# source string -> (display name, home URL, trust tier, default section, flags)
# tier 1 major national/international newsroom or wire; 2 reputable specialist/regional newsroom; 3 primary source
# (government/agency/company blog); 4 low-editorial aggregator/contributor network (shown, demoted); 5 junk (dropped).
PUBLISHERS = {
 "Top stories - Google News": ("Google News", "https://news.google.com", 2, None, ()),
 "Al Jazeera": ("Al Jazeera", "https://www.aljazeera.com", 1, "world", ()),
 "Guardian World": ("The Guardian", "https://www.theguardian.com", 1, "world", ()),
 "Guardian Business": ("The Guardian", "https://www.theguardian.com", 1, "business", ()),
 "Space | The Guardian": ("The Guardian", "https://www.theguardian.com", 1, "science", ()),
 "BBC World": ("BBC News", "https://www.bbc.com/news", 1, "world", ()),
 "BBC Business": ("BBC News", "https://www.bbc.com/news/business", 1, "business", ()),
 "BBC Technology": ("BBC News", "https://www.bbc.com/news/technology", 1, "tech", ()),
 "NYT World": ("The New York Times", "https://www.nytimes.com", 1, "world", ()),
 "NYT Business": ("The New York Times", "https://www.nytimes.com", 1, "business", ()),
 "NYT Politics": ("The New York Times", "https://www.nytimes.com", 1, "politics", ()),
 "NYT > Science": ("The New York Times", "https://www.nytimes.com", 1, "science", ()),
 "NYT > Technology": ("The New York Times", "https://www.nytimes.com", 1, "tech", ()),
 "NPR Politics": ("NPR", "https://www.npr.org", 1, "politics", ()),
 "NPR Business": ("NPR", "https://www.npr.org", 1, "business", ()),
 "Planet Money": ("NPR Planet Money", "https://www.npr.org/sections/money", 2, "business", ("podcast",)),
 "CNBC Top News": ("CNBC", "https://www.cnbc.com", 1, "markets", ()),
 "CNBC Finance": ("CNBC", "https://www.cnbc.com", 1, "markets", ()),
 "FT Home": ("Financial Times", "https://www.ft.com", 1, "business", ()),
 "MarketWatch Top Stories": ("MarketWatch", "https://www.marketwatch.com", 1, "markets", ()),
 "World & Nation": ("Los Angeles Times", "https://www.latimes.com", 1, "us", ()),
 "World News - Breaking News, Top Stories": ("HuffPost", "https://www.huffpost.com", 2, "us", ()),
 "Playbook": ("Politico Playbook", "https://www.politico.com/playbook", 2, "politics", ("newsletter",)),
 "The Hill Policy": ("The Hill", "https://thehill.com", 2, "politics", ()),
 "Bloomberg Originals": ("Bloomberg", "https://www.bloomberg.com", 1, "business", ("video",)),
 "Business Insider": ("Business Insider", "https://www.businessinsider.com", 4, "business", ()),
 "Forbes - Business": ("Forbes", "https://www.forbes.com", 4, "business", ("contributor",)),
 "Fortune | FORTUNE": ("Fortune", "https://fortune.com", 2, "business", ()),
 "Inc.com": ("Inc.", "https://www.inc.com", 4, "business", ()),
 "Entrepreneur": ("Entrepreneur", "https://www.entrepreneur.com", 4, "business", ()),
 "Economic Times": ("The Economic Times", "https://economictimes.indiatimes.com", 4, "markets", ("foreign_desk",)),
 "World News, Today World News, Latest International News, World Breaking News, Trending News of World - Times of India": ("Times of India", "https://timesofindia.indiatimes.com", 4, "world", ("foreign_desk",)),
 "Foreign Policy": ("Foreign Policy", "https://foreignpolicy.com", 2, "world", ()),
 "Foreign Affairs": ("Foreign Affairs", "https://www.foreignaffairs.com", 2, "world", ("analysis",)),
 "War on the Rocks": ("War on the Rocks", "https://warontherocks.com", 2, "world", ("analysis",)),
 "Crisis Group": ("International Crisis Group", "https://www.crisisgroup.org", 3, "world", ()),
 "RAND News": ("RAND Corporation", "https://www.rand.org", 3, "world", ()),
 "Defense News": ("Defense News", "https://www.defensenews.com", 2, "world", ()),
 "Breaking Defense": ("Breaking Defense", "https://breakingdefense.com", 2, "world", ()),
 "gCaptain (shipping)": ("gCaptain", "https://gcaptain.com", 2, "business", ()),
 "Dept of War (DoD) News": ("U.S. Department of War", "https://www.war.gov", 3, "us", ("gov",)),
 "Dept of War (DoD) Releases": ("U.S. Department of War", "https://www.war.gov", 3, "us", ("gov",)),
 "START (UMD) Terrorism Research": ("START (University of Maryland)", "https://www.start.umd.edu", 3, "world", ()),
 "Las Vegas Review-Journal": ("Las Vegas Review-Journal", "https://www.reviewjournal.com", 2, "us", ("regional",)),
 "Las Vegas Sun": ("Las Vegas Sun", "https://lasvegassun.com", 2, "us", ("regional",)),
 "KTNV Las Vegas": ("KTNV 13 Action News", "https://www.ktnv.com", 2, "us", ("regional",)),
 "The Nevada Independent": ("The Nevada Independent", "https://thenevadaindependent.com", 2, "us", ("regional",)),
 "SCOTUSblog": ("SCOTUSblog", "https://www.scotusblog.com", 2, "politics", ()),
 "Federal News Network": ("Federal News Network", "https://federalnewsnetwork.com", 2, "politics", ()),
 "Government Executive": ("Government Executive", "https://www.govexec.com", 2, "politics", ()),
 "CBO Publications": ("Congressional Budget Office", "https://www.cbo.gov", 3, "politics", ("gov",)),
 "GAO Reports": ("U.S. Government Accountability Office", "https://www.gao.gov", 3, "politics", ("gov",)),
 "Federal Register Presidential Docs": ("Federal Register", "https://www.federalregister.gov", 3, "politics", ("gov",)),
 "Congress.gov Presented to President": ("Congress.gov", "https://www.congress.gov", 3, "politics", ("gov",)),
 "Congress.gov Most-Viewed Bills": ("Congress.gov", "https://www.congress.gov", 3, "politics", ("gov",)),
 "US Courts Judiciary News": ("U.S. Courts", "https://www.uscourts.gov", 3, "politics", ("gov",)),
 "OpenSecrets News": ("OpenSecrets", "https://www.opensecrets.org", 2, "politics", ()),
 "Federal Reserve Press": ("Federal Reserve", "https://www.federalreserve.gov", 3, "markets", ("gov",)),
 "Federal Reserve Speeches": ("Federal Reserve", "https://www.federalreserve.gov", 3, "markets", ("gov",)),
 "NY Fed Liberty Street Economics": ("New York Fed", "https://libertystreeteconomics.newyorkfed.org", 3, "markets", ("gov",)),
 "SEC Press Releases": ("U.S. Securities and Exchange Commission", "https://www.sec.gov", 3, "markets", ("gov",)),
 "CFTC Press Releases": ("CFTC", "https://www.cftc.gov", 3, "markets", ("gov",)),
 "BLS Latest Numbers": ("Bureau of Labor Statistics", "https://www.bls.gov", 3, "business", ("gov",)),
 "SBA News": ("U.S. Small Business Administration", "https://www.sba.gov", 3, "business", ("gov",)),
 "EIA Today in Energy": ("U.S. Energy Information Administration", "https://www.eia.gov", 3, "business", ("gov",)),
 "EIA Press Releases": ("U.S. Energy Information Administration", "https://www.eia.gov", 3, "business", ("gov",)),
 "SEC EDGAR All Filings": ("SEC EDGAR", "https://www.sec.gov/edgar", 3, "markets", ("filings",)),
 "SEC EDGAR 8-K": ("SEC EDGAR", "https://www.sec.gov/edgar", 3, "markets", ("filings",)),
 "All News": ("Investing.com", "https://www.investing.com", 4, "markets", ("empty_summaries",)),
 "Investing.com Stock Market": ("Investing.com", "https://www.investing.com", 4, "markets", ("empty_summaries",)),
 "Investing.com Economic Indicators": ("Investing.com", "https://www.investing.com", 4, "business", ("empty_summaries",)),
 "Seeking Alpha Market Currents": ("Seeking Alpha", "https://seekingalpha.com", 4, "markets", ("empty_summaries",)),
 "OilPrice.com": ("OilPrice.com", "https://oilprice.com", 2, "markets", ()),
 "Rigzone": ("Rigzone", "https://www.rigzone.com", 2, "markets", ()),
 "HousingWire": ("HousingWire", "https://www.housingwire.com", 2, "business", ()),
 "NerdWallet": ("NerdWallet", "https://www.nerdwallet.com", 4, "markets", ("personal_finance",)),
 "The College Investor": ("The College Investor", "https://thecollegeinvestor.com", 4, "markets", ("personal_finance",)),
 "Money Under 30": ("Money Under 30", "https://www.moneyunder30.com", 4, "markets", ("personal_finance",)),
 "Money Crashers": ("Money Crashers", "https://www.moneycrashers.com", 5, "markets", ("personal_finance", "evergreen")),
 "Money Saving Mom®": ("Money Saving Mom", "https://moneysavingmom.com", 5, "markets", ("deals",)),
 "Financial Samurai": ("Financial Samurai", "https://www.financialsamurai.com", 5, "markets", ("blog",)),
 "Making Sense Of Cents": ("Making Sense of Cents", "https://www.makingsenseofcents.com", 5, "markets", ("blog",)),
 "Oblivious Investor": ("Oblivious Investor", "https://obliviousinvestor.com", 5, "markets", ("blog",)),
 "Afford Anything®": ("Afford Anything", "https://affordanything.com", 5, "markets", ("podcast",)),
 "The Ramsey Show": ("The Ramsey Show", "https://www.ramseysolutions.com", 5, "markets", ("podcast",)),
 "Money For the Rest of Us": ("Money For the Rest of Us", "https://moneyfortherestofus.com", 5, "markets", ("podcast",)),
 "MyWifeQuitHerJob.com": ("MyWifeQuitHerJob", "https://mywifequitherjob.com", 5, "business", ("blog",)),
 "The Market's Compass Technical View": ("The Market's Compass", "https://themarketscompass.substack.com", 5, "markets", ("blog",)),
 "Personal Finance": ("r/personalfinance", "https://www.reddit.com/r/personalfinance", 5, "markets", ("reddit",)),
 "Cointelegraph.com News": ("Cointelegraph", "https://cointelegraph.com", 4, "markets", ("crypto",)),
 "Bitcoin News": ("Bitcoin.com News", "https://news.bitcoin.com", 4, "markets", ("crypto",)),
 "CryptoPotato": ("CryptoPotato", "https://cryptopotato.com", 5, "markets", ("crypto",)),
 "News - Cryptonews": ("Cryptonews", "https://cryptonews.com", 5, "markets", ("crypto",)),
 "INCRYPTED": ("Incrypted", "https://incrypted.com", 5, "markets", ("crypto", "non_english")),
 "DailyCoin": ("DailyCoin", "https://dailycoin.com", 5, "markets", ("crypto",)),
 "NewsBTC": ("NewsBTC", "https://www.newsbtc.com", 5, "markets", ("crypto",)),
 "CryptoNinjas": ("CryptoNinjas", "https://www.cryptoninjas.net", 5, "markets", ("crypto", "promo")),
 "ZebPay": ("ZebPay", "https://zebpay.com/blog", 5, "markets", ("crypto", "promo")),
 "Bitcoin - The Currency of the Internet": ("r/Bitcoin", "https://www.reddit.com/r/Bitcoin", 5, "markets", ("reddit", "crypto")),
 "Ethereum": ("r/ethereum", "https://www.reddit.com/r/ethereum", 5, "markets", ("reddit", "crypto")),
 "Cryptocurrency News & Discussion": ("r/CryptoCurrency", "https://www.reddit.com/r/CryptoCurrency", 5, "markets", ("reddit", "crypto")),
 "Ethereum Foundation Blog": ("Ethereum Foundation", "https://blog.ethereum.org", 3, "tech", ("crypto",)),
 "Bitcoin Audible": ("Bitcoin Audible", "https://bitcoinaudible.com", 5, "markets", ("podcast", "crypto")),
 "PR Newswire M&A": ("PR Newswire", "https://www.prnewswire.com", 4, "business", ("pr",)),
 "PR Newswire General Business": ("PR Newswire", "https://www.prnewswire.com", 4, "business", ("pr",)),
 "PR Newswire Contracts": ("PR Newswire", "https://www.prnewswire.com", 4, "business", ("pr",)),
 "PR Newswire Joint Ventures": ("PR Newswire", "https://www.prnewswire.com", 4, "business", ("pr",)),
 "PR Newswire Business Tech": ("PR Newswire", "https://www.prnewswire.com", 4, "tech", ("pr",)),
 "Business Wire": ("Business Wire", "https://www.businesswire.com", 4, "business", ("pr",)),
 "Marijuana Moment": ("Marijuana Moment", "https://www.marijuanamoment.net", 2, "politics", ("cannabis",)),
 "MJBizDaily": ("MJBizDaily", "https://mjbizdaily.com", 2, "business", ("cannabis",)),
 "Hacker News": ("Hacker News", "https://news.ycombinator.com", 4, "tech", ("aggregator", "empty_summaries")),
 "Hacker News 200+": ("Hacker News", "https://news.ycombinator.com", 4, "tech", ("aggregator",)),
 "Product Hunt — The best new products, every day": ("Product Hunt", "https://www.producthunt.com", 5, "tech", ("promo",)),
 "The Verge": ("The Verge", "https://www.theverge.com", 2, "tech", ()),
 "WIRED": ("WIRED", "https://www.wired.com", 2, "tech", ()),
 "TechCrunch": ("TechCrunch", "https://techcrunch.com", 2, "tech", ()),
 "cybersecurity | TechCrunch": ("TechCrunch", "https://techcrunch.com/category/security", 2, "tech", ()),
 "Ars Technica": ("Ars Technica", "https://arstechnica.com", 2, "tech", ()),
 "Engadget - Technology News & Expert Reviews": ("Engadget", "https://www.engadget.com", 2, "tech", ()),
 "www.theregister.com - Articles": ("The Register", "https://www.theregister.com", 2, "tech", ()),
 "CNET": ("CNET", "https://www.cnet.com", 4, "tech", ()),
 "Gizmodo": ("Gizmodo", "https://gizmodo.com", 4, "tech", ()),
 "ReadWrite": ("ReadWrite", "https://readwrite.com", 4, "tech", ()),
 "Latest news": ("ZDNET", "https://www.zdnet.com", 4, "tech", ()),
 "9to5Mac": ("9to5Mac", "https://9to5mac.com", 4, "tech", ("apple",)),
 "MacRumors": ("MacRumors", "https://www.macrumors.com", 4, "tech", ("apple",)),
 "AppleInsider": ("AppleInsider", "https://appleinsider.com", 4, "tech", ("apple",)),
 "The Keyword": ("Google (The Keyword)", "https://blog.google", 3, "tech", ("corporate_blog",)),
 "OpenAI News": ("OpenAI", "https://openai.com/news", 3, "tech", ("corporate_blog",)),
 "Hugging Face Blog": ("Hugging Face", "https://huggingface.co/blog", 3, "tech", ("corporate_blog", "empty_summaries")),
 "Simon Willison (LLMs)": ("Simon Willison", "https://simonwillison.net", 3, "tech", ("blog",)),
 "Feld Thoughts": ("Feld Thoughts", "https://feld.com", 5, "tech", ("blog",)),
 "Small Business Trends": ("Small Business Trends", "https://smallbiztrends.com", 5, "business", ("listicle",)),
 "GaryVee": ("GaryVee", "https://www.youtube.com/@garyvee", 5, "business", ("video", "promo")),
 "Marie Forleo": ("Marie Forleo", "https://www.marieforleo.com", 5, "business", ("video", "promo")),
 "Masters of Scale": ("Masters of Scale", "https://mastersofscale.com", 5, "business", ("podcast",)),
 "How I Built This with Guy Raz": ("How I Built This", "https://wondery.com/shows/how-i-built-this", 5, "business", ("podcast",)),
 "The Duct Tape Marketing Podcast": ("Duct Tape Marketing", "https://ducttapemarketing.com", 5, "business", ("podcast",)),
 "The Startup Junkies Podcast": ("Startup Junkies", "https://startupjunkie.org", 5, "business", ("podcast",)),
 "EconTalk": ("EconTalk", "https://www.econtalk.org", 5, "business", ("podcast",)),
 "Linus Tech Tips": ("Linus Tech Tips", "https://www.youtube.com/@LinusTechTips", 5, "tech", ("video",)),
 "Unbox Therapy": ("Unbox Therapy", "https://www.youtube.com/@unboxtherapy", 5, "tech", ("video",)),
 "Marques Brownlee": ("Marques Brownlee", "https://www.youtube.com/@mkbhd", 5, "tech", ("video",)),
 "This Week in Tech (Audio)": ("This Week in Tech", "https://twit.tv", 5, "tech", ("podcast",)),
 "Accidental Tech Podcast": ("Accidental Tech Podcast", "https://atp.fm", 5, "tech", ("podcast",)),
 "Clockwise": ("Clockwise", "https://www.relay.fm/clockwise", 5, "tech", ("podcast",)),
 "ISF Podcast": ("ISF Podcast", "https://www.securityforum.org", 5, "tech", ("podcast",)),
 "Risky Business": ("Risky Business", "https://risky.biz", 5, "tech", ("podcast",)),
 "Darknet Diaries": ("Darknet Diaries", "https://darknetdiaries.com", 5, "tech", ("podcast",)),
 "cybersecurity": ("r/cybersecurity", "https://www.reddit.com/r/cybersecurity", 5, "tech", ("reddit",)),
 "Technical Information Security Content & Discussion": ("r/netsec", "https://www.reddit.com/r/netsec", 5, "tech", ("reddit",)),
 "Blackhat Library: Hacking techniques and research": ("r/blackhat", "https://www.reddit.com/r/blackhat", 5, "tech", ("reddit",)),
 "Poynter": ("Poynter", "https://www.poynter.org", 2, "business", ("media",)),
 "Nieman Lab": ("Nieman Lab", "https://www.niemanlab.org", 2, "business", ("media",)),
 "Columbia Journalism Review": ("Columbia Journalism Review", "https://www.cjr.org", 2, "business", ("media",)),
 "Phys.org - latest science and technology news stories": ("Phys.org", "https://phys.org", 2, "science", ()),
 "Nature": ("Nature", "https://www.nature.com", 2, "science", ()),
 "Latest Science News -- ScienceDaily": ("ScienceDaily", "https://www.sciencedaily.com", 2, "science", ()),
 "Popular Science": ("Popular Science", "https://www.popsci.com", 2, "science", ()),
 "Science Latest": ("Science (AAAS)", "https://www.science.org", 2, "science", ()),
 "New Scientist - Space": ("New Scientist", "https://www.newscientist.com", 2, "science", ()),
 "NASA": ("NASA", "https://www.nasa.gov", 3, "science", ("gov",)),
 "Discovery": ("Discovery", "https://www.discovery.com", 4, "science", ()),
 "Reddit Science": ("r/science", "https://www.reddit.com/r/science", 4, "science", ("reddit",)),
 "FlowingData": ("FlowingData", "https://flowingdata.com", 4, "science", ("blog",)),
 "Hidden Brain": ("Hidden Brain", "https://hiddenbrain.org", 5, "science", ("podcast",)),
 "Sawbones: A Marital Tour of Misguided Medicine": ("Sawbones", "https://maximumfun.org/podcasts/sawbones", 5, "science", ("podcast",)),
 "The Infinite Monkey Cage": ("The Infinite Monkey Cage", "https://www.bbc.co.uk/programmes/b00snr0w", 5, "science", ("podcast",)),
 "Gastropod": ("Gastropod", "https://gastropod.com", 5, "science", ("podcast",)),
 "Probably Science": ("Probably Science", "https://probablyscience.com", 5, "science", ("podcast",)),
 "Shirtloads of Science": ("Shirtloads of Science", "https://shirtloadsofscience.libsyn.com", 5, "science", ("podcast",)),
 "Golf.com": ("GOLF.com", "https://golf.com", 2, "sports", ("golf",)),
}
# Google News query feeds: query source -> (default section, topic, flags). The publisher comes from the title suffix.
GN_QUERIES = {
 'Google News: "Supreme Court" ruling': ("politics", "scotus", ()),
 'Google News: PGA Tour OR LIV Golf': ("sports", "golf", ()),
 'Google News: small business owners': ("business", "smallbiz", ("noisy",)),
 'Google News: BRICS': ("world", "brics", ("state_media_heavy",)),
 'Google News: Strait of Hormuz OR tanker OR "oil pipeline" route': ("world", "energy", ()),
 'Google News: OPEC crude oil': ("markets", "energy", ()),
 'Google News: Las Vegas real estate': ("business", "realestate", ("noisy", "listings")),
 'Google News: "State Department" Rubio OR sanctions': ("world", "foreign-policy", ()),
 'Google News: political violence': ("us", "political-violence", ("noisy",)),
 'Google News: FOMC OR "Federal Reserve" rates': ("markets", "fed", ()),
 'Google News: propaganda OR disinformation media': ("world", "media", ("noisy",)),
 'Google News: local LLM OR llama.cpp OR Ollama OR MLX': ("tech", "ai", ()),
 'Google News: House vote OR Senate vote bill passes': ("politics", "congress", ()),
 'Google News: Nevada Supreme Court OR "Nevada law"': ("us", "nevada", ("local_candidate",)),
 'Google News: unusual options activity': ("markets", "options", ("junk",)),
 'Google News: Mac Studio OR "M5" Apple silicon AI': ("tech", "apple", ()),
 'Google News: Nevada ballot question': ("politics", "nevada-elections", ("local_candidate",)),
 'Google News: Nevada legislature': ("politics", "nevada-politics", ("local_candidate",)),
 'Google News: federal workforce OR federal employees OPM': ("politics", "federal-workforce", ()),
 'Google News: government transparency FOIA': ("politics", "transparency", ()),
 'Google News: Las Vegas cannabis OR dispensary Nevada': ("business", "cannabis", ("noisy", "local_candidate")),
 'Google News: fedgazette OR "Minneapolis Fed"': ("markets", "fed", ()),
 'Google News: "trustee sale" OR foreclosure auction Las Vegas': ("business", "realestate", ("local_candidate",)),
}
# Publishers seen in Google News title suffixes: suffix -> (display name, home URL, tier)
GN_PUBLISHERS = {
 "Reuters": ("Reuters", "https://www.reuters.com", 1), "AP News": ("AP News", "https://apnews.com", 1), "Associated Press": ("AP News", "https://apnews.com", 1),
 "The New York Times": ("The New York Times", "https://www.nytimes.com", 1), "The Washington Post": ("The Washington Post", "https://www.washingtonpost.com", 1),
 "BBC": ("BBC News", "https://www.bbc.com", 1), "NBC News": ("NBC News", "https://www.nbcnews.com", 1), "CBS News": ("CBS News", "https://www.cbsnews.com", 1),
 "ABC News": ("ABC News", "https://abcnews.go.com", 1), "Breaking News, Latest News and Videos": ("ABC News", "https://abcnews.go.com", 1),
 "CNN": ("CNN", "https://www.cnn.com", 1), "Fox News": ("Fox News", "https://www.foxnews.com", 2), "NPR": ("NPR", "https://www.npr.org", 1), "PBS": ("PBS News", "https://www.pbs.org/newshour", 1),
 "The Guardian": ("The Guardian", "https://www.theguardian.com", 1), "Al Jazeera": ("Al Jazeera", "https://www.aljazeera.com", 1),
 "WSJ": ("The Wall Street Journal", "https://www.wsj.com", 1), "The Wall Street Journal": ("The Wall Street Journal", "https://www.wsj.com", 1),
 "Bloomberg.com": ("Bloomberg", "https://www.bloomberg.com", 1), "Bloomberg": ("Bloomberg", "https://www.bloomberg.com", 1), "Bloomberg Law News": ("Bloomberg Law", "https://news.bloomberglaw.com", 2),
 "CNBC": ("CNBC", "https://www.cnbc.com", 1), "Financial Times": ("Financial Times", "https://www.ft.com", 1), "Axios": ("Axios", "https://www.axios.com", 2),
 "Politico": ("Politico", "https://www.politico.com", 2), "POLITICO": ("Politico", "https://www.politico.com", 2), "The Hill": ("The Hill", "https://thehill.com", 2), "USA Today": ("USA Today", "https://www.usatoday.com", 2),
 "Los Angeles Times": ("Los Angeles Times", "https://www.latimes.com", 1), "The Boston Globe": ("The Boston Globe", "https://www.bostonglobe.com", 2), "The Seattle Times": ("The Seattle Times", "https://www.seattletimes.com", 2),
 "Houston Chronicle": ("Houston Chronicle", "https://www.houstonchronicle.com", 2), "Newsweek": ("Newsweek", "https://www.newsweek.com", 4), "New York Post": ("New York Post", "https://nypost.com", 4),
 "Page Six": ("Page Six", "https://pagesix.com", 5), "Breitbart News": ("Breitbart", "https://www.breitbart.com", 4), "Daily Kos": ("Daily Kos", "https://www.dailykos.com", 4),
 "SCOTUSblog": ("SCOTUSblog", "https://www.scotusblog.com", 2), "Democracy Docket": ("Democracy Docket", "https://www.democracydocket.com", 4), "The National Law Review": ("National Law Review", "https://natlawreview.com", 3),
 "News From The States": ("States Newsroom", "https://statesnewsroom.com", 2), "The Center Square": ("The Center Square", "https://www.thecentersquare.com", 4), "Patch": ("Patch", "https://patch.com", 4), "Hoodline": ("Hoodline", "https://hoodline.com", 5),
 "Federal News Network": ("Federal News Network", "https://federalnewsnetwork.com", 2), "FEDweek": ("FEDweek", "https://www.fedweek.com", 3), "FedSmith.com": ("FedSmith", "https://www.fedsmith.com", 4), "GovExec.com": ("Government Executive", "https://www.govexec.com", 2),
 "Yahoo Sports": ("Yahoo Sports", "https://sports.yahoo.com", 4), "Yahoo Finance": ("Yahoo Finance", "https://finance.yahoo.com", 4), "Yahoo": ("Yahoo News", "https://news.yahoo.com", 4), "AOL.com": ("AOL", "https://www.aol.com", 4),
 "ESPN": ("ESPN", "https://www.espn.com", 1), "CBS Sports": ("CBS Sports", "https://www.cbssports.com", 2), "NBC Sports": ("NBC Sports", "https://www.nbcsports.com", 2), "Sky Sports": ("Sky Sports", "https://www.skysports.com", 2),
 "Golfweek": ("Golfweek", "https://golfweek.usatoday.com", 2), "GOLF.com": ("GOLF.com", "https://golf.com", 2), "Golf Channel": ("Golf Channel", "https://www.nbcsports.com/golf", 2), "PGA Tour": ("PGA Tour", "https://www.pgatour.com", 3),
 "Golfmagic": ("GolfMagic", "https://www.golfmagic.com", 4), "Today's Golfer": ("Today's Golfer", "https://www.todays-golfer.com", 4), "Women's Golf Journal": ("Women's Golf Journal", "https://womensgolfjournal.com", 4), "theScore": ("theScore", "https://www.thescore.com", 4), "MMA Fighting": ("MMA Fighting", "https://www.mmafighting.com", 4),
 "MarketBeat": ("MarketBeat", "https://www.marketbeat.com", 5), "Benzinga": ("Benzinga", "https://www.benzinga.com", 4), "TipRanks": ("TipRanks", "https://www.tipranks.com", 5), "Seeking Alpha": ("Seeking Alpha", "https://seekingalpha.com", 4),
 "TradingView": ("TradingView", "https://www.tradingview.com", 5), "Traders Union": ("Traders Union", "https://tradersunion.com", 5), "BigGo Finance": ("BigGo", "https://biggo.com", 5), "Moomoo": ("Moomoo", "https://www.moomoo.com", 5), "富途牛牛": ("Futu", "https://www.futunn.com", 5),
 "FXStreet": ("FXStreet", "https://www.fxstreet.com", 5), "Mitrade": ("Mitrade", "https://www.mitrade.com", 5), "Simply Wall Street": ("Simply Wall St", "https://simplywall.st", 5), "StreetInsider": ("StreetInsider", "https://www.streetinsider.com", 5),
 "FinancialContent": ("FinancialContent", None, 5), "Newswire.com": ("Newswire.com", "https://www.newswire.com", 5), "PR Newswire": ("PR Newswire", "https://www.prnewswire.com", 4), "marketscreener.com": ("MarketScreener", "https://www.marketscreener.com", 4), "The Business Journals": ("The Business Journals", "https://www.bizjournals.com", 2),
 "Realtor.com": ("Realtor.com", "https://www.realtor.com", 5), "Mansion Global": ("Mansion Global", "https://www.mansionglobal.com", 4), "Nevada Business Magazine": ("Nevada Business Magazine", "https://www.nevadabusiness.com", 2),
 "Las Vegas Sun": ("Las Vegas Sun", "https://lasvegassun.com", 2), "Las Vegas Review-Journal": ("Las Vegas Review-Journal", "https://www.reviewjournal.com", 2), "The Nevada Independent": ("The Nevada Independent", "https://thenevadaindependent.com", 2),
 "KSNV": ("KSNV News 3", "https://news3lv.com", 2), "News3LV": ("KSNV News 3", "https://news3lv.com", 2), "FOX5 Vegas": ("FOX5 Las Vegas", "https://www.fox5vegas.com", 2), "KTNV": ("KTNV 13 Action News", "https://www.ktnv.com", 2), "KTNV 13 Action News Las Vegas": ("KTNV 13 Action News", "https://www.ktnv.com", 2),
 "8NewsNow": ("8 News Now", "https://www.8newsnow.com", 2), "KLAS": ("8 News Now", "https://www.8newsnow.com", 2),
 "KTVN": ("KTVN 2 News", "https://www.ktvn.com", 2), "KRXI2": ("KRNV/KRXI Reno", "https://mynews4.com", 2), "Reno Gazette Journal": ("Reno Gazette Journal", "https://www.rgj.com", 2), "Nevada Appeal": ("Nevada Appeal", "https://www.nevadaappeal.com", 2),
 "The Record Courier": ("The Record-Courier", "https://www.recordcourier.com", 2), "Elko Daily Free Press": ("Elko Daily Free Press", "https://elkodaily.com", 2), "Nevada Current": ("Nevada Current", "https://nevadacurrent.com", 2), "This Is Reno": ("This Is Reno", "https://thisisreno.com", 2),
 "Boulder City Review": ("Boulder City Review", "https://bouldercityreview.com", 2), "Havasu News": ("Today's News-Herald", "https://www.havasunews.com", 2), "Today's News-Herald": ("Today's News-Herald", "https://www.havasunews.com", 2),
 "Mohave Valley Daily News": ("Mohave Valley Daily News", "https://www.mohavedailynews.com", 2), "Mohave Daily News": ("Mohave Valley Daily News", "https://www.mohavedailynews.com", 2),
 "Kingman Miner": ("Kingman Daily Miner", "https://kdminer.com", 2), "Kingman Daily Miner": ("Kingman Daily Miner", "https://kdminer.com", 2), "Mesquite Local News": ("Mesquite Local News", "https://mesquitelocalnews.com", 2),
 "Laughlin Nevada Times": ("Laughlin Nevada Times", "https://www.laughlinnevadatimes.com", 2), "Parker Pioneer": ("Parker Pioneer", "https://www.parkerpioneer.net", 2), "St George News": ("St. George News", "https://www.stgeorgeutah.com", 2),
 "12News": ("12News (KPNX Phoenix)", "https://www.12news.com", 2), "KNAU": ("KNAU Arizona Public Radio", "https://www.knau.org", 2), "KJZZ": ("KJZZ", "https://kjzz.org", 2), "AZ Mirror": ("Arizona Mirror", "https://azmirror.com", 2), "Arizona Mirror": ("Arizona Mirror", "https://azmirror.com", 2),
 "Cronkite News": ("Cronkite News", "https://cronkitenews.azpbs.org", 2), "The Arizona Republic": ("The Arizona Republic", "https://www.azcentral.com", 2), "Arizona Daily Sun": ("Arizona Daily Sun", "https://azdailysun.com", 2),
 "Northern Nevada Business Weekly": ("Northern Nevada Business Weekly", "https://www.nnbw.com", 2), "The Salt Lake Tribune": ("The Salt Lake Tribune", "https://www.sltrib.com", 2),
 "Pokerfuse": ("Pokerfuse", "https://pokerfuse.com", 5), "Casino.com": ("Casino.com", None, 5), "NewsBreak: Local News & Alerts": ("NewsBreak", None, 5), "inkl": ("inkl", None, 5), "Facebook": ("Facebook", None, 5), "LinkedIn": ("LinkedIn", None, 5),
 "TV BRICS": ("TV BRICS", "https://tvbrics.com", 5), "DD News": ("DD News", "https://ddnews.gov.in", 4), "News On AIR": ("All India Radio", "https://www.newsonair.gov.in", 4), "The Economic Times": ("The Economic Times", "https://economictimes.indiatimes.com", 4), "The Times of India": ("Times of India", "https://timesofindia.indiatimes.com", 4), "Hindustan Times": ("Hindustan Times", "https://www.hindustantimes.com", 4), "Firstpost": ("Firstpost", "https://www.firstpost.com", 4),
 "Modern Ghana": ("Modern Ghana", "https://www.modernghana.com", 5), "MyJoyOnline": ("MyJoyOnline", "https://www.myjoyonline.com", 4), "IOL": ("IOL (South Africa)", "https://www.iol.co.za", 4), "Devdiscourse": ("Devdiscourse", "https://www.devdiscourse.com", 5), "Big News Network.com": ("Big News Network", None, 5), "Social News XYZ": ("Social News XYZ", None, 5),
 "UA.NEWS": ("UA.News", None, 5), "news.lavx.hu": ("lavx.hu", None, 5), "Unisba Media": ("Unisba Media", None, 5), "Vietnam.vn": ("Vietnam.vn", None, 5), "Operativ Məlumat Mərkəzi": ("Operativ (Azerbaijan)", None, 5), "Latest news from Azerbaijan": ("Azernews", None, 5), "Apa.az": ("APA (Azerbaijan)", None, 5), "Modern.az": ("Modern.az", None, 5),
 "EnergyNow.com": ("EnergyNow", "https://energynow.com", 4), "EnergyNow": ("EnergyNow", "https://energynow.com", 4), "OilPrice.com": ("OilPrice.com", "https://oilprice.com", 2), "Rigzone": ("Rigzone", "https://www.rigzone.com", 2),
 "The Verge": ("The Verge", "https://www.theverge.com", 2), "MacRumors": ("MacRumors", "https://www.macrumors.com", 4), "9to5Mac": ("9to5Mac", "https://9to5mac.com", 4), "9to5Google": ("9to5Google", "https://9to5google.com", 4), "AppleInsider": ("AppleInsider", "https://appleinsider.com", 4), "Engadget": ("Engadget", "https://www.engadget.com", 2), "TechCrunch": ("TechCrunch", "https://techcrunch.com", 2), "Wccftech": ("Wccftech", "https://wccftech.com", 5), "shattered.io": ("shattered.io", None, 5), "roundtable.io": ("roundtable.io", None, 5), "OpenTools": ("OpenTools", None, 5), "TechGig": ("TechGig", None, 5),
 "Small Business Trends": ("Small Business Trends", "https://smallbiztrends.com", 5), "NFIB": ("NFIB", "https://www.nfib.com", 3), "Forbes": ("Forbes", "https://www.forbes.com", 4),
 "The Hollywood Reporter": ("The Hollywood Reporter", "https://www.hollywoodreporter.com", 2), "Variety": ("Variety", "https://variety.com", 2), "Deadline": ("Deadline", "https://deadline.com", 2),
 "U.S. Department of State (.gov)": ("U.S. Department of State", "https://www.state.gov", 3), "Colorado Attorney General (.gov)": ("Colorado Attorney General", None, 3),
 "The Jerusalem Post": ("The Jerusalem Post", "https://www.jpost.com", 2), "Gulf News": ("Gulf News", "https://gulfnews.com", 4), "The Manila Times": ("The Manila Times", "https://www.manilatimes.net", 4), "The Globe and Mail": ("The Globe and Mail", "https://www.theglobeandmail.com", 1), "South China Morning Post": ("South China Morning Post", "https://www.scmp.com", 2), "CGTN": ("CGTN", "https://www.cgtn.com", 5), "Anadolu Ajansı": ("Anadolu Agency", "https://www.aa.com.tr", 4), "The Sunday Guardian": ("The Sunday Guardian", None, 5),
 "WISH-TV": ("WISH-TV", "https://www.wishtv.com", 2), "KOMO": ("KOMO News", "https://komonews.com", 2), "VTDigger": ("VTDigger", "https://vtdigger.org", 2), "PennLive": ("PennLive", "https://www.pennlive.com", 2),
}
_GN_PUBLISHER_DROP = _rx(r"^(MarketBeat|TipRanks|TradingView|Traders Union|BigGo|Moomoo|富途牛牛|FXStreet|Mitrade|Simply Wall St|StreetInsider|FinancialContent|Newswire\.com|Realtor\.com|TV BRICS|Facebook|LinkedIn|inkl|NewsBreak|Pokerfuse|Casino\.com|Social News XYZ|Big News Network|Devdiscourse|Unisba Media|Vietnam\.vn|news\.lavx\.hu|shattered\.io|roundtable\.io|OpenTools|Page Six|Digital Journal|The Batesville Daily Guard|Bluefield Daily Telegraph|Hoodline|CoinMarketCap|Wccftech|Wonkette|Substack|.*\.gov\.in|.*Daily Guard)")
_NON_LATIN = re.compile(r"[Ѐ-ӿ؀-ۿऀ-ॿ฀-๿぀-ヿ一-鿿가-힯]")
# Publishers behind a hard or metered paywall (affects the "Read original" affordance only).
PAYWALLED = {"The New York Times", "The Wall Street Journal", "Financial Times", "The Washington Post", "Bloomberg", "Bloomberg Law",
             "The Boston Globe", "The Economist", "Barron's", "The Athletic", "Los Angeles Times", "The Seattle Times", "Houston Chronicle",
             "The Globe and Mail", "Las Vegas Review-Journal", "Today's News-Herald", "Mohave Valley Daily News", "Kingman Daily Miner",
             "Parker Pioneer", "Business Insider", "Foreign Affairs", "Foreign Policy", "The Arizona Republic", "Arizona Daily Sun", "Nature"}
# Regional newsrooms whose coverage area is ours; unlocks the context-only region aliases ("the Strip", bare "Henderson").
REGIONAL_PUBLISHERS = {"Las Vegas Review-Journal", "Las Vegas Sun", "KTNV 13 Action News", "The Nevada Independent", "KSNV News 3", "FOX5 Las Vegas",
                       "8 News Now", "Nevada Current", "Boulder City Review", "Today's News-Herald", "Mohave Valley Daily News", "Kingman Daily Miner",
                       "Mesquite Local News", "Laughlin Nevada Times", "Nevada Business Magazine", "Parker Pioneer", "KNAU Arizona Public Radio",
                       "Arizona Mirror", "Cronkite News", "12News (KPNX Phoenix)", "St. George News"}

def _domain(url):
    try:
        host = urlparse(url or "").netloc.lower()
    except Exception:
        return None
    host = host[4:] if host.startswith("www.") else host
    return host or None

def publisher(item):
    """{"name", "home", "tier", "domain", "paywalled", "flags", "default", "via", "raw"} for an item. Google News items take
    the publisher from the title suffix (item["title_pub"] when feed stashed it, else re-derived from the raw title).
    Direct regional sources (item["via"] == "direct") already carry source/tier/homepage and keep them. Unknown -> tier 4."""
    src = str(item.get("source") or "").strip()
    link = item.get("link") or ""
    if item.get("via") == "direct" or (isinstance(item.get("publisher"), dict) and item["publisher"].get("name") and item["publisher"].get("tier")):
        p = item.get("publisher") if isinstance(item.get("publisher"), dict) else {}
        name = p.get("name") or src or "Local source"
        home = p.get("home") or item.get("homepage") or None
        tier = int(p.get("tier") or item.get("tier") or 2)
        return {"name": name, "home": home, "domain": _domain(home) or _domain(link), "tier": max(1, min(tier, 5)),
                "paywalled": bool(p.get("paywalled") if p.get("paywalled") is not None else item.get("paywalled")) or name in PAYWALLED,
                "flags": tuple(p.get("flags") or ()) + ("regional", "direct"), "default": "local", "via": "direct", "raw": src}
    if src in GN_QUERIES or is_google_news(src):
        tp = item.get("title_pub")
        if tp is None: tp = normalize_title_full(item.get("title") or "", src)[1]
        if tp:
            g = GN_PUBLISHERS.get(tp)
            if g:
                return {"name": g[0], "home": g[1], "domain": _domain(g[1]), "tier": g[2], "paywalled": g[0] in PAYWALLED,
                        "flags": ("regional",) if g[0] in REGIONAL_PUBLISHERS else (), "default": None, "via": "google_news", "raw": tp}
            tier = 5 if (_GN_PUBLISHER_DROP.match(tp) or _NON_LATIN.search(tp)) else 4
            return {"name": tp, "home": None, "domain": None, "tier": tier, "paywalled": tp in PAYWALLED, "flags": (), "default": None, "via": "google_news", "raw": tp}
        return {"name": "Google News", "home": "https://news.google.com", "domain": "news.google.com", "tier": 4, "paywalled": False, "flags": (), "default": None, "via": "google_news", "raw": src}
    rec = PUBLISHERS.get(src)
    if rec:
        return {"name": rec[0], "home": rec[1], "domain": _domain(rec[1]) or _domain(link), "tier": rec[2], "paywalled": rec[0] in PAYWALLED,
                "flags": tuple(rec[4]), "default": rec[3], "via": "feed", "raw": src}
    if src.startswith("PR Newswire"):
        return {"name": "PR Newswire", "home": "https://www.prnewswire.com", "domain": "prnewswire.com", "tier": 4, "paywalled": False, "flags": ("pr",), "default": "business", "via": "feed", "raw": src}
    dom = _domain(link)
    return {"name": src or "Wire report", "home": None, "domain": None if dom == "news.google.com" else dom, "tier": 4, "paywalled": src in PAYWALLED,
            "flags": ("regional",) if src in REGIONAL_PUBLISHERS else (), "default": None, "via": "feed", "raw": src}

def is_regional_source(item_or_pub):
    pub = item_or_pub if "tier" in item_or_pub and "flags" in item_or_pub else publisher(item_or_pub)
    return "regional" in (pub.get("flags") or ()) or pub.get("name") in REGIONAL_PUBLISHERS

# ====================================================================== 3. LANGUAGE
_SCRIPTS = [("ru", re.compile(r"[Ѐ-ӿ]")), ("ar", re.compile(r"[؀-ۿ]")), ("hi", re.compile(r"[ऀ-ॿ]")),
            ("th", re.compile(r"[฀-๿]")), ("ja", re.compile(r"[぀-ヿ]")), ("zh", re.compile(r"[一-鿿]")), ("ko", re.compile(r"[가-힯]"))]
_STOP = {
 "en": {"the", "and", "of", "to", "in", "for", "on", "with", "is", "at", "by", "from", "as", "that", "this", "are", "was", "after", "over", "says", "its", "his", "her", "has", "have", "will", "new", "about", "into", "than", "more"},
 "es": {"el", "la", "los", "las", "del", "para", "con", "una", "por", "es", "en", "que", "se", "su", "al", "más", "como", "pero", "sus", "ha", "sobre", "este", "esta", "también", "ser", "año", "años", "tras", "entre", "desde", "lanza", "anuncia"},
 "fr": {"le", "les", "des", "pour", "avec", "dans", "sur", "une", "est", "et", "du", "au", "aux", "qui", "pas", "ce", "cette", "ses", "par", "plus", "sont", "annonce", "lance", "après", "été"},
 "de": {"der", "die", "das", "und", "mit", "für", "nicht", "auf", "eine", "ist", "von", "zu", "den", "dem", "sich", "ein", "im", "bei", "nach", "wird", "auch", "über", "einen", "einer", "eröffnet", "integriert", "zusammenfassung"},
 "it": {"il", "gli", "della", "degli", "che", "per", "con", "una", "del", "di", "è", "sono", "nel", "nella", "anche", "come", "dal", "alla", "dei", "delle", "lancia", "annuncia", "riassunto"},
 "pt": {"não", "uma", "os", "para", "com", "em", "do", "da", "dos", "das", "que", "é", "no", "na", "mais", "ao", "pelo", "pela", "anuncia", "lança", "resumo"},
}

def lang(item):
    """ISO 639-1 code for the item's language from title+summary: "en", "es", "fr", "de", "it", "pt", a script code
    ("zh", "ja", "ko", "ru", "ar", "hi", "th") or "other"."""
    text = f"{item.get('title') or ''} {str(item.get('summary') or '')[:300]}"
    letters = [c for c in text if c.isalpha()]
    if letters:
        for code, rx in _SCRIPTS:
            n = len(rx.findall(text))
            if n and n / len(letters) > 0.2: return code
    toks = re.findall(r"[a-záéíóúñüçàèìòùâêîôûäöß']+", text.lower())
    if not toks: return "en"
    scores = {k: sum(1 for t in toks if t in v) for k, v in _STOP.items()}
    best = max((k for k in scores if k != "en"), key=lambda k: scores[k])
    if scores[best] >= 3 and scores[best] > scores["en"]: return best
    return "en"

# ====================================================================== 4. QUALITY GATE
LISTICLE = _rx(r"^\s*(?:the\s+)?(?:top\s+)?\d{1,2}\s+(?:best|essential|must|ways|things|tips|reasons|stocks|mistakes|lessons|rules|steps|signs|habits|questions|ideas|books|apps|tools|strategies|secrets|side hustles|jobs|crypto|coins|tokens|etfs|dividend)\b|\btop\s+\d{1,2}\s+\w+\s+(?:coins|tokens|stocks|etfs)\b")
DEALS = _rx(r"\*(?:HOT|Ends Tonight|Today Only)\*|\{(?:Ends Tonight|Today Only)[^}]*\}|\b(?:PRICE DROP|Price Drop)\b|\bonly \$\d|\bjust \$\d|\bshipped\b|\(reg\.? \$|\bdeals? (?:on|of the day)\b|\bpromo codes?\b|\breferral code\b|\bsign[- ]up bonus\b|\bcoupons?\b|\b\d{1,2}% off\b|\bbest (?:deals|buys)\b|\bbuy now\b")
PROMO_PR = _rx(r"\b(?:securities (?:fraud )?lawsuit|class action|deadline alert|investors? (?:have|with) (?:opportunity|losses)|lead(?:ing)? plaintiff|shareholder alert|named to .* list|recognized as|wins? .* award|celebrates .* anniversary|to present at|to participate in .* conference|announces (?:participation|pricing|closing)|inner circle|power 150|market to reach usd|market size)\b")
OPTIONS_SPAM = _rx(r"\b(?:unusual(?:ly)?\s+(?:large\s+)?(?:options?|call|put)\b|options? (?:volume|activity)|call options|put options|V/OI)")
LISTING = _rx(r"^\d{2,6}\s+[NSEW]?\.?\s?[A-Z][\w' .]+(?:Ave|Avenue|St|Street|Dr|Drive|Rd|Road|Way|Ln|Lane|Ct|Court|Blvd|Cir|Pl|Pkwy)\b.*\b(?:NV|AZ|UT|CA)\s+\d{5}")
REDDIT = _rx(r"submitted by /u/|\[link\] \[comments\]|^(?:Daily|Weekday|Weekly|Mentorship) .* (?:Discussion|Thread|Monday)|^Welcome to the Daily")
ANALYST_NOTE = _rx(r"\b(?:declares? (?:quarterly |monthly )?dividend|ex-dividend|price target|upgrades?|downgrades?|initiates? coverage|reiterates?|maintains? (?:buy|hold|sell)|GAAP EPS|beats? by \$|misses? by \$|Q[1-4] (?:20\d\d )?(?:earnings|results)|to report (?:Q[1-4]|results)|conference call|webcast)\b")
WHY_STOCK = _rx(r"^why (?:is|are|did) .* (?:stock|shares) (?:surging|sliding|climbing|falling|up|down|jump|drop|soar|plunge)")
SEC_FORM = re.compile(r"^\s*(?:8-K|10-Q|10-K|S-1|S-3|424B\d?|Form 4|SC 13[DG]|13F-HR|6-K|D/A|D|3|4|4/A|144|X-17A-5)\s+[-–]\s")
NO_SUMMARY = re.compile(r"^(?:|Comments|TBD|Article URL:.*|Comments.*|Read more.*|Continue reading.*)$", re.S)
WIRE_DATELINE = _rx(r"^(?:LAS VEGAS|HENDERSON|NORTH LAS VEGAS|BULLHEAD CITY|LAUGHLIN|LAKE HAVASU CITY|KINGMAN|FORT MOHAVE|MOHAVE VALLEY|MESQUITE|BOULDER CITY|NEEDLES)\b[^,]*,\s*(?:Nev|NV|Ariz|AZ|Calif|CA)")
_DATELINE_KEY = {"las vegas": "las-vegas", "henderson": "henderson", "north las vegas": "north-las-vegas", "bullhead city": "bullhead-city", "laughlin": "laughlin",
                 "lake havasu city": "lake-havasu-city", "kingman": "kingman", "fort mohave": "mohave-valley", "mohave valley": "mohave-valley", "mesquite": "mesquite",
                 "boulder city": "boulder-city", "needles": "needles"}

def wire_dateline(text):
    """Region key for a wire dateline at the start of the text ("LAS VEGAS, Oct. 14, 2026 /PRNewswire/"), else None."""
    m = WIRE_DATELINE.match(str(text or "").strip())
    if not m: return None
    city = re.match(r"^[A-Za-z .]+?(?=\b[^A-Za-z .]|,|$)", m.group(0)).group(0).strip().lower()
    for k, v in _DATELINE_KEY.items():
        if city.startswith(k): return v
    return None

def _gate(item, title, summ, pub):
    """(verdict, reason); verdict in keep / demote / drop. Order matters (first match wins)."""
    text = f"{title} {summ[:200]}"
    flags = set(pub.get("flags") or ())
    if item.get("category") == "filings" or "filings" in flags: return "drop", "sec_filing"
    if SEC_FORM.search(title): return "drop", "sec_filing"
    if pub["tier"] >= 5: return "drop", "tier5_source"
    if "reddit" in flags or REDDIT.search(text): return "drop", "reddit"
    if "pr" in flags:
        if PROMO_PR.search(title): return "drop", "pr_promo"
        return "demote", "press_wire"
    if DEALS.search(title): return "drop", "deals_promo"
    if LISTICLE.search(title): return "drop", "listicle"
    if OPTIONS_SPAM.search(title): return "drop", "options_spam"
    if LISTING.search(title): return "drop", "real_estate_listing"
    if PROMO_PR.search(title) and "direct" not in flags: return "drop", "pr_promo"
    if WHY_STOCK.search(title): return "drop", "stock_move_filler"
    direct = "direct" in flags   # regional gov/meeting/event feeds: short or missing summaries are normal, never a drop
    if len(title) < 20 and not summ: return ("demote", "title_too_short") if direct else ("drop", "title_too_short")
    if NO_SUMMARY.match(summ):
        return ("demote", "no_summary") if (pub["tier"] <= 2 or direct) else ("drop", "no_summary_low_tier")
    if ANALYST_NOTE.search(title) and pub["tier"] >= 4: return "demote", "analyst_note"
    if "podcast" in flags or "video" in flags: return "drop", "podcast_video"
    if "evergreen" in flags or "personal_finance" in flags: return "demote", "evergreen_advice"
    if "crypto" in flags and pub["tier"] >= 4: return "demote", "crypto_low_tier"
    if pub["tier"] == 4: return "demote", "tier4_source"
    return "keep", ""

def quality(item, pub=None):
    """(keep: bool, score: float, reasons: [str]). keep=False means drop; score 1.0 = full weight, 0.5 = demoted
    (rendered, never the homepage lead/top). Press wires survive only with a home-region dateline or mention;
    Spanish-language items from regional newsrooms are kept (demoted) with reason lang:es; other non-English is dropped."""
    pub = pub or (item.get("publisher") if isinstance(item.get("publisher"), dict) and "tier" in item["publisher"] else publisher(item))
    title = item.get("title") or ""
    summ = _text(item.get("summary"))
    verdict, reason = _gate(item, title, summ, pub)
    reasons = [reason] if reason else []
    lg = item.get("lang") or lang({"title": title, "summary": summ})
    if verdict != "drop" and lg != "en":
        if lg == "es" and is_regional_source(pub): verdict = "demote"; reasons.append("lang:es")
        else: verdict, reasons = "drop", [f"non_english:{lg}"]
    if verdict != "drop" and "pr" in (pub.get("flags") or ()):
        regions = item.get("regions") or detect_regions(f"{title} {summ[:400]}", item.get("source") or "")
        if HOME_REGIONS & set(regions) or wire_dateline(summ): verdict = "demote"; reasons = ["pr_local"]
        else: verdict, reasons = "drop", ["pr_nonlocal"]
    return verdict != "drop", {"keep": 1.0, "demote": 0.5, "drop": 0.0}[verdict], reasons

# ====================================================================== 5. CATEGORIZATION
US_STATES = r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington(?: state)?|West Virginia|Wisconsin|Wyoming"
US_CITIES = r"Los Angeles|L\.A\.|New York City|NYC|Chicago|Houston|Phoenix|Philadelphia|San Antonio|San Diego|Dallas|San Jose|Austin|Jacksonville|Fort Worth|Columbus|Charlotte|San Francisco|Indianapolis|Seattle|Denver|Washington,? D\.?C\.?|D\.C\.|Boston|Nashville|Detroit|Portland|Las Vegas|Memphis|Louisville|Baltimore|Milwaukee|Albuquerque|Tucson|Fresno|Sacramento|Atlanta|Miami|Minneapolis|New Orleans|Cleveland|Tampa|Orlando|Pittsburgh|Cincinnati|St\. Louis|Salt Lake City|Honolulu|Anchorage|Spokane|Maui"
US_FED = r"Congress|Senate|House of Representatives|the House|White House|Pentagon|Supreme Court|SCOTUS|FBI|ICE|DHS|Homeland Security|DOJ|Justice Department|Department of (?:Justice|Education|Energy|Labor|Transportation|State|War|Defense|Agriculture|Commerce)|EPA|FDA|CDC|NIH|IRS|OPM|GSA|FEMA|NASA|National Guard|Medicare|Medicaid|Social Security|Federal Reserve|the Fed\b|FOMC|Treasury"
FOREIGN = r"Ukraine|Ukrainian|Russia|Russian|Syrian|Iraqi|Lebanese|Yemeni|Saudis?|Emirati|Qatari|Kuwait|Omani?|Bahrain|Jordan(?:ian)?|Palestinian|Enugu|Lagos|Abuja|Nairobi|Accra|Johannesburg|Cape Town|Addis|Khartoum|Mogadishu|Kinshasa|Kigali|Kampala|Harare|Lusaka|Luanda|Dakar|Bamako|Ouagadougou|Niamey|N'Djamena|Tripoli|Tunis|Algiers|Rabat|Casablanca|Mumbai|Delhi|Kolkata|Chennai|Bengaluru|Hyderabad|Karachi|Lahore|Islamabad|Colombo|Kathmandu|Yangon|Bangkok|Hanoi|Ho Chi Minh|Kuala Lumpur|Taipei|Shanghai|Shenzhen|Guangzhou|Osaka|Kyoto|Busan|Melbourne|Brisbane|Perth|Auckland|Wellington|Toronto|Vancouver|Montreal|Alberta|Ontario|Quebec|British Columbia|Guadalajara|Monterrey|Tijuana|Bogot[aá]|Caracas|Lima|Santiago|Buenos Aires|S[aã]o Paulo|Rio de Janeiro|Bras[ií]lia|Quito|La Paz|Montevideo|Asunci[oó]n|Kingston|Port-au-Prince|San Juan|Managua|Tegucigalpa|San Salvador|Guatemala City|Panama City|Reykjavik|Oslo|Stockholm|Copenhagen|Helsinki|Dublin|Edinburgh|Manchester|Birmingham|Lisbon|Barcelona|Milan|Naples|Venice|Munich|Frankfurt|Hamburg|Vienna|Zurich|Geneva|Amsterdam|Prague|Budapest|Bucharest|Sofia|Belgrade|Zagreb|Sarajevo|Kiev|Odesa|Kharkiv|Donetsk|Crimea|Minsk|Tbilisi|Yerevan|Astana|Tashkent|Bishkek|Dushanbe|Ashgabat|Ulaanbaatar|Mongolia|Tibet|Xinjiang|Uyghur|Macau|Okinawa|Putin|Kremlin|Zelensk(?:y|yy|iy)|Kyiv|Moscow|Israel|Israeli|Gaza|Hamas|Hezbollah|West Bank|Netanyahu|Iran|Iranian|Tehran|Houthi|Yemen|Saudi|Riyadh|UAE|Qatar|Hormuz|Red Sea|Bab el-Mandeb|Syria|Lebanon|Beirut|Iraq|Turkey|Türkiye|Erdogan|China|Chinese|Beijing|Xi Jinping|Taiwan|Hong Kong|Japan|Japanese|Tokyo|Korea|Korean|Seoul|Pyongyang|India|Indian|Modi|New Delhi|Pakistan|Bangladesh|Dhaka|Sri Lanka|Nepal|Afghanistan|Kabul|Taliban|Myanmar|Thailand|Vietnam|Philippines|Manila|Indonesia|Jakarta|Malaysia|Singapore|Australia|Australian|Canberra|Sydney|New Zealand|Canada|Canadian|Ottawa|Trudeau|Carney|Mexico|Mexican|Sheinbaum|Brazil|Brazilian|Lula|Bolsonaro|Argentina|Milei|Venezuela|Maduro|Colombia|Chile|Peru|Cuba|Cuban|Havana|Haiti|Panama|Nicaragua|Guatemala|Honduras|El Salvador|Europe|European|EU\b|Brussels|NATO|Britain|British|UK\b|U\.K\.|London|Starmer|England|Scotland|Wales|Ireland|Irish|France|French|Paris|Macron|Germany|German|Berlin|Merz|Italy|Italian|Rome|Meloni|Vatican|Pope|Spain|Spanish|Madrid|Portugal|Netherlands|Dutch|Belgium|Switzerland|Swiss|Austria|Poland|Polish|Warsaw|Tusk|Hungary|Orb[aá]n|Czech|Slovakia|Romania|Bulgaria|Greece|Greek|Athens|Serbia|Kosovo|Bosnia|Croatia|Albania|Albanian|Sweden|Swedish|Norway|Norwegian|Denmark|Danish|Finland|Finnish|Baltic|Estonia|Latvia|Lithuania|Belarus|Moldova|Georgia(?:n)? (?:government|parliament)|Armenia|Azerbaijan|Baku|Kazakhstan|Uzbekistan|Central Asia|Africa|African|Nigeria|Nigerian|Ghana|Kenya|Ethiopia|Sudan|Somalia|Congo|Rwanda|Uganda|Tanzania|Zimbabwe|South Africa|Egypt|Egyptian|Cairo|Libya|Tunisia|Algeria|Morocco|Mali|Niger|Burkina|Senegal|Mauritius|Seychelles|BRICS|United Nations|U\.N\.|UN\b|Security Council|ICJ|ICC|WHO\b|IMF|World Bank|G7|G20|OPEC|Davos|Nobel|Cop3\d|COP3\d"
SPORTS = r"\b(?:PGA(?: Tour)?|LIV Golf|Ryder Cup|Korn Ferry|DP World Tour|LPGA|Masters|golf(?:er|ers)?\b|NFL|NBA|WNBA|MLB|NHL|MLS|NCAA|college football|CFP\b|College Football Playoff|Raiders|Golden Knights|Las Vegas Aces|Valkyries|Patriots|Chiefs|Cowboys|Lakers|Yankees|Dodgers|Brewers|Super Bowl|World Series|Stanley Cup|playoffs?|quarterback|touchdown|home run|slam dunk|Champions League|Premier League|La Liga|Serie A|Bundesliga|Real Madrid|Barcelona|Man(?:chester)? (?:United|City)|Bayern|PSG|Atletico|Juventus|FIFA|World Cup|Olympics?|UFC|MMA|boxing|heavyweight|F1|Formula 1|IndyCar|NASCAR|Grand Prix|Wimbledon|US Open|Ryder|ALCS|NLCS|Guardians|Chelsea|Arsenal|Liverpool|Tottenham|Inter Milan|AC Milan|welterweight|middleweight|lightweight|featherweight|knockout|\bKO\b|title fight|undercard|bout\b|volleyball|basketball|football|baseball|hockey|soccer|softball|lacrosse|wrestling|rodeo|NFR\b|Mountain West|UNLV (?:football|basketball|volleyball|soccer|Rebels)|Rebels|Nevada Preps|high school football|Athlete of the Week|state title|Week \d+ (?:picks|predictions|rankings)|coach(?:es|ing)? (?:fired|hired)|head coach|free agen(?:t|cy)|trade deadline|injur(?:y|ed) (?:list|report)|out indefinitely|sidelined)"
SCIENCE = r"\b(?:researchers?|scientists?|study (?:finds|suggests|shows|reveals)|peer-reviewed|journal (?:Nature|Science|Cell|Lancet|JAMA|PNAS)|Nobel Prize|NASA|SpaceX launch|Artemis|asteroid|exoplanet|black hole|galaxy|telescope|Webb|Hubble|fossil|dinosaur|genome|DNA|species|climate change|global warming|hurricane|earthquake|volcano|wildfire|drought|El Niño|vaccine|FDA approv|clinical trial|cancer|Alzheimer|measles|flu season|bird flu|outbreak|pandemic|public health|CDC|quantum (?:comput|physic|geometr)|physicists?|astronomers?|biologists?|neuroscien|paleontolog|archaeolog)"
TECH = r"\b(?:AI\b|artificial intelligence|LLM|GPT-?\d|ChatGPT|OpenAI|Anthropic|Claude|Gemini|Copilot|Nvidia|chip(?:s|maker)?\b|semiconductor|Apple|iPhone|iOS|macOS|Mac(?:Book| mini| Studio)|M\d (?:Pro|Max|Ultra)|Android|Google|Alphabet|Microsoft|Windows|Amazon Web Services|AWS|Meta\b|Facebook|Instagram|TikTok|X\b(?= |,)|Twitter|Tesla|SpaceX|Starlink|cyber(?:security|attack)|hack(?:ers?|ed)|ransomware|data breach|vulnerability|CVE-\d|open[- ]source|GitHub|software|app\b|startup|Silicon Valley|data center|cloud|robot(?:ics)?|drone|EV\b|electric vehicle|self-driving|autonomous|crypto|bitcoin|Bitcoin|Ethereum|blockchain|stablecoin|smartphone|gadget|laptop|GPU|processor)"
BUSINESS = r"\b(?:CEO|CFO|executive|company|companies|corporate|merger|acquisition|acquires?|to buy|takeover|deal|bankruptcy|Chapter 11|layoffs?|job cuts|hiring|union|strike|workers|wages?|tariffs?|trade (?:war|deal|talks|tensions)|supply chain|shipping|port of|container|freight|retail(?:er)?|consumer|sales|housing|home sales|mortgage|real estate|realtor|homebuyers?|rent(?:s|al)?|landlord|developer|construction|small business|entrepreneur|franchise|restaurant|airline|Boeing|Airbus|automaker|Ford|GM\b|Toyota|bank(?:s|ing)?|JPMorgan|Goldman|Bank of America|Wells Fargo|Citi|insurance|insurer|economy|economic|GDP|recession|growth|manufactur(?:ing|er)|factory|energy|utility|power plant|grid|solar|wind farm|nuclear|LNG|pipeline|refinery|cannabis|marijuana|hemp|dispensar(?:y|ies)|casino|gaming revenue|resort|tourism|LVCVA|Strip)"
POLITICS = r"\b(?:Supreme Court|SCOTUS|justices?|appeals court|circuit court|federal judge|constitutional|First Amendment|Second Amendment|14th Amendment|birthright citizenship|Congress|congressional|Senate|senators?|House (?:vote|bill|passes|Republicans|Democrats|Speaker)|Speaker|bill (?:passes|signed|vetoed)|legislation|legislature|lawmakers?|governor|mayor|city council|county commission|election|elections|ballot|voters?|voting|early voting|mail ballots?|midterms?|primary|campaign|candidate|poll(?:s|ing)?|Republicans?|Democrats?|GOP|MAGA|White House|president(?:ial)?|Trump|Vance|administration|executive order|impeach|filibuster|shutdown|budget|deficit|spending bill|appropriations|veto|nominee|confirmation|attorney general|secretary of (?:state|war|defense|treasury|education|labor)|Rubio|Hegseth|ambassador|State Department|sanctions|immigration|ICE|deportation|asylum|refugees?|border|DOGE|federal (?:workers|workforce|employees)|OPM|FOIA|watchdog|inspector general|GAO|CBO|lobby(?:ing|ist)|PAC|political)"
CRIME_LOCAL_US = r"\b(?:police|sheriff|deputies|LVMPD|NCSO|Metro(?: police)?|arrested|arrest|charged|indicted|sentenced|pleads? guilty|convicted|murder|homicide|shooting|shot|stabbing|killed|dies|dead|death|crash|rollover|collision|pursuit|suspect|robbery|burglary|fraud|scam|missing|found dead|fire(?:fighters)?|wildfire|flood(?:ing)?|flash[- ]flood|storm(?! of)|tornado|hurricane|evacuat|school district|students?|teacher|hospital|overdose|fentanyl|opioid|jail|prison|inmate|DUI|highway|freeway|I-\d+|US-\d+|road(?:s)? (?:closed|reopen)|closure|outage)"
DEFENSE = r"\b(?:Army|Navy|Air Force|Marines?|Space Force|National Guard|Pentagon|Department of War|Hegseth|troops|soldiers?|warship|destroyer|aircraft carrier|USS \w+|fighter jets?|F-35|missile|interceptor|drone warfare|counter-drone|defense contract|Lockheed|Raytheon|RTX|Northrop|General Dynamics|Anduril|AUSA|CENTCOM|NATO)"
RX = {k: _rx(v) for k, v in dict(US_STATES=US_STATES, US_CITIES=US_CITIES, US_FED=US_FED, FOREIGN=FOREIGN, SPORTS=SPORTS, SCIENCE=SCIENCE, TECH=TECH, BUSINESS=BUSINESS, POLITICS=POLITICS, CRIME=CRIME_LOCAL_US, DEFENSE=DEFENSE).items()}
RX["SCIENCE_STRONG"] = _rx(r"\b(?:researchers?(?! at (?:OpenAI|Google|Microsoft|Meta|Apple|Nvidia|Anthropic))|scientists?|study (?:finds|suggests|shows|reveals|links)|peer-reviewed|Nobel Prize|NASA|Artemis|asteroid|exoplanet|black hole|telescope|Webb|Hubble|fossil|dinosaur|genome|new species|astronomers?|physicists?|biologists?|paleontolog\w*|archaeolog\w*|neuroscien\w*|clinical trial|FDA approv\w*|vaccine|outbreak|measles|bird flu|climate (?:change|scientists)|global warming|El Niño|Mars (?:moon|rover|sample)|SpaceX launch|rocket launch|quantum (?:comput\w*|physic\w*))\b")
RX["US_ANY"] = _rx(f"\\b(?:{US_STATES}|{US_CITIES}|{US_FED}|U\\.S\\.|US\\b|America(?:n|ns)?)\\b")
RX["FOREIGN_B"] = _rx(f"\\b(?:{FOREIGN})\\b")
RX["US_GEO"] = _rx(f"\\b(?:{US_STATES}|{US_CITIES}|U\\.S\\.|US\\b|America(?:n|ns)?|Congress|Senate|White House|SCOTUS|federal)\\b")
RX["FED"] = _rx(r"\b(?:FOMC|Federal Reserve|the Fed\b|Fed(?:'s)? (?:chair|governor|president|minutes|rate|official|Williams|Hammack|Cook|Powell|Waller|Bowman|Jefferson|Musalem|Goolsbee|Daly|Logan|Bostic)|rate (?:hike|cut)s?\b|interest rates?)")
RX["MARKETS_T"] = _rx(r"\b(?:stocks?|shares(?! of (?:the|their|its|our|water|Colorado))|S&P(?: 500)?|Dow(?: Jones)?|Nasdaq|Wall Street|Treasur(?:y|ies) yields?|bond market|yields?|earnings|EPS|dividend|IPO|buyback|ETF|options|futures|crude|Brent|WTI|oil prices?|OPEC\+?|bpd|barrels|gold price|bitcoin|BTC|Ethereum|ETH\b|XRP|Solana|crypto|stablecoin|Nikkei|FTSE|rupee|yen\b|forex|investors?|traders?|hedge fund|m-cap|market cap|sell-off)\b")
RX["STATE_COURT"] = _rx(r"\b(?:" + US_STATES + r"|state) Supreme Court\b")
RX["COURTS"] = _rx(r"\b(?:Supreme Court|SCOTUS|justices|appeals court|circuit court|federal judge|constitutional|Amendment|birthright citizenship)\b")
RX["FOREIGN_COURT"] = _rx(r"\b(?:India|Indian|Canada|Canadian|UK|U\.K\.|British|Pakistan|Israel|Israeli|Kenya|Nigeria|Australia|Philippine|Brazil|Mexico)\b")

# Single-topic sources -> section (applied first; feeds are single-topic so precision is ~1.0).
SOURCE_SECTION = {
 "Golf.com": "sports", 'Google News: PGA Tour OR LIV Golf': "sports",
 "SCOTUSblog": "politics", "Federal News Network": "politics", "Government Executive": "politics", "CBO Publications": "politics",
 "GAO Reports": "politics", "Federal Register Presidential Docs": "politics", "Congress.gov Presented to President": "politics", "Congress.gov Most-Viewed Bills": "politics",
 "US Courts Judiciary News": "politics", "OpenSecrets News": "politics", "NPR Politics": "politics", "NYT Politics": "politics", "Playbook": "politics", "The Hill Policy": "politics",
 'Google News: federal workforce OR federal employees OPM': "politics", 'Google News: government transparency FOIA': "politics",
 "Defense News": "world", "Breaking Defense": "world", "Foreign Policy": "world", "Foreign Affairs": "world", "War on the Rocks": "world", "Crisis Group": "world",
 "Phys.org - latest science and technology news stories": "science", "Nature": "science", "Latest Science News -- ScienceDaily": "science", "Popular Science": "science",
 "Science Latest": "science", "New Scientist - Space": "science", "NASA": "science", "Space | The Guardian": "science", "NYT > Science": "science", "Reddit Science": "science",
 "HousingWire": "business", "MJBizDaily": "business", "Marijuana Moment": "politics", "gCaptain (shipping)": "business", "Poynter": "business", "Nieman Lab": "business", "Columbia Journalism Review": "business",
 "OilPrice.com": "markets", "Rigzone": "markets", "EIA Today in Energy": "business", "Federal Reserve Press": "markets", "Federal Reserve Speeches": "markets", "NY Fed Liberty Street Economics": "markets",
 'Google News: FOMC OR "Federal Reserve" rates': "markets", 'Google News: fedgazette OR "Minneapolis Fed"': "markets", 'Google News: OPEC crude oil': "markets",
 "Cointelegraph.com News": "markets", "Bitcoin News": "markets", "CryptoPotato": "markets", "News - Cryptonews": "markets", "DailyCoin": "markets", "NewsBTC": "markets",
 "9to5Mac": "tech", "MacRumors": "tech", "AppleInsider": "tech", "The Verge": "tech", "Ars Technica": "tech", "WIRED": "tech", "TechCrunch": "tech", "cybersecurity | TechCrunch": "tech",
 "Engadget - Technology News & Expert Reviews": "tech", "www.theregister.com - Articles": "tech", "CNET": "tech", "Gizmodo": "tech", "The Keyword": "tech", "OpenAI News": "tech",
 "Hugging Face Blog": "tech", "Simon Willison (LLMs)": "tech", "Hacker News": "tech", "Hacker News 200+": "tech", 'Google News: local LLM OR llama.cpp OR Ollama OR MLX': "tech", 'Google News: Mac Studio OR "M5" Apple silicon AI': "tech",
 "Dept of War (DoD) News": "us", "Dept of War (DoD) Releases": "us",
}
# Sources whose upstream category is known wrong: never trust it, fall through to keyword rules and project hints.
UNTRUSTED_CATEGORY_SOURCES = {"Top stories - Google News", "All News", "Investing.com Stock Market", "Investing.com Economic Indicators", "Seeking Alpha Market Currents",
 "Forbes - Business", "Inc.com", "Fortune | FORTUNE", "Economic Times", "Las Vegas Review-Journal", "Las Vegas Sun", "KTNV Las Vegas", "The Nevada Independent",
 "World & Nation", "World News - Breaking News, Top Stories", "Al Jazeera", "Guardian World", "NYT World", "BBC World", "CNBC Top News", "ReadWrite", "Small Business Trends",
 'Google News: "Supreme Court" ruling', 'Google News: small business owners', 'Google News: political violence', 'Google News: propaganda OR disinformation media',
 'Google News: Las Vegas real estate', 'Google News: Nevada Supreme Court OR "Nevada law"', 'Google News: Nevada ballot question', 'Google News: Nevada legislature',
 'Google News: "State Department" Rubio OR sanctions', 'Google News: Strait of Hormuz OR tanker OR "oil pipeline" route', 'Google News: BRICS', 'Google News: House vote OR Senate vote bill passes',
 "World News, Today World News, Latest International News, World Breaking News, Trending News of World - Times of India", "PR Newswire M&A", "PR Newswire General Business", "PR Newswire Contracts", "PR Newswire Joint Ventures", "PR Newswire Business Tech", "Business Wire"}
PROJECT_HINT = {"golf": "sports", "foreign": "world", "fed": "markets", "oil": "markets", "markets": "markets", "ai": "tech", "civic": "politics",
                "smallbiz": "business", "realestate": "business", "cannabis": "business", "media": "world", "nevada": "us"}

def categorize_rule(item, pub=None):
    """(section, rule id). Ordered rules, first match wins; see audits/taxonomy.md §3.1 for fire counts and precision."""
    pub = pub or publisher(item)
    src = str(item.get("source") or "")
    t = item.get("title") or ""
    summ = _text(item.get("summary"))
    ts = f"{t} {summ[:240]}"
    projects = set(item.get("projects") or [])
    upstream = item.get("category")
    if src in SOURCE_SECTION:
        sec = SOURCE_SECTION[src]
        if sec in ("sports", "science"): return sec, "R0_source"
        if sec == "politics" and RX["SPORTS"].search(t) and not re.search(r"Supreme Court|court|judge", t, re.I): return "sports", "R1_sports"
        return sec, "R0_source"
    if RX["SPORTS"].search(t) and not re.search(r"\b(?:stock|shares|lawsuit|Supreme Court|sues|bankrupt|data center|arena deal|developer)\b", t, re.I): return "sports", "R1_sports"
    if RX["CRIME"].search(t) and not RX["FOREIGN_B"].search(t) and not re.search(r"\b(?:Supreme Court|SCOTUS|Congress|Senate|stock|shares|prices?|refiner|AI\b|OpenAI|Claude|ChatGPT|Nobel)\b", t) \
       and (RX["US_ANY"].search(t) or "regional" in (pub.get("flags") or ()) or not RX["FOREIGN_B"].search(f"{t} {summ[:200]}")): return "us", "R2_us_safety"
    if RX["FED"].search(t): return "markets", "R3_fed"
    if RX["MARKETS_T"].search(t): return "markets", "R4_markets"
    if RX["STATE_COURT"].search(t) and not re.search(r"\bU\.?S\.? Supreme Court\b", t): return "us", "R5b_state_court"
    if RX["COURTS"].search(t):
        if RX["FOREIGN_COURT"].search(t) and not RX["US_GEO"].search(t): return "world", "R7_foreign_court"
        return "politics", "R5_courts"
    if RX["SCIENCE_STRONG"].search(t) or (len(RX["SCIENCE"].findall(t)) >= 2 and not re.search(r"\b(?:AI|OpenAI|Nvidia|Apple|Google|Microsoft|Meta|pope|Pope|stock|shares|Act\b)\b", t)): return "science", "R6_science"
    fo_hits = len(RX["FOREIGN_B"].findall(t))
    if RX["DEFENSE"].search(t) and fo_hits: return "world", "R7_defense_world"
    if fo_hits and not re.search(r"\b(?:Congress|Senate|House|midterms?|voters|ballot|Supreme Court|governor)\b", t): return "world", "R7_foreign"
    if RX["TECH"].search(t) and not re.search(r"\b(?:Congress|Senate|Supreme Court|election|ballot)\b", t): return "tech", "R8_tech"
    if RX["POLITICS"].search(t): return "politics", "R9_politics"
    if RX["BUSINESS"].search(t) or re.search(r"\b(?:prices?|inflation|economy|GDP|jobs|unemployment|wages|cost of living|affordability)\b", t, re.I) or projects & {"smallbiz", "realestate", "cannabis"}: return "business", "R10_business"
    if RX["FOREIGN_B"].search(ts) and not RX["US_ANY"].search(ts): return "world", "R11_foreign_summary"
    if src in UNTRUSTED_CATEGORY_SOURCES or pub.get("via") == "google_news":
        for p in ("golf", "fed", "oil", "foreign", "ai", "civic", "smallbiz", "realestate", "cannabis", "media", "markets"):
            if p in projects: return PROJECT_HINT[p], f"R12_project_{p}"
        if pub.get("default") in CAT_NAME and pub.get("default") != "local": return pub["default"], "R13_publisher_default"
        return "us", "R14_fallback_us"
    if upstream in SECTIONS and upstream != "local": return upstream, "R15_upstream"
    d = pub.get("default")
    return (d if d in CAT_NAME and d != "local" else "us"), "R13_publisher_default"

def categorize(item, pub=None):
    """National section key (one of config.CAT_NAME, never "local": Local is a flag from regions, not a section rule)."""
    sec, _ = categorize_rule(item, pub)
    return sec if sec in CAT_NAME else "us"

# ====================================================================== 6. REGIONS
# Ordered most specific first. aliases are regex fragments matched case-insensitively with word boundaries over
# title + summary. parent = administrative parent (rolled up automatically); also = other umbrellas rolled up too.
def _R(name, state, kind, aliases, parent=None, also=(), wikidata=None, home=False, intro="", links=()):
    return {"name": name, "state": state, "kind": kind, "aliases": list(aliases), "parent": parent, "also": list(also),
            "wikidata": wikidata, "home": home, "intro": intro, "links": list(links)}
REGIONS = OrderedDict([
 ("bullhead-city", _R("Bullhead City", "AZ", "city",
   [r"bullhead(?: city)?(?! (?:catfish|shark|minnow))", r"riviera, ariz", r"Mohave High", r"Colorado River Union", r"Laughlin[/-]Bullhead", r"Bullhead City (?:Police|Fire|Council|Mayor|Parkway)", r"Rotary Park", r"Bullhead Area Chamber", r"Laughlin/Bullhead International"],
   parent="mohave-county", also=("colorado-river",), wikidata="Q79432", home=True,
   intro="Bullhead City sits on the Arizona bank of the Colorado River across from Laughlin, Nevada. With about 42,000 residents it is the largest city in the corridor, home to the Laughlin/Bullhead International Airport, Mohave High School and the Colorado River Union High School District. News here covers the city council, police and fire departments, river recreation, housing growth and the data-center and utility decisions shaping Mohave County's economy.",
   links=[("City of Bullhead City", "https://www.bullheadcity.com"), ("Mohave Valley Daily News", "https://www.mohavedailynews.com"), ("Bullhead Area Chamber of Commerce", "https://www.bullheadareachamber.com")])),
 ("laughlin", _R("Laughlin", "NV", "area",
   [r"laughlin(?! (?:Air Force|AFB))", r"Don Laughlin", r"Riverside Resort", r"Aquarius Casino", r"Edgewater (?:Casino|Hotel|Laughlin)", r"Harrah'?s Laughlin", r"Tropicana Laughlin", r"Golden Nugget Laughlin", r"Laughlin Event Center", r"Cal[- ]?Nev[- ]?Ari", r"Searchlight, Nev\w*", r"Avi Resort", r"Needles Hwy", r"Laughlin (?:Town Advisory|Library|Ranch|River Run|Chamber|Constable|Justice Court)", r"Colorado Belle", r"Pioneer Hotel"],
   parent="clark-county", also=("colorado-river",), wikidata="Q594154", home=True,
   intro="Laughlin is an unincorporated resort town at the southern tip of Clark County, Nevada, on the Colorado River opposite Bullhead City. Founded by Don Laughlin in 1966, it draws visitors to its riverfront casinos, the Laughlin Event Center and off-road racing in the surrounding desert. Coverage follows the Laughlin Town Advisory Board, Clark County services for the town, tourism and gaming, and the river itself.",
   links=[("Clark County: Laughlin", "https://www.clarkcountynv.gov/government/departments/laughlin/"), ("Visit Laughlin", "https://www.visitlaughlin.com"), ("Laughlin Chamber of Commerce", "https://www.laughlinchamber.com")])),
 ("mohave-valley", _R("Mohave Valley", "AZ", "area",
   [r"mo[hj]ave valley", r"fort mo[hj]ave", r"Fort Mojave (?:Indian )?Tribe", r"Spirit Mountain", r"Golden Shores", r"Topock", r"Fort Mojave Mesa", r"Mohave Valley (?:Fire|Elementary|Irrigation)", r"Aha Macav"],
   parent="mohave-county", also=("colorado-river",), wikidata="Q615832", home=True,
   intro="Mohave Valley and Fort Mohave are unincorporated communities along the Colorado River south of Bullhead City, Arizona, neighbouring the Fort Mojave Indian Reservation and the Spirit Mountain casino. The area is served by the Fort Mojave Mesa and Mohave Valley fire departments, Mohave County government and the Mohave Valley Elementary School District. Stories here cover growth, roads, fire and public safety, tribal news and river access.",
   links=[("Mohave County", "https://www.mohave.gov"), ("Fort Mojave Indian Tribe", "https://www.fortmojaveindiantribe.com"), ("Mohave Valley Daily News", "https://www.mohavedailynews.com")])),
 ("needles", _R("Needles", "CA", "city",
   [r"Needles,? (?:Calif\w*|CA\b|California)", r"City of Needles", r"Needles (?:Unified|Marina|Bridge|Police|Chamber|Senior|Highway|Airport|Regional|City Council|Mayor)", r"downtown Needles", r"in Needles\b", r"Needles-area"],
   parent="mojave-desert", also=("colorado-river",), wikidata="Q846591", home=True,
   intro="Needles is a small California city on the Colorado River and Interstate 40, just downstream from Mohave Valley and the Fort Mojave reservation. A historic Route 66 and railroad town in San Bernardino County, it shares the river, the job market and the news cycle with the Arizona and Nevada communities across the water. Coverage includes the city council, Needles Unified schools, the bridge and highway corridors and river recreation.",
   links=[("City of Needles", "https://www.cityofneedles.com"), ("Needles Chamber of Commerce", "https://www.needleschamber.com")])),
 ("lake-havasu-city", _R("Lake Havasu City", "AZ", "city",
   [r"lake havasu(?: city)?", r"havasu(?! falls| creek|pai)", r"Lake Havasu Unified", r"LHCPD", r"Havasu Regional Medical", r"ASU (?:at )?Havasu", r"London Bridge.*(?:Havasu|Ariz)", r"Havasu News"],
   parent="mohave-county", also=("colorado-river",), wikidata="Q79435", home=True,
   intro="Lake Havasu City, Arizona, is the Colorado River corridor's boating and tourism hub, built around the lake behind Parker Dam and the relocated London Bridge. With about 58,000 residents it is Mohave County's largest city, home to Havasu Regional Medical Center, the Lake Havasu Unified School District and an ASU campus. Coverage follows city hall, police and fire, the lake and river, and seasonal tourism.",
   links=[("Lake Havasu City", "https://www.lhcaz.gov"), ("Today's News-Herald", "https://www.havasunews.com"), ("Go Lake Havasu", "https://www.golakehavasu.com")])),
 ("kingman", _R("Kingman", "AZ", "city",
   [r"kingman(?!, Kan| Reef)", r"Golden Valley(?:, Ariz)?(?!, Minn)", r"Dolan Springs", r"Hualapai", r"Route 66.*(?:Ariz|Mohave|Kingman)", r"Chloride, Ariz", r"Meadview", r"White Hills, Ariz", r"Kingman (?:Regional|Airport|Unified|Police|Fire|City Council|Mayor|Academy)", r"KRMC"],
   parent="mohave-county", wikidata="Q79733", home=True,
   intro="Kingman is the Mohave County seat, an Interstate 40 and Route 66 crossroads about 35 miles east of the Colorado River. Its roughly 35,000 residents are served by Kingman Regional Medical Center, the Kingman Unified School District and Mohave Community College, and the county's courts, sheriff and board of supervisors sit here. Coverage includes county government, the city council, highways and rail, and the Hualapai and Golden Valley communities nearby.",
   links=[("City of Kingman", "https://www.cityofkingman.gov"), ("Kingman Daily Miner", "https://kdminer.com"), ("Mohave County", "https://www.mohave.gov")])),
 ("mohave-county", _R("Mohave County", "AZ", "county",
   [r"mohave county", r"MCSO\b", r"Colorado City, Ariz", r"Beaver Dam, Ariz", r"Littlefield, Ariz", r"Oatman", r"Mohave Community College", r"Mohave Electric", r"Mohave County (?:Sheriff|Supervisors|Board|Elections|Recorder|Library|Development Services|Attorney|Superior Court)"],
   parent="arizona", wikidata="Q58696", home=True,
   intro="Mohave County covers the northwest corner of Arizona, from the Colorado River communities of Bullhead City, Mohave Valley and Lake Havasu City to Kingman and the Arizona Strip. Its 13,000 square miles make it one of the largest counties in the United States, governed by a five-member board of supervisors with the sheriff's office, elections department and superior court in Kingman. Coverage follows the supervisors, elections, the sheriff, planning and water decisions that reach every town in the corridor.",
   links=[("Mohave County", "https://www.mohave.gov"), ("Mohave County Sheriff's Office", "https://www.mcsoaz.gov"), ("Mohave County Elections", "https://www.mohave.gov/elections")])),
 ("lake-mead", _R("Lake Mead", "NV", "area",
   [r"Lake Mead(?! (?:Blvd|Boulevard|Pkwy|Parkway|Dr\b|Drive))", r"Hoover Dam", r"Boulder Dam", r"Lake Mead (?:National Recreation Area|NRA)", r"Callville Bay", r"Boulder Beach", r"Echo Bay", r"Temple Bar", r"Willow Beach", r"Cottonwood Cove", r"Katherine Landing", r"Lake Mohave", r"Arizona Hot Springs"],
   parent="boulder-city", also=("colorado-river",), wikidata="Q654515", home=True,
   intro="Lake Mead is the reservoir behind Hoover Dam and the centrepiece of Lake Mead National Recreation Area, which also takes in Lake Mohave down to Davis Dam above Laughlin and Bullhead City. The park is managed from Boulder City by the National Park Service and the lake's level is the region's most watched number, set by Bureau of Reclamation operations and Colorado River shortage rules. Coverage includes park alerts, marinas and launch ramps, water levels and dam operations.",
   links=[("Lake Mead National Recreation Area", "https://www.nps.gov/lake/"), ("Bureau of Reclamation: Lower Colorado", "https://www.usbr.gov/lc/"), ("Hoover Dam", "https://www.usbr.gov/lc/hooverdam/")])),
 ("boulder-city", _R("Boulder City", "NV", "city",
   [r"boulder city(?!, Colo)", r"Nevada State Railroad Museum", r"Eldorado Valley", r"Boulder City (?:Review|Hospital|Council|Mayor|Police|Fire|Chamber|High)", r"Hemenway (?:Park|Valley)", r"Boulder Creek Golf", r"Nevada Way\b"],
   parent="clark-county", also=("colorado-river",), wikidata="Q858801", home=True,
   intro="Boulder City, Nevada, was built in 1931 to house Hoover Dam's workers and remains one of two Nevada cities that prohibit gambling. About 15,000 people live in the historic town 25 miles southeast of Las Vegas, gateway to Lake Mead National Recreation Area and home to the Nevada State Railroad Museum and the Eldorado Valley solar fields. Coverage follows the city council, utilities and growth-control ordinances, the dam and the lake, and the Boulder City Review.",
   links=[("City of Boulder City", "https://www.bcnv.org"), ("Boulder City Review", "https://bouldercityreview.com"), ("Boulder City Chamber of Commerce", "https://www.bouldercitychamber.com")])),
 ("mesquite", _R("Mesquite", "NV", "city",
   [r"mesquite(?:, nev| nv|, nevada|,? Nev\.| police| city| golf| gaming| mayor| council| fire| chamber| recreation| library| local news| blvd)", r"City of Mesquite", r"Virgin Valley", r"Bunkerville", r"Overton, Nev", r"Logandale", r"Moapa Valley", r"Moapa\b", r"Eureka Casino", r"CasaBlanca Resort", r"Mesquite Gaming", r"Mesquite Local News"],
   parent="clark-county", wikidata="Q991218", home=True,
   intro="Mesquite is a city of about 25,000 on Interstate 15 at the Nevada-Arizona line, 80 miles northeast of Las Vegas in the Virgin Valley. Known for golf, casinos and retirement communities, it also serves the farming towns of Bunkerville and the Moapa Valley and sits a short drive from St. George, Utah. Coverage follows city hall, Mesquite police and fire, the Virgin Valley Water District, I-15 and the Virgin River.",
   links=[("City of Mesquite", "https://www.mesquitenv.gov"), ("Mesquite Local News", "https://mesquitelocalnews.com"), ("Mesquite Chamber of Commerce", "https://www.mesquitenvchamber.com")])),
 ("henderson", _R("Henderson", "NV", "city",
   [r"henderson(?:, nev| nv|, nevada|,? Nev\.)", r"City of Henderson", r"Henderson (?:Police|Fire|City Council|Mayor|Pavilion|Executive Airport|Convention Center|Symphony|Silver Knights|Hospital)", r"Green Valley (?:Ranch|Pkwy|Parkway|High|, Nev)", r"Anthem, Nev", r"Inspirada", r"Cadence, Nev", r"Clark County Museum", r"Lake Las Vegas", r"Water Street District", r"Dollar Loan Center", r"Lee'?s Family Forum", r"Touro University Nevada"],
   parent="las-vegas", wikidata=None, home=True,
   intro="Henderson is Nevada's second-largest city, with more than 330,000 residents on the southeast side of the Las Vegas Valley between the Strip and Lake Mead. Its master-planned communities, the Water Street District, the Henderson Executive Airport and the Clark County Museum make it a frequent dateline for growth, sports and parks news. Coverage follows the Henderson city council, police and fire, schools and development.",
   links=[("City of Henderson", "https://www.cityofhenderson.com"), ("Henderson Chamber of Commerce", "https://www.hendersonchamber.com")])),
 ("north-las-vegas", _R("North Las Vegas", "NV", "city",
   [r"north las vegas", r"NLV\b", r"Nellis(?: AFB| Air Force Base)?", r"Aliante", r"Craig Ranch", r"Apex Industrial", r"North Las Vegas (?:Police|Mayor|City Council|Airport|Library)"],
   parent="las-vegas", home=True,
   intro="North Las Vegas is a city of about 290,000 on the north side of the Las Vegas Valley, home to Nellis Air Force Base, the Aliante and Craig Ranch communities and the fast-growing Apex industrial park. Coverage follows the city council and mayor, the North Las Vegas Police Department, Nellis and the warehouses and manufacturers moving in along Interstate 15.",
   links=[("City of North Las Vegas", "https://www.cityofnorthlasvegas.com"), ("Nellis Air Force Base", "https://www.nellis.af.mil")])),
 ("las-vegas", _R("Las Vegas", "NV", "city",
   [r"las vegas(?!, new mexico|, N\.M)", r"LVMPD", r"Las Vegas Metropolitan Police", r"Metro Police", r"Las Vegas Strip", r"Fremont Street", r"Downtown Las Vegas", r"Summerlin", r"Spring Valley, Nev", r"Paradise, Nev", r"Sunrise Manor", r"Whitney, Nev", r"Enterprise, Nev", r"UNLV", r"Allegiant Stadium", r"T-Mobile Arena", r"(?:the|at) Sphere\b", r"Sphere (?:in Las Vegas|Entertainment)", r"Harry Reid(?: International)?(?: Airport)?", r"McCarran", r"LVCVA", r"Raiders(?!'? of the Lost)", r"Golden Knights", r"Las Vegas Aces", r"Silver Knights", r"Las Vegas Aviators", r"Clark County School District", r"CCSD", r"Sin City", r"Vegas\b", r"Caesars Palace", r"Bellagio", r"MGM Grand", r"Wynn Las Vegas", r"Resorts World", r"Fontainebleau", r"Durango Casino", r"Red Rock Resort", r"Las Vegas Convention Center", r"Thomas & Mack", r"Orleans Arena", r"Cashman Field", r"Las Vegas Ballpark", r"Mayor Berkley", r"Shelley Berkley", r"Eighth Judicial District", r"Regional Justice Center", r"Las Vegas Blvd", r"Spaghetti Bowl", r"Boulder Highway"],
   parent="las-vegas-valley", wikidata="Q23768", home=True,
   intro="Las Vegas is the heart of Clark County and the largest city within 100 miles of the Colorado River corridor: the county seat, the hub for flights through Harry Reid International Airport and the place where state politics, big-league sports and tourism meet. With about 660,000 city residents and 2.3 million in the valley, it sets the agenda for Southern Nevada on water, housing, schools and public safety. Coverage includes city hall, Metro police, the Strip and downtown, UNLV and the valley's pro teams.",
   links=[("City of Las Vegas", "https://www.lasvegasnevada.gov"), ("Las Vegas Review-Journal", "https://www.reviewjournal.com"), ("Las Vegas Sun", "https://lasvegassun.com"), ("KTNV 13 Action News", "https://www.ktnv.com")])),
 ("las-vegas-valley", _R("Las Vegas Valley", "NV", "area",
   [r"Las Vegas Valley", r"Southern Nevada", r"the valley\b.*(?:Nev|Vegas)", r"Red Rock Canyon", r"Mount Charleston", r"Lee Canyon", r"Spring Mountains", r"Sloan Canyon"],
   parent="clark-county", home=True,
   intro="The Las Vegas Valley is the metropolitan area of Las Vegas, Henderson, North Las Vegas and the unincorporated towns of Clark County, ringed by Red Rock Canyon, Mount Charleston and Sloan Canyon. Regional stories about Southern Nevada's water, transportation, schools and growth land here when they are not about a single city.",
   links=[("Clark County", "https://www.clarkcountynv.gov"), ("Southern Nevada Water Authority", "https://www.snwa.com"), ("RTC of Southern Nevada", "https://www.rtcsnv.com")])),
 ("clark-county", _R("Clark County", "NV", "county",
   [r"clark county", r"Indian Springs", r"Primm", r"Jean, Nev", r"Goodsprings", r"Sandy Valley", r"Blue Diamond, Nev", r"Mountain Springs, Nev", r"Clark County (?:Commission|Commissioners|School|Fire|Coroner|Election|Family Services|Parks|Museum|Government Center|Detention|Registrar|Health District|Water Reclamation)", r"Clark County, Nev"],
   parent="southern-nevada", wikidata="Q108403", home=True,
   intro="Clark County is Nevada's most populous county, covering Las Vegas and its suburbs as well as the outlying communities of Laughlin, Mesquite, Boulder City, Searchlight, Moapa Valley and Indian Springs. A seven-member county commission runs the Las Vegas Strip and the unincorporated towns, the election department, the Clark County School District's boundaries, the coroner and much of the region's fire and family services. Coverage follows the commission, elections, county services in the outlying towns and the agencies that serve 2.3 million people.",
   links=[("Clark County", "https://www.clarkcountynv.gov"), ("Clark County Election Department", "https://www.clarkcountynv.gov/vote"), ("Clark County School District", "https://www.ccsd.net")])),
 ("colorado-river", _R("Colorado River", "", "river",
   [r"colorado river", r"Lake Powell", r"Glen Canyon", r"Davis Dam", r"Parker Dam", r"Imperial Dam", r"Bureau of Reclamation", r"Lower Basin", r"Upper Basin", r"Central Arizona Project", r"Metropolitan Water District", r"Southern Nevada Water Authority", r"SNWA", r"Mohave County Water", r"river allocation", r"water (?:cuts|shortage|allocation|rights).*(?:Ariz|Nev|Calif|river)", r"Colorado River Indian Tribes", r"Imperial Irrigation District", r"Laughlin Bridge"],
   parent=None, wikidata="Q1265", home=True,
   intro="The lower Colorado River is the thread that ties Ground Level News's communities together: from Hoover Dam and Lake Mead past Davis Dam, Laughlin and Bullhead City to Needles, Lake Havasu and Parker Dam. Its flows, shortage declarations and the negotiations among seven states, tribes and the Bureau of Reclamation decide what the region drinks, farms and powers. This hub gathers river operations, water policy, dam news and recreation along the whole corridor.",
   links=[("Bureau of Reclamation: Lower Colorado Basin", "https://www.usbr.gov/lc/"), ("USGS water data", "https://waterdata.usgs.gov"), ("Colorado River Commission of Nevada", "https://crc.nv.gov")])),
 ("southern-nevada", _R("Southern Nevada", "NV", "area",
   [r"Pahrump", r"Nye County", r"Beatty, Nev", r"Amargosa", r"Tonopah", r"Lincoln County, Nev", r"Caliente, Nev", r"Pioche", r"Alamo, Nev"],
   parent="nevada", home=False,
   intro="Southern Nevada takes in Clark County and the rural counties around it: Nye County with Pahrump, Beatty and Tonopah, and Lincoln County with Caliente and Pioche.",
   links=[("Nevada Current", "https://nevadacurrent.com"), ("The Nevada Independent", "https://thenevadaindependent.com")])),
 ("northern-arizona", _R("Northern Arizona", "AZ", "area",
   [r"northern arizona", r"Flagstaff", r"Prescott", r"Sedona", r"Williams, Ariz", r"Coconino", r"Yavapai", r"Grand Canyon", r"Page, Ariz", r"Navajo Nation", r"Hopi", r"Verde Valley", r"Cottonwood, Ariz", r"Camp Verde", r"Winslow, Ariz", r"Holbrook", r"Show Low", r"Payson, Ariz", r"NAU\b", r"Northern Arizona University"],
   parent="arizona", home=False,
   intro="Northern Arizona covers Flagstaff, Prescott, Sedona, the Grand Canyon and the Navajo and Hopi nations, the high country east of Mohave County.",
   links=[("Arizona Daily Sun", "https://azdailysun.com"), ("KNAU", "https://www.knau.org")])),
 ("western-arizona", _R("Western Arizona", "AZ", "area",
   [r"La Paz County", r"Parker, Ariz", r"Quartzsite", r"Yuma", r"Blythe", r"Ehrenberg", r"Bill Williams River", r"Alamo Lake", r"Wickenburg", r"Salome, Ariz"],
   parent="arizona", home=False,
   intro="Western Arizona runs down the lower Colorado River from Parker and La Paz County to Yuma, downstream of Lake Havasu.",
   links=[("Parker Pioneer", "https://www.parkerpioneer.net")])),
 ("utah-dixie", _R("St. George and Southern Utah", "UT", "area",
   [r"st\.? george(?:, Utah)?", r"Washington County, Utah", r"Hurricane, Utah", r"Cedar City", r"Dixie\b", r"Zion National", r"Utah Tech", r"Kanab", r"Springdale, Utah", r"Ivins", r"Santa Clara, Utah", r"Iron County, Utah", r"Kane County", r"Southern Utah University", r"SUU\b"],
   parent="utah", home=False,
   intro="St. George and Utah's Dixie are 40 miles up Interstate 15 from Mesquite: Washington County, Zion National Park, Cedar City and the fastest-growing corner of Utah.",
   links=[("St. George News", "https://www.stgeorgeutah.com")])),
 ("mojave-desert", _R("Mojave Desert, California", "CA", "area",
   [r"Barstow", r"Baker, Calif", r"Mojave National Preserve", r"Twentynine Palms", r"Joshua Tree", r"San Bernardino County", r"Victorville", r"Death Valley"],
   parent=None, home=False,
   intro="The California Mojave Desert west of the river: Needles, Barstow, the Mojave National Preserve and San Bernardino County's high desert.",
   links=[])),
 ("nevada", _R("Nevada", "NV", "state",
   [r"nevada", r"nevadans?", r"Nev\b", r"Reno(?! 911)", r"Sparks, Nev", r"Carson City", r"Washoe", r"Elko", r"Ely, Nev", r"Winnemucca", r"Fallon, Nev", r"Fernley", r"Minden, Nev", r"Gardnerville", r"Lake Tahoe", r"(?:Gov\.?|Governor|Joe) Lombardo", r"Cortez Masto", r"Jacky Rosen", r"Dina Titus", r"Horsford", r"Susie Lee", r"Amodei", r"Aaron Ford", r"Nevada (?:Legislature|Senate|Assembly|Supreme Court|Gaming|DMV|DOT|NDOT|Highway Patrol|NHP|System of Higher Education|NSHE)", r"Silver State", r"Battle Born"],
   parent=None, wikidata="Q1227", home=False,
   intro="Statewide Nevada news: the Legislature in Carson City, the governor and congressional delegation, the Nevada Supreme Court, gaming regulators and the agencies whose decisions reach Clark County's river towns.",
   links=[("State of Nevada", "https://nv.gov"), ("Nevada Legislature", "https://www.leg.state.nv.us"), ("The Nevada Independent", "https://thenevadaindependent.com")])),
 ("arizona", _R("Arizona", "AZ", "state",
   [r"arizona", r"arizonans?", r"Ariz\b", r"Phoenix(?!, Ore)", r"Tucson", r"Scottsdale", r"Tempe", r"Chandler, Ariz", r"Gilbert, Ariz", r"Glendale, Ariz", r"Mesa, Ariz", r"Maricopa", r"Pima County", r"Katie Hobbs", r"Gov\.? Hobbs", r"Ruben Gallego", r"Mark Kelly", r"Andy Biggs", r"Schweikert", r"Gosar", r"Crane, Ariz", r"Arizona (?:Legislature|Senate|House|Supreme Court|Corporation Commission|DPS|DOT|ADOT|Game and Fish|State|Sun Devils|Wildcats)", r"Arizona State University", r"Arizona Public Service", r"Salt River Project", r"UniSource", r"Grand Canyon State"],
   parent=None, wikidata="Q816", home=False,
   intro="Statewide Arizona news: the Legislature and governor in Phoenix, the Arizona Corporation Commission that regulates Mohave Electric and UniSource, the state Supreme Court, ADOT and the elections that Mohave County votes in.",
   links=[("State of Arizona", "https://az.gov"), ("Arizona Mirror", "https://azmirror.com"), ("Cronkite News", "https://cronkitenews.azpbs.org")])),
 ("utah", _R("Utah", "UT", "state",
   [r"\butah\b", r"utahns?", r"Salt Lake", r"Provo", r"Ogden", r"Spencer Cox", r"Gov\.? Cox", r"Mike Lee", r"BYU"],
   parent=None, home=False,
   intro="Statewide Utah news, relevant to Mesquite and the Virgin Valley through St. George and Interstate 15.",
   links=[("The Salt Lake Tribune", "https://www.sltrib.com")])),
])
REGION_RX = {k: re.compile(r"\b(?:" + "|".join(v["aliases"]) + r")\b", re.I) for k, v in REGIONS.items()}
# Aliases that only count when the item comes from a regional newsroom (too ambiguous in national copy).
_SOURCE_ONLY = {"las-vegas": _rx(r"\b(?:the Strip|the valley|Metro\b|Spring Valley|Paradise|Downtown)\b"), "henderson": _rx(r"\bHenderson\b"),
                "mesquite": _rx(r"\bMesquite\b(?!\s+(?:tree|trees|wood|smoke|smoked|grill|grilled|flour|bean|beans|chips?|charcoal|BBQ|barbecue|Street|St\.|Ave\.?|Avenue|Road|Rd\.?|Lane|Ln\.?))"),
                "laughlin": _rx(r"\b(?:Edgewater|Riverside|the river\b)"), "bullhead-city": _rx(r"\bBullhead\b")}
HOME_REGIONS = frozenset(k for k, v in REGIONS.items() if v["home"])
STATE_REGIONS = frozenset(k for k, v in REGIONS.items() if not v["home"])
# False friends removed from the text before matching: other places with our names, sports teams, products, idioms.
REGION_FALSE_FRIENDS = _rx(r"\b(?:Franco-Nevada|Sierra Nevada|Nevada City|Nevada Gold|Nevada Copper|Nevada Canyon|Las Vegas, New Mexico|Las Vegas, N\.M\.|Henderson, (?:Ky|Kentucky|N\.?C|Texas|Tex|Colo|Tenn)\.?|Mesquite, (?:Tex|Texas)|mesquite[- ](?:tree|trees|wood|smoke|smoked|grill|grilled|flour|bean|beans|chips?|charcoal|BBQ|barbecue)|Boulder, Colo|Boulder, Colorado|Kingman, Kan\.?|Kingman Reef|Parker, Colo|Phoenix Suns|Phoenix Mercury|Arizona Cardinals|Arizona Diamondbacks|Joaquin Phoenix|River Phoenix|Gaza Strip|Red Raiders|Raiders of the Lost Ark|Oakland Raiders|Laughlin (?:Air Force Base|AFB)|bullhead (?:catfish|shark|minnow)|Golden Valley, Minn\.?|Green Valley, Ariz|Spring Valley, (?:N\.?Y|Calif|Ill|Wis)\.?|Hobbs, N\.?M\.?|London'?s Metropolitan Police|Metropolitan Police Service|Janet Reno|Reno 911|Virgin River \(|Washington County, (?:Ore|Pa|Md|Minn|Wis)\.?|Salt Lake Potash|Lake Mead Blvd|Lake Mead Boulevard)\b")

def region_parents(key):
    """All ancestors of a region key (parent chain plus `also` umbrellas), nearest first."""
    out, seen = [], {key}
    stack = []
    r = REGIONS.get(key)
    if not r: return out
    stack.extend([r.get("parent")] + list(r.get("also") or []))
    while stack:
        k = stack.pop(0)
        if not k or k in seen or k not in REGIONS: continue
        seen.add(k); out.append(k)
        rr = REGIONS[k]
        stack.extend([rr.get("parent")] + list(rr.get("also") or []))
    return out

def _ordered(keys):
    idx = {k: i for i, k in enumerate(REGIONS)}
    return sorted(set(keys), key=lambda k: idx.get(k, 999))

def detect_regions(text, source=""):
    """Region keys named in `text` (title + summary), false friends removed, wire datelines honoured, parents and
    umbrellas rolled up (laughlin -> clark-county, southern-nevada, nevada, colorado-river). Context-only aliases
    ("the Strip", bare "Henderson") count only when `source` is a regional newsroom. Sorted most specific first."""
    text = str(text or "")
    if not text: return []
    text = REGION_FALSE_FRIENDS.sub(" ", text)
    hits = [k for k, rx in REGION_RX.items() if rx.search(text)]
    dl = wire_dateline(text)
    if dl: hits.append(dl)
    if source and (source in REGIONAL_PUBLISHERS or is_regional_source({"source": source})):
        hits += [k for k, rx in _SOURCE_ONLY.items() if rx.search(text)]
    out = set(hits)
    for k in hits: out.update(region_parents(k))
    return _ordered(out)

_AREA_TO_REGION = {
 "bullhead city": "bullhead-city", "bullhead": "bullhead-city", "laughlin": "laughlin", "mohave valley": "mohave-valley", "mojave valley": "mohave-valley",
 "fort mohave": "mohave-valley", "fort mojave": "mohave-valley", "mohave county": "mohave-county", "lake havasu city": "lake-havasu-city", "lake havasu": "lake-havasu-city",
 "havasu": "lake-havasu-city", "kingman": "kingman", "golden valley": "kingman", "clark county": "clark-county", "henderson": "henderson", "mesquite": "mesquite",
 "boulder city": "boulder-city", "las vegas": "las-vegas", "north las vegas": "north-las-vegas", "lake mead": "lake-mead", "hoover dam": "lake-mead",
 "searchlight": "laughlin", "needles": "needles", "colorado river": "colorado-river", "las vegas valley": "las-vegas-valley", "southern nevada": "las-vegas-valley",
 "nevada": "nevada", "arizona": "arizona", "utah": "utah", "northern arizona": "northern-arizona", "st. george": "utah-dixie", "st george": "utah-dixie",
 "moapa valley": "mesquite", "overton": "mesquite", "logandale": "mesquite", "bunkerville": "mesquite", "example": None, "": None,
}

def area_to_region(area):
    """Region key for a press-release `area:` value ("Mojave Valley" -> mohave-valley); falls back to detect_regions
    on the string (most specific hit); None when nothing matches."""
    a = re.sub(r"\s+", " ", str(area or "")).strip().lower().rstrip(".")
    a = re.sub(r",?\s*(?:nv|az|ca|ut|nevada|arizona|california|utah)$", "", a).strip()
    if a in _AREA_TO_REGION: return _AREA_TO_REGION[a]
    hits = detect_regions(str(area or ""))
    direct = [k for k in hits if REGION_RX[k].search(str(area))]
    return (direct or hits or [None])[0]

def region_name(key, with_state=False):
    r = REGIONS.get(key)
    if not r: return str(key or "").replace("-", " ").title()
    return f"{r['name']}, {r['state']}" if with_state and r.get("state") and r["kind"] not in ("state", "river") else r["name"]

def home_region(regions):
    """The most specific home region among a list of keys (REGIONS order), or None."""
    for k in _ordered(regions or []):
        if k in HOME_REGIONS: return k
    return None

# ====================================================================== 7. TOPICS
TOPICS = OrderedDict([
 ("energy", {"name": "Energy & Oil", "color": "energy", "intro": "Oil and gas prices, OPEC, pipelines and tankers, utilities and the power that data centers and the desert Southwest run on, including Mohave Electric and NV Energy.",
             "projects": ["oil"], "rx": r"\b(?:oil|crude|OPEC|Brent|WTI|LNG|natural gas|pipeline|refiner\w*|tanker|Hormuz|EIA\b|utility|power plant|grid|solar|wind (?:farm|power)|nuclear|data center.*power|electric(?:ity)? rates?|Mohave Electric|NV Energy|Arizona Public Service|UniSource)"}),
 ("realestate", {"name": "Real Estate & Housing", "color": "realestate", "intro": "Home prices and sales, mortgages, rents, development and zoning, from the national housing market to the subdivisions rising along the Colorado River.",
                 "projects": ["realestate"], "rx": r"\b(?:real estate|housing|home (?:sales|prices)|homebuyers?|mortgage(?:s| rates)?|realtor|rent(?:s|al)?|landlord|apartments?|homebuilder|HOA|foreclosure|trustee sale|zoning|subdivision|affordable housing)"}),
 ("smallbiz", {"name": "Small Business", "color": "smallbiz", "intro": "Main Street economics: owners, startups, franchises, chambers of commerce, the SBA and the grand openings and closings that change a town.",
               "projects": ["smallbiz"], "rx": r"\b(?:small business(?:es)?|entrepreneur|startup|franchise|main street|shop local|chamber of commerce|SBA\b|ribbon cutting|grand opening)"}),
 ("fed", {"name": "Economy & Fed", "color": "economy", "intro": "The Federal Reserve, interest rates, inflation and jobs: the numbers and decisions behind mortgage rates, savings yields and the cost of living.",
          "projects": ["fed"], "rx": r"\b(?:Federal Reserve|the Fed\b|FOMC|rate (?:hike|cut)s?|Powell|Hammack|Fed'?s? (?:Williams|Cook|Waller|Bowman|Jefferson)|interest rates?|inflation|CPI|jobs report|payrolls)"}),
 ("ai", {"name": "Artificial Intelligence", "color": "tech", "intro": "Large language models, chips, data centers and the companies racing to build them, plus what AI means for work, schools and the power grid.",
         "projects": ["ai"], "rx": r"\b(?:AI\b|artificial intelligence|LLM|ChatGPT|OpenAI|Anthropic|Claude|Gemini|Nvidia|machine learning|Ollama|llama\.cpp|MLX|Mac Studio|Apple silicon|M\d (?:Max|Pro|Ultra))"}),
 ("cannabis", {"name": "Cannabis", "color": "health", "intro": "Nevada and Arizona's legal cannabis industries, dispensaries, regulation and federal rescheduling.",
               "projects": ["cannabis"], "rx": r"\b(?:cannabis|marijuana|hemp|THC|dispensar(?:y|ies)|CBD|rescheduling)"}),
 ("golf", {"name": "Golf", "color": "sports", "intro": "The PGA Tour, LIV Golf, the majors and the desert courses of Mesquite, Laughlin and Lake Havasu.",
           "projects": ["golf"], "rx": r"\b(?:golf|PGA|LIV\b|Ryder Cup|LPGA|Korn Ferry|DP World Tour)"}),
 ("media", {"name": "Media & Journalism", "color": "opinion", "intro": "Newsrooms, press freedom, disinformation and the business of local news.",
            "projects": ["media"], "rx": r"\b(?:journalis(?:m|ts?)|newsroom|newspaper|press freedom|disinformation|propaganda|misinformation|Sinclair|local news|libel|defamation|press secretary|media ban)"}),
 ("crypto", {"name": "Crypto", "color": "markets", "intro": "Bitcoin, Ethereum, stablecoins and the regulation of digital assets.",
             "projects": [], "rx": r"\b(?:bitcoin|crypto|Ethereum|XRP|Solana|stablecoin|blockchain|BTC|ETH\b)"}),
 ("scotus", {"name": "Supreme Court", "color": "politics", "intro": "The U.S. Supreme Court's docket, arguments and rulings.",
             "projects": [], "rx": r"\b(?:Supreme Court|SCOTUS|justices?)"}),
 ("elections", {"name": "Elections 2026", "color": "politics", "intro": "The Nov. 3 midterms, Nevada's ballot questions, Mohave and Clark County races and early voting.",
                "projects": [], "rx": r"\b(?:election|ballot|voters?|early voting|midterms?|campaign|candidate|polls?|redistricting)"}),
 ("water", {"name": "Colorado River & Water", "color": "local", "intro": "The river's flows and shortages, Lake Mead and Lake Powell, Reclamation, the seven-state negotiations and local water agencies.",
            "projects": [], "rx": r"\b(?:Colorado River|Lake Mead|Lake Powell|Lake Mohave|water (?:rights|allocation|shortage|cuts|conservation)|drought|Bureau of Reclamation|SNWA|groundwater|aquifer)"}),
 ("public-safety", {"name": "Public Safety", "color": "crime", "intro": "Police, sheriffs, fire departments, crashes, wildfires and emergencies.",
                    "projects": [], "rx": r"\b(?:police|sheriff|fire department|firefighters|crash|shooting|arrest|wildfire|flood|evacuat\w*|missing)"}),
 ("education", {"name": "Schools & Education", "color": "education", "intro": "School districts, colleges and universities, from CCSD to Mohave Community College.",
                "projects": [], "rx": r"\b(?:school district|CCSD|students?|teachers?|university|UNLV|college|campus|tuition)"}),
 ("tourism-gaming", {"name": "Tourism & Gaming", "color": "business", "intro": "Casinos, resorts, visitor numbers and gaming revenue on the Strip and along the river.",
                     "projects": [], "rx": r"\b(?:casino|resort|the Strip|tourism|LVCVA|visitors?|gaming revenue|hotel|convention|sportsbook|prediction markets?)"}),
 ("defense", {"name": "Defense", "color": "world", "intro": "The Pentagon, the services, weapons and wars.",
              "projects": [], "rx": r"\b(?:Pentagon|Department of War|Army|Navy|Air Force|troops|missile|drone|NATO|Hegseth)"}),
 ("foreign-policy", {"name": "Foreign Policy", "color": "world", "intro": "Diplomacy, sanctions and the State Department.", "projects": ["foreign"], "rx": None}),
 ("government", {"name": "Government & Civic", "color": "politics", "intro": "Congress, agencies, transparency and the federal workforce.", "projects": ["civic"], "rx": None}),
])
TOPIC_RX = {k: re.compile(v["rx"], re.I) for k, v in TOPICS.items() if v.get("rx")}
PROJECT_TOPIC = {p: k for k, v in TOPICS.items() for p in v.get("projects") or []}

def detect_topics(item):
    """Topic hub keys for an item from tracker projects and vocabulary over title + summary."""
    text = f"{item.get('title') or ''} {_text(item.get('summary'))[:300]}"
    topics = {PROJECT_TOPIC[p] for p in (item.get("projects") or []) if p in PROJECT_TOPIC}
    topics |= {k for k, rx in TOPIC_RX.items() if rx.search(text)}
    return [k for k in TOPICS if k in topics]

# ====================================================================== 8. SUMMARIES
_BOILER = [
 _rx(r"The post\b.*?\bappeared first on\b.*?(?:\.|$)"), _rx(r"\bappeared first on\b.*$"), _rx(r"\bThis (?:article|story|post) (?:was )?(?:originally )?(?:appeared|published)\b.*$"),
 _rx(r"\b(?:Continue reading|Read more|Read the full (?:story|article)|Click here to read|Read the rest|Full story)\b.*$"), _rx(r"\[(?:…|\.\.\.|&hellip;)\]"), _rx(r"\(Read more\)"),
 _rx(r"^Article URL:.*$"), _rx(r"Comments URL:.*$"), _rx(r"\bPoints:\s*\d+.*$"), _rx(r"^\s*#?\s*Comments\s*$"), _rx(r"submitted by /u/\S+.*$"), _rx(r"\[link\]\s*\[comments\]"),
 _rx(r"<\s*\|\s*Archive\s*\|.*?\|\s*>"), _rx(r"(?:\|\s*)?(?:Archive|Submissions|Index|Search|Calendar|RSS|Education|About APOD|Discuss)\s*(?:\||>|$)"), _rx(r"^APOD:\s*\d{4} \w+ \d{1,2}\s*[-–]\s*"), _rx(r"(?:^|\s)Explanation:\s*"),
 _rx(r"\bImage Credit(?: & Copyright)?:.*$"), _rx(r"\bSign up for\b[^.]*newsletter[^.]*\.?"), _rx(r"\bSubscribe to\b[^.]*\.$"), _rx(r"\bFollow us on\b.*$"),
]
_TRAILING_PUB = _rx(r"\s+[-–—|]\s+[A-Z][\w.&' -]{1,40}$", 0)

def clean_summary(title, summary, limit=420):
    """Feed summary without boilerplate: HTML, "The post … appeared first on …", "Continue reading", "Read more", […],
    Hacker News "Comments", APOD navigation, trailing publisher names. Returns "" when the summary only repeats the title
    or has fewer than 40 characters of real content; a summary that starts with the title keeps the remainder."""
    s = _text(summary)
    if not s: return ""
    for rx in _BOILER: s = rx.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—|…·")
    t = _text(title)
    if t:
        tn = re.sub(r"\W+", " ", t.lower()).strip()
        sn = re.sub(r"\W+", " ", s.lower()).strip()
        if sn == tn or sn.rstrip(".") == tn: return ""
        if sn.startswith(tn):
            s = s[len(t):].lstrip(" .:-–—|") if s.lower().startswith(t.lower()) else re.sub(r"^\W*" + r"\W+".join(map(re.escape, t.split())) + r"\W*", "", s, flags=re.I)
    m = _TRAILING_PUB.search(s)
    if m and s[:m.start()].count(" ") >= 6 and len(m.group(0).split()) <= 5 and not re.search(r"\b(?:and|or|to|of|the|a|in|for|with|by)\s*$", s[:m.start()], re.I):
        s = s[:m.start()].rstrip()   # "… full story. - The Verge" / "… | CNBC"
    s = s.strip(" -–—|…·")
    if len(re.sub(r"[^A-Za-z0-9À-ÿ]", "", s)) < 40: return ""
    if limit and len(s) > limit: s = s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-–") + "…"
    return s

# ====================================================================== 9. RANKING AND CLUSTERS
_TIER_W = {1: 1.0, 2: 0.9, 3: 0.75, 4: 0.55, 5: 0.0}
_OPINION = {"opinion", "column", "editorial", "analysis", "letter", "cartoon", "commentary", "review"}

def score(item, now_ts, cluster_size=1):
    """Homepage lead/top score (higher is better, deterministic): recency, publisher tier, real summary, keyword-matched
    photo, cluster size, local/state boost, minus demotion, opinion, question headline, long title; small section prior."""
    now_ts = int(now_ts if now_ts is not None else dt.datetime.now(dt.timezone.utc).timestamp())
    age_h = max(0.0, (now_ts - int(item.get("ts") or now_ts)) / 3600)
    recency = math.exp(-age_h / 9.0)
    tier = item.get("tier") or (item.get("publisher") or {}).get("tier") or 4
    s = 40 * recency + 25 * _TIER_W.get(int(tier), 0.55)
    s += 12 if item.get("summary") else 0
    s += 6 if item.get("has_photo") else 0
    s += 8 * min(max(cluster_size, item.get("cluster_size") or 1) - 1, 4) / 4
    sec = item.get("section") or item.get("cat") or "us"
    if item.get("local"): s += 12 if sec == "sports" else 30
    elif item.get("state_local") or (set(item.get("regions") or []) & STATE_REGIONS): s += 12
    if item.get("via") == "direct": s += 4
    if "water" in (item.get("topics") or []): s += 8
    if item.get("demoted") or (item.get("quality") is not None and item["quality"] < 1): s -= 15
    if (item.get("label") or item.get("kind")) in _OPINION: s -= 10
    if item.get("lang") not in (None, "en"): s -= 20
    title = item.get("title") or ""
    if title.rstrip().endswith("?"): s -= 8
    if len(title) > 120: s -= 6
    s += {"us": 4, "world": 3, "politics": 3, "business": 2, "markets": 0, "tech": 1, "science": 2, "sports": 0, "local": 2}.get(sec, 0)
    return round(s, 2)

def rank(items, now_ts=None, reps_only=False):
    """Items sorted by score desc (ties: newer first). reps_only=True keeps one representative per cluster."""
    now_ts = int(now_ts if now_ts is not None else dt.datetime.now(dt.timezone.utc).timestamp())
    out = [i for i in items if not reps_only or i.get("cluster_rep", True)]
    return sorted(out, key=lambda i: (-(i.get("score") if i.get("score") is not None else score(i, now_ts)), -(i.get("ts") or 0)))

_CL_STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "at", "by", "with", "from", "as", "is", "are", "be", "this", "that", "it", "its",
            "after", "over", "amid", "says", "said", "new", "us", "u.s", "how", "why", "what", "who", "will", "has", "have", "his", "her", "their", "into", "about"}

def _tokens(title):
    return {w for w in re.findall(r"[a-z0-9']+", str(title or "").lower()) if w not in _CL_STOP and len(w) > 2}

def cluster_key(title):
    """Coarse exact-duplicate key: first six sorted content tokens of the title."""
    toks = sorted(w for w in _tokens(title) if len(w) > 3)
    return " ".join(toks[:6])

def cluster(items, threshold=0.6):
    """Group same-day near-duplicates (Jaccard >= threshold on title tokens, or identical cluster_key) and attach
    item["also"] = other members, item["cluster"] = key, item["cluster_size"], item["cluster_rep"] (best score).
    Returns {cluster key: [items]}."""
    parent = list(range(len(items)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[max(ra, rb)] = min(ra, rb)
    toks = [_tokens(i.get("title")) for i in items]
    days = [dt.datetime.fromtimestamp(int(i.get("ts") or 0), dt.timezone.utc).date() for i in items]
    by_key = {}
    for n, i in enumerate(items):
        k = cluster_key(i.get("title"))
        if k: by_key.setdefault((days[n], k), []).append(n)
    for group in by_key.values():
        for n in group[1:]: union(group[0], n)
    index = {}
    for n, ts in enumerate(toks):
        for w in ts: index.setdefault((days[n], w), []).append(n)
    seen = set()
    for n, ts in enumerate(toks):
        if len(ts) < 3: continue
        cands = set()
        for w in ts: cands.update(index.get((days[n], w), ()))
        for m in cands:
            if m <= n or (n, m) in seen: continue
            seen.add((n, m))
            inter = len(ts & toks[m])
            if inter and inter / len(ts | toks[m]) >= threshold: union(n, m)
    groups = {}
    for n in range(len(items)): groups.setdefault(find(n), []).append(n)
    out = {}
    for root, members in groups.items():
        lst = [items[m] for m in members]
        key = cluster_key(items[root].get("title")) or (items[root].get("id") or str(root))
        key = f"{days[root].isoformat()}:{key}"
        best = max(lst, key=lambda i: (i.get("score") or 0, i.get("tier") and -i["tier"] or 0, i.get("ts") or 0))
        for i in lst:
            i["also"] = [o for o in lst if o is not i]
            i["cluster"] = key; i["cluster_size"] = len(lst); i["cluster_rep"] = i is best
        out[key] = lst
    return out

# ====================================================================== 10. PER-ITEM PIPELINE
def process(item, now_ts=None):
    """normalize_title -> publisher -> clean_summary -> lang -> quality -> detect_regions -> categorize -> topics -> score.
    Returns a NEW dict with the annotations feed.load_items promises (title, title_pub, label, publisher, tier, paywalled,
    summary, lang, keep, quality, demoted, quality_reasons, regions, local, state_local, region, section, cat, rule,
    topics, score). Does not touch id/slug/ts/date/kind/also (feed owns those)."""
    it = dict(item)
    now_ts = int(now_ts if now_ts is not None else dt.datetime.now(dt.timezone.utc).timestamp())
    src = str(it.get("source") or "")
    raw_title = it.get("title") or ""
    if it.get("via") == "direct":
        title, title_pub, label = _text(raw_title), None, normalize_title_full(raw_title, "")[2]
        title = title_case_if_caps(title)
    else:
        title, title_pub, label = normalize_title_full(raw_title, src)
    it.update(title=title, title_pub=title_pub, label=label)
    pub = publisher(it)
    it["publisher"] = pub; it["tier"] = pub["tier"]; it["paywalled"] = bool(pub.get("paywalled"))
    it["source"] = pub["name"]
    raw_summary = _text(it.get("summary"))
    it["lang"] = lang({"title": title, "summary": raw_summary})
    text = f"{title} {raw_summary[:400]}"
    regions = list(it.get("regions") or [])
    regions += detect_regions(text, pub["name"] if pub.get("via") in ("direct", "google_news") else src)
    for k in list(regions): regions += region_parents(k)
    it["regions"] = _ordered(k for k in regions if k in REGIONS)
    it["local"] = bool(HOME_REGIONS & set(it["regions"]))
    it["state_local"] = (not it["local"]) and bool(STATE_REGIONS & set(it["regions"]))
    given = [k for k in (item.get("regions") or []) if k in HOME_REGIONS]   # a direct feed's own region wins over text order
    it["region"] = (item.get("region") if item.get("region") in HOME_REGIONS else None) or (given[0] if given else None) or home_region(it["regions"])
    keep, q, reasons = quality({**it, "summary": raw_summary}, pub)
    it["keep"] = keep; it["quality"] = q; it["demoted"] = q < 1.0; it["quality_reasons"] = reasons
    it["summary"] = clean_summary(title, raw_summary)
    sec, rule = categorize_rule({**it, "summary": raw_summary}, pub)
    it["section"] = sec if sec in CAT_NAME else "us"; it["rule"] = rule
    it["cat"] = "local" if (it.get("via") == "direct" or it.get("cat") == "local") else it["section"]
    it["topics"] = detect_topics({**it, "summary": raw_summary})
    it["score"] = score(it, now_ts)
    return it
