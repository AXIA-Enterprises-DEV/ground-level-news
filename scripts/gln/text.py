"""Small text helpers: escaping, cleaning, slugs, dates."""
import re, html, datetime as dt
from .config import NOW

def esc(s): return html.escape(str(s or ""), quote=True)
def clean(s, n=None):
    s = re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n: s = s[:n].rsplit(" ", 1)[0] + "…"
    return s
def slugify(s): return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:70] or "story"

def ago(ts):
    if not ts: return ""
    s = int(NOW.timestamp()) - ts
    if s < 3600: return f"{max(1, s//60)}m ago"
    if s < 86400: return f"{s//3600}h ago"
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%b %d")

def iso(ts): return dt.datetime.fromtimestamp(ts or NOW.timestamp(), dt.timezone.utc).isoformat()
