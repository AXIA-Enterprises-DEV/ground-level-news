"""Page chrome (header, nav, footer, scripts), cards and grids, share-card hookup, file writing. Owned by UI."""
import os, re, shutil, sys, pathlib
from .config import ROOT, OUT, SITE, BASE, NAME, TAG, CONTACT, NOW, CATS, CAT_NAME, brand
from .text import esc, clean, ago
from .images import story_img, img_tag
from .head import head

def page(title, body, desc=TAG, path="/", ticker="", og_type="website", extra_head="", og_img=None, md=None):
    cur = lambda pre: ' aria-current="page"' if path.startswith(pre) else ""
    nav = "".join(f'<a href="/category/{k}/"{cur(f"/category/{k}/")}>{v}</a>' for k, v in CATS) + f'<a href="/press-releases/" class="pr"{cur("/press-releases/")}>Press Releases</a>'
    return f"""<!doctype html><html lang="en"><head>{head(title, desc, path, og_type, extra_head, og_img, md)}</head><body>
<div class="ticker"><span class="live">LIVE</span><div class="tk-wrap"><div class="tk">{ticker}{ticker}</div></div></div>
<a class="skip" href="#main">Skip to content</a>
<header class="top" id="top"><div class="wrap hdr"><a class="logo" href="/" aria-label="Ground Level News home"><img src="/img/logo-header.webp" alt="Ground Level News" width="191" height="104"></a>
<button class="menu" type="button" aria-controls="site-nav" aria-expanded="false" aria-label="Open menu"><span></span><span></span><span></span></button>
<nav class="nav" id="site-nav" aria-label="Sections">{nav}</nav></div></header>
<main class="wrap" id="main">{body}</main>
<footer class="foot"><div class="wrap">
<div class="fgrid"><div class="fbrand"><a class="flogo" href="/" aria-label="Ground Level News home"><img src="/img/logo.webp" alt="Ground Level News" width="297" height="180" loading="lazy"></a>
<p>{TAG} National headlines from public news feeds, plus local news from Bullhead City, Laughlin, Mohave Valley, Clark County, Mesquite and Boulder City. Every story links to its original publisher.</p>
<a class="btn" href="/submit/">Submit a press release</a></div>
<nav aria-label="Sections"><h2>Sections</h2><ul class="cols2">{"".join(f'<li><a href="/category/{k}/">{v}</a></li>' for k, v in CATS)}<li><a href="/press-releases/">Press Releases</a></li></ul></nav>
<nav aria-label="About"><h2>About</h2><ul><li><a href="/about/">About &amp; Sources</a></li><li><a href="/submit/">Submit a Release</a></li><li><a href="/identity/">Brand &amp; Logo</a></li><li><a href="/accessibility/">Accessibility</a></li><li><a href="mailto:{CONTACT}">Contact</a></li></ul></nav>
<nav aria-label="For AI and developers"><h2>For AI &amp; Developers</h2><ul><li><a href="/llm-info/">LLM info</a></li><li><a href="/llms.txt">llms.txt</a></li><li><a href="/llms-full.txt">llms-full.txt</a></li><li><a href="/agents.txt">agents.txt</a></li><li><a href="/ai.txt">ai.txt</a></li><li><a href="/agents.md">Agent guide</a></li></ul></nav>
<nav aria-label="Feeds"><h2>Feeds</h2><ul><li><a href="/rss.xml">RSS</a></li><li><a href="/feed.xml">Atom</a></li><li><a href="/sitemap.xml">Sitemap</a></li><li><a href="/news-sitemap.xml">News sitemap</a></li></ul></nav></div>
<div class="fbar"><p>© {NOW.year} {NAME} · Updated <time datetime="{NOW.strftime('%Y-%m-%dT%H:%MZ')}">{NOW.strftime('%b %d, %Y %H:%M UTC')}</time></p><a class="heyai" href="/llm-info/">Hey AI, learn about us <span aria-hidden="true">→</span></a></div></div></footer>
<script>document.querySelectorAll('.loadmore').forEach(function(b){{var g=b.parentNode.previousElementSibling,st=+g.dataset.step||9;
function lbl(){{var n=g.querySelectorAll('.more-item').length;if(!n)b.parentNode.remove();else b.textContent='View more ('+n+' more)';}}lbl();
b.addEventListener('click',function(){{var h=[].slice.call(g.querySelectorAll('.more-item'),0,st);h.forEach(function(e){{e.classList.remove('more-item');}});h[0]&&h[0].focus();lbl();}});}});</script>
<script>document.querySelectorAll('[data-ts]').forEach(e=>{{const s=Math.floor(Date.now()/1000)-+e.dataset.ts;e.textContent=s<3600?Math.max(1,s/60|0)+'m ago':s<86400?(s/3600|0)+'h ago':new Date(e.dataset.ts*1000).toLocaleDateString(undefined,{{month:'short',day:'numeric'}})}})</script>
<script>(function(){{var b=document.querySelector('.menu'),n=document.getElementById('site-nav'),t=document.getElementById('top');
function set(o){{document.body.classList.toggle('open',o);b.setAttribute('aria-expanded',o);b.setAttribute('aria-label',o?'Close menu':'Open menu');}}
b.addEventListener('click',function(){{var o=b.getAttribute('aria-expanded')!=='true';set(o);if(o){{var a=n.querySelector('a');a&&a.focus();}}}});
document.addEventListener('keydown',function(e){{if(e.key==='Escape'&&b.getAttribute('aria-expanded')==='true'){{set(false);b.focus();}}}});
n.addEventListener('click',function(e){{if(e.target.closest('a'))set(false);}});
matchMedia('(min-width:901px)').addEventListener('change',function(m){{if(m.matches)set(false);}});
var s=false;addEventListener('scroll',function(){{var c=scrollY>60;if(c!==s){{s=c;t.classList.toggle('compact',c);}}}},{{passive:true}});}})();</script>
</body></html>"""

