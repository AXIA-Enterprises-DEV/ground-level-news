"""Everything inside <head>: meta tags, Open Graph, feeds, icons, JSON-LD. Owned by SEO."""
import json
from .config import SITE, NAME, TAG
from .text import esc

ORG = {"@type":"NewsMediaOrganization","@id":SITE+"/#org","name":NAME,"url":SITE+"/","logo":{"@type":"ImageObject","url":SITE+"/img/logo.png","width":297,"height":180},
       "publishingPrinciples":SITE+"/about/"}
SITE_LD = json.dumps({"@context":"https://schema.org","@graph":[ORG,{"@type":"WebSite","@id":SITE+"/#website","url":SITE+"/","name":NAME,"description":TAG,"publisher":{"@id":SITE+"/#org"},"inLanguage":"en-US"}]}).replace("</","<\\/")

def ldj(o): return f'<script type="application/ld+json">{json.dumps(o).replace("</","<\\/")}</script>'
def crumbs(*pairs): return {"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":n+1,"name":a,"item":SITE+b} for n,(a,b) in enumerate(pairs)]}
def absimg(im): return (SITE + im["src"]) if im and im["src"].startswith("/") else (im or {}).get("src")

def head(title, desc=TAG, path="/", og_type="website", extra_head="", og_img=None, md=None):
    """Return the inner HTML of <head> for a page."""
    full = f"{esc(title)} | {NAME}" if title != NAME else f"{NAME} | {TAG}"
    url = SITE + path
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{full}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}"><meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}"><meta property="og:type" content="{og_type}">
<meta property="og:image" content="{og_img or SITE + "/og.png"}"><meta property="og:image:alt" content="{NAME}"><meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#ffffff">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"><link rel="icon" type="image/png" sizes="512x512" href="/icon-512.png"><link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"><meta name="twitter:image" content="{og_img or SITE + "/og.png"}">
<link rel="alternate" type="application/rss+xml" title="{NAME} RSS" href="/rss.xml"><link rel="alternate" type="application/atom+xml" title="{NAME} Atom" href="/feed.xml">{f'<link rel="alternate" type="text/markdown" href="{md}">' if md else ''}<link rel="help" type="text/plain" href="/llms.txt" title="llms.txt">
<meta name="twitter:title" content="{esc(title)}"><meta name="twitter:description" content="{esc(desc)}"><meta name="robots" content="index,follow,max-image-preview:large">
<script type="application/ld+json">{SITE_LD}</script>
<link rel="preload" href="/fonts/outfit.woff2" as="font" type="font/woff2" crossorigin><link rel="preload" href="/fonts/jakarta.woff2" as="font" type="font/woff2" crossorigin>
<link rel="manifest" href="/site.webmanifest"><meta name="color-scheme" content="light"><meta name="format-detection" content="telephone=no">
<link rel="stylesheet" href="/style.css"><script>document.documentElement.classList.add("js")</script>{extra_head}"""
