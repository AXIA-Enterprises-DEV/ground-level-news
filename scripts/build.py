#!/usr/bin/env python3
"""Ground Level News static site builder.
Pulls news-tracker data from its GitHub Pages URL, renders HTML into _site/.
The generator lives in scripts/gln/; this file only orchestrates."""
import shutil, sys, pathlib, types
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gln import config, images
from gln.config import ROOT, OUT, BLOCK, CATS, CAT_NAME
from gln.text import esc
from gln.feed import load_items, load_prs
from gln.pages import render_all
from gln.llm_layer import render_llm_pages
from gln.seo import render_feeds


def build_context():
    items, man = load_items()
    images.IMG_CFG = images.load_images()
    prs = load_prs()
    print(f"items={len(items)} press_releases={len(prs)}")
    tick_syms = [t for t in (man.get("tickers") or [])][:30]
    ticker = "".join(f'<a href="/story/{i["slug"]}/"><b>{esc(CAT_NAME.get("local" if i.get("local") else i["cat"]))}</b>{esc(i["title"])}</a>' for i in items[:25])
    if tick_syms: ticker += '<span class="syms">TRENDING TICKERS: ' + " ".join(f'<em>${esc(t)}</em>' for t in tick_syms) + "</span>"
    by = {k: [] for k in CAT_NAME}
    for i in items:
        by[i["cat"]].append(i)
        if i.get("local"): by["local"].append(i)
    real_prs = [p for p in prs if not p.get("example")]
    return types.SimpleNamespace(items=items, man=man, prs=prs, real_prs=real_prs, ticker=ticker, by=by)


def main():
    if OUT.exists(): shutil.rmtree(OUT)
    shutil.copytree(ROOT/"static", OUT)
    c = build_context()
    render_all(c)
    render_llm_pages(c)
    urls = render_feeds(c)
    hits = [str(f.relative_to(OUT)) for f in OUT.rglob("*") if f.is_file() and f.suffix in {".html", ".md", ".txt", ".xml", ".json", ".webmanifest"}
            and BLOCK.search(f.read_text(encoding="utf-8", errors="ignore"))]
    if hits: sys.exit(f"ERROR: blocked name found in {len(hits)} file(s): {hits[:10]}")
    print("built", len(urls), "pages")


if __name__ == "__main__": main()
