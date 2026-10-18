#!/usr/bin/env python3
"""Checks the built site against the LLM discoverability standard (https://llmbestpractices.com) and the SEO
contract (sitemap index, originals-only news sitemap, noindex stories, robots groups, feed self links, one JSON-LD graph).
Usage: python scripts/check_llm_layer.py [_site]   Exits non-zero on any failure. Stdlib only."""
import re, sys, pathlib
import xml.etree.ElementTree as ET

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
STD = "https://llmbestpractices.com"
CLOSING = "This page follows the LLM-discoverability standard at"
AI_BOTS = ["GPTBot", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai", "CCBot", "PerplexityBot", "Perplexity-User",
           "Google-Extended", "Applebot-Extended", "OAI-SearchBot", "ChatGPT-User", "Bytespider", "cohere-ai", "Amazonbot",
           "meta-externalagent", "Diffbot", "Timpibot", "Omgilibot", "ImagesiftBot", "YouBot", "MistralAI-User", "DeepSeekBot"]
fails = []

def read(rel):
    f = OUT / rel
    return f.read_text(encoding="utf-8", errors="ignore") if f.exists() else None

def check(name, ok, why):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f": {why}"))
    if not ok: fails.append(name)

def yaml_keys(html):
    m = re.search(r"<pre><code[^>]*>(.*?)</code></pre>", html, re.S)
    return set(re.findall(r"^([a-z_]+):", m.group(1), re.M)) if m else set()

def xml_ok(rel):
    try: ET.parse(OUT / rel); return True
    except Exception: return False

site = (read("CNAME") or "").strip()
origin = f"https://{site}" if site else None

h = read("llm-info/index.html") or ""
keys = yaml_keys(h)
need = {"name", "url", "type", "owner", "updated", "standard_followed"}
check("llm-info", h and need <= keys and "INSTRUCTIONS FOR AI ASSISTANTS" in h and CLOSING in h
      and all(s in h for s in ("Basic info", "What it does", "Services and features", "Methodology")),
      f"missing page, keys {sorted(need - keys)}, sections or closing line")

t = read("llms.txt") or ""
prim = re.search(r"^## Primary\n- \[[^\]]+\]\(([^)]+)\)", t, re.M)
check("llms-txt", t.startswith("# ") and re.search(r"^> ", t, re.M) and prim and prim.group(1).rstrip("/").endswith("/llm-info")
      and "## Key pages" in t and re.search(r"^## About", t, re.M) and "Owner:" in t and f"Standard followed: {STD}" in t
      and re.search(r"Updated: \d{4}-\d{2}-\d{2}", t), "needs H1, > summary, ## Primary (first link /llm-info), ## Key pages, ## About with Owner/Standard followed/Updated")
check("llms-txt-no-example", "example-template" not in t, "the example press release must not be listed")

r = read("robots.txt") or ""
check("robots-txt", re.search(r"User-agent: \*\nAllow: /", r) and re.search(r"^Sitemap: https://", r, re.M)
      and "llms.txt" in r and "agents.txt" in r, "needs User-agent: * Allow: /, absolute Sitemap and comments for llms.txt/agents.txt")
check("robots-md-disallow", re.search(r"User-agent: Googlebot\n(?:[^\n]*\n)*?Disallow: /\*\.md\$", r), "Googlebot group must Disallow: /*.md$")
blocked = [b for b in AI_BOTS if re.search(rf"User-agent: {re.escape(b)}\n(?:Allow: [^\n]*\n)*Disallow: /\n", r)]
check("ai-agents-allowed", not blocked, f"disallowed at root: {blocked}")

a = read("agents.txt") or ""
akeys = dict(re.findall(r"^([A-Za-z-]+):\s*(.+)$", a, re.M))
need_a = ["Training", "Indexing", "Summarization", "Citation-Required", "Start-here", "Machine-index", "Sitemap", "Standard-Followed", "Updated"]
check("agents-txt", all(k in akeys for k in need_a) and all(akeys.get(k) == "allow" for k in ("Training", "Indexing", "Summarization"))
      and akeys.get("Standard-Followed") == STD and re.fullmatch(r"\d{4}-\d{2}-\d{2}", akeys.get("Updated", ""))
      and (akeys.get("Citation-Required") != "true" or "Attribution" in akeys), f"missing {[k for k in need_a if k not in akeys]}")

