#!/usr/bin/env python3
"""Ground Level News static site builder.
Pulls news-tracker data (plus regional feeds) and renders HTML into _site/.
The generator lives in scripts/gln/; this file only orchestrates.
Env: TRACKER_BASE (URL or local dir), OUT_DIR, SITE_URL, CONTACT_EMAIL, OG_STORIES, SOURCES_DISABLED=1, MIN_ITEMS."""
import os, shutil, sys, time, pathlib, types, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from gln import config, images
from gln.config import ROOT, OUT, BLOCK, CATS, CAT_NAME
from gln.text import esc
from gln.feed import load_items, load_prs
from gln.pages import render_all
from gln.llm_layer import render_llm_pages
from gln.seo import render_feeds


def optional(modname, attr):
    """Import gln.<modname>.<attr> if the module exists and exposes it; None otherwise (modules land independently)."""
    try:
        return getattr(importlib.import_module(f"gln.{modname}"), attr, None)
    except ImportError as e:
        print(f"note: gln.{modname} not available ({e})", file=sys.stderr); return None


def timed(label, fn, *a, **kw):
    t = time.time(); r = fn(*a, **kw); print(f"  {label}: {time.time() - t:.1f}s"); return r


def build_context():
    items, man = load_items()
    images.IMG_CFG = images.load_images()
    prs = load_prs()
    real_prs = [p for p in prs if not p.get("example")]
    print(f"items={len(items)} originals={len(real_prs)} (+{len(prs) - len(real_prs)} example)")
    by = {k: [] for k in CAT_NAME}
    for i in items:
        by.setdefault(i["cat"], []).append(i)
        if i.get("local") and i["cat"] != "local": by["local"].append(i)
    # Legacy ticker string (the new shell renders a static "Just in" strip from c.items instead; kept for back-compat).
    ticker = "".join(f'<a href="/story/{i["slug"]}/"><b>{esc(CAT_NAME.get("local" if i.get("local") else i["cat"]))}</b>{esc(i["title"])}</a>' for i in items[:25])
    c = types.SimpleNamespace(items=items, man=man, prs=prs, real_prs=real_prs, originals=real_prs, ticker=ticker, by=by, urls=[], conditions={})
    fetch_conditions = optional("conditions", "fetch_conditions")
    if fetch_conditions and os.environ.get("SOURCES_DISABLED") != "1":
        try: c.conditions = timed("conditions", fetch_conditions) or {}
        except Exception as e: print(f"WARN conditions: {e}", file=sys.stderr)
    return c


def main():
    t0 = time.time()
    if OUT.exists(): shutil.rmtree(OUT)
    shutil.copytree(ROOT/"static", OUT)
    c = build_context()
    write_conditions = optional("conditions", "write_conditions")
    if write_conditions and c.conditions:
        try: write_conditions(OUT, c.conditions) if write_conditions.__code__.co_argcount >= 2 else write_conditions(OUT)
        except Exception as e: print(f"WARN conditions.json: {e}", file=sys.stderr)
    timed("pages", render_all, c)
    render_local = optional("local", "render_local")
    if render_local: timed("local", render_local, c)
    render_editorial = optional("editorial", "render_editorial")
    if render_editorial: timed("editorial", render_editorial, c)
    timed("llm layer", render_llm_pages, c)
    urls = timed("feeds", render_feeds, c)
    hits = [str(f.relative_to(OUT)) for f in OUT.rglob("*") if f.is_file() and f.suffix in {".html", ".md", ".txt", ".xml", ".json", ".webmanifest", ".ics"}
            and BLOCK.search(f.read_text(encoding="utf-8", errors="ignore"))]
    if hits: sys.exit(f"ERROR: blocked name found in {len(hits)} file(s): {hits[:10]}")
    print(f"built {len(urls)} pages in {time.time() - t0:.1f}s")


if __name__ == "__main__": main()