OG_CACHE = ROOT/".ogcache"
OG_STORIES = int(os.environ.get("OG_STORIES", "300"))
def og_for(slug, title, cat, im=None):
    """Branded 1200x630 share card (over the story photo when there is one), cached by content hash."""
    if not brand: return None
    photo = None
    if im and not im.get("brand") and im["src"].startswith("/"):
        f = ROOT/"static"/im["src"].lstrip("/")
        photo = f if f.exists() else None
    try:
        brand.og_cached(title, cat, OUT/f"og/{slug}.jpg", OG_CACHE, photo, (im or {}).get("credit") if photo else None); return f"{SITE}/og/{slug}.jpg"
    except Exception as e:
        print(f"WARN og {slug}: {e}", file=sys.stderr); return None

def card(it, cls="card"):
    cat = "local" if it.get("local") else it["cat"]
    meta = f'<span class="meta">{esc(it.get("source"))} · <time data-ts="{it["ts"]}">{ago(it["ts"])}</time></span>'
    if cls == "mini":
        return f'<a class="mini" href="/story/{it["slug"]}/"><span class="tag t-{cat}">{esc(CAT_NAME.get(cat))}</span><h3>{esc(it["title"])}</h3>{meta}</a>'
    im = story_img(it)
    return f"""<a class="{cls}" href="/story/{it['slug']}/"><span class="thumb">{img_tag(im, sizes="(max-width:640px) 100vw, (max-width:1000px) 50vw, 400px", small=True)}</span>
<span class="cb"><span class="tag t-{cat}">{esc(CAT_NAME.get(cat))}</span><h3>{esc(it['title'])}</h3>{f'<p>{esc(clean(it["summary"],170))}</p>' if it['summary'] else ''}{meta}</span></a>"""

def grid(cards, show, cls="grid", step=None, label="View more"):
    """A card grid that shows `show` cards; the rest stay in the HTML (for crawlers and no-JS) behind a View more button."""
    step = step or show
    if len(cards) <= show: return f'<div class="{cls}">{"".join(cards)}</div>'
    html = "".join(c if n < show else c.replace('class="card', 'class="card more-item', 1) for n, c in enumerate(cards))
    return f'<div class="{cls}" data-step="{step}">{html}</div><div class="more-wrap"><button class="loadmore" type="button">{label}</button></div>'

def write(path, content):
    f = OUT / path.lstrip("/")
    if path.endswith("/"): f = f / "index.html"
    if BASE: content = re.sub(r'(href|src)="/(?!/)', lambda m: f'{m.group(1)}="{BASE}/', content)
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(content, encoding="utf-8")