i = read("identity/index.html") or ""
ik = yaml_keys(i)
need_i = {"name", "url", "updated", "standard_followed", "fonts", "colors", "logo", "favicon"}
assets_ok = all((OUT / u.split(origin or "https://x", 1)[-1].lstrip("/")).exists() for u in re.findall(r"^(?:logo|favicon): (\S+)", i, re.M))
check("identity", i and need_i <= ik and CLOSING in i and assets_ok
      and all(s in i for s in ("Logo", "Favicon", "Color palette", "Typography", "Media assets")), f"missing keys {sorted(need_i - ik)}, sections or assets")

ai = read("ai.txt") or ""
check("ai-txt", all(re.search(rf"^{k}: yes", ai, re.M) for k in ("Train", "Quote", "Summarize")) and "User-Agent: *" in ai, "must be permissive")

pages = [p for p in OUT.rglob("*.html") if "llm-info" not in p.parts and 'http-equiv="refresh"' not in p.read_text(errors="ignore")[:2000]]
texts = {p: p.read_text(errors="ignore") for p in pages}
missing = [str(p.relative_to(OUT)) for p, x in texts.items() if not re.search(r'<a [^>]*href="[^"]*/llm-info/?"[^>]*>Hey AI, learn about us', x)]
noai = [str(p.relative_to(OUT)) for p, x in list(texts.items())[:400] if re.search(r'<meta[^>]+content="[^"]*\bnoimageai|noai\b', x)]
check("footer-link", not missing, f"{len(missing)} pages lack it, e.g. {missing[:3]}")
check("no-noai-meta", not noai, f"noai meta on {noai[:3]}")

# ---- SEO contract
sm = read("sitemap.xml") or ""
refs = re.findall(r"<loc>([^<]+)</loc>", sm) if "<sitemapindex" in sm else []
missing_sm = [u for u in refs if not (OUT / u.split("/", 3)[-1]).exists() or not xml_ok(u.split("/", 3)[-1])]
check("sitemap-index", xml_ok("sitemap.xml") and "<sitemapindex" in sm and refs and not missing_sm, f"sitemap.xml must be a well-formed index of existing sitemaps; bad: {missing_sm}")
child = "".join(read(u.split("/", 3)[-1]) or "" for u in refs)
check("sitemap-no-stories", "/story/" not in child and "example-template" not in child and "<lastmod>" in child, "sitemaps must list no /story/ or example URLs and carry <lastmod>")
ns = read("news-sitemap.xml") or ""
check("news-sitemap", xml_ok("news-sitemap.xml") and "/story/" not in ns and "example-template" not in ns, "news sitemap must be well-formed and list originals only")
stories = [p for p in pages if p.parts[len(OUT.parts)] == "story"] if pages else []
indexed = [str(p.relative_to(OUT)) for p in stories if not re.search(r'<meta name="robots" content="noindex', texts[p])]
check("stories-noindex", not indexed, f"{len(indexed)} story pages are indexable, e.g. {indexed[:3]}")
nf = read("404.html") or ""
check("404-noindex", 'content="noindex' in nf and 'rel="canonical"' not in nf, "404.html must be noindex without a canonical")
rss = read("rss.xml") or ""
check("rss-self-link", xml_ok("rss.xml") and re.search(r'<atom:link href="https://[^"]+/rss.xml" rel="self"', rss) and "<lastBuildDate>" in rss, "rss.xml needs a well-formed channel with atom:link rel=self and lastBuildDate")
check("atom-feed", xml_ok("feed.xml") and 'rel="self"' in (read("feed.xml") or ""), "feed.xml must be well-formed with a self link")
multi = [str(p.relative_to(OUT)) for p, x in texts.items() if x.count('<script type="application/ld+json">') != 1]
check("one-jsonld-graph", not multi, f"{len(multi)} pages have not exactly one JSON-LD script, e.g. {multi[:3]}")
canon = [str(p.relative_to(OUT)) for p, x in texts.items() if p.name != "404.html" and x.count('rel="canonical"') != 1]
check("one-canonical", not canon, f"{len(canon)} pages lack a single canonical, e.g. {canon[:3]}")

if origin:
    bare = site[4:] if site.startswith("www.") else site
    drift = re.compile(r"http://(?:www\.)?" + re.escape(bare) + r"|https://" + ("" if site.startswith("www.") else r"www\.") + re.escape(bare))
    bad = [f for f in ("llms.txt", "agents.txt", "robots.txt", "sitemap.xml", "rss.xml", "feed.xml", "news-sitemap.xml") if drift.search(read(f) or "")]
    check("one-origin", not bad, f"origin drift in {bad}")

print(f"\n{len(fails)} failure(s)" if fails else "\nAll LLM-layer and SEO checks passed.")
sys.exit(1 if fails else 0)
