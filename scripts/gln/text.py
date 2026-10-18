"""Small text helpers: escaping, cleaning, slugs, and the single date formatter used by every page."""
import re, html, datetime as dt
from zoneinfo import ZoneInfo
from .config import NOW, TZ_NAME

TZ = ZoneInfo(TZ_NAME)
_TZ_ABBR = {"MST": "MST", "MDT": "MST"}   # Arizona never observes DST

def esc(s): return html.escape(str(s or ""), quote=True)

def clean(s, n=None):
    s = re.sub(r"<[^>]+>", " ", html.unescape(str(s or "")))
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n: s = s[:n].rsplit(" ", 1)[0].rstrip(" ,;:-–") + "…"
    return s

def slugify(s, n=70):
    """URL slug: lowercase ASCII words joined by hyphens, cut at the last hyphen before `n`, never ending in a hyphen."""
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")
    if len(s) > n:
        cut = s[:n]
        if s[n] != "-" and "-" in cut: cut = cut.rsplit("-", 1)[0]   # cut mid-word: back up to the last hyphen
        s = cut.strip("-")
    return s or "story"

def title_case_if_caps(s):
    """Turn ALL-CAPS wire headlines into Title Case; leave mixed-case titles alone."""
    s = str(s or "")
    letters = [c for c in s if c.isalpha()]
    if len(letters) > 12 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "with"}
        words = s.lower().split(" ")
        out = []
        for i, w in enumerate(words):
            if i and w in small: out.append(w)
            elif re.fullmatch(r"(?:u\.s\.|u\.k\.|u\.n\.|ceo|cfo|ai|nasa|fbi|ice|gop|nfl|nba|mlb|nhl|pga|sec|ipo|etf|usa|eu|uk|us|tv|fda|cdc|doj)\W*", w): out.append(w.upper())
            else: out.append(w[:1].upper() + w[1:])
        return " ".join(out)
    return s

# ---------- dates ----------
def to_ts(v):
    """Coerce an epoch int/float/str, ISO string, date or datetime to an int epoch; None when it cannot be parsed."""
    if v is None or v == "": return None
    if isinstance(v, bool): return None
    if isinstance(v, (int, float)): return int(v) if v > 0 else None
    if isinstance(v, dt.datetime):
        if v.tzinfo is None: v = v.replace(tzinfo=TZ)
        return int(v.timestamp())
    if isinstance(v, dt.date): return int(dt.datetime(v.year, v.month, v.day, 12, tzinfo=TZ).timestamp())
    s = str(v).strip()
    if re.fullmatch(r"-?\d{9,13}(?:\.\d+)?", s):
        f = float(s); f = f / 1000 if f > 1e11 else f
        return int(f) if f > 0 else None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None: d = d.replace(tzinfo=TZ)
    return int(d.timestamp())

def _dt(ts): return dt.datetime.fromtimestamp(int(ts) if ts else NOW.timestamp(), dt.timezone.utc)

def iso(ts):
    """RFC 3339 UTC string (seconds precision) for an epoch; the build time when ts is falsy."""
    return _dt(ts).replace(microsecond=0).isoformat()

def ago(ts):
    if not ts: return ""
    s = int(NOW.timestamp()) - int(ts)
    if s < 3600: return f"{max(1, s // 60)}m ago"
    if s < 86400: return f"{s // 3600}h ago"
    return _dt(ts).astimezone(TZ).strftime("%b %-d")

def fmt_date(v, style="rel"):
    """The single date formatter. `v` is an epoch or ISO string. Styles:
    rel   -> "3h ago" / "Yesterday" / "Oct 14" (local, Arizona time)
    short -> "Oct 14" (adds the year when not the current year)
    long  -> "Oct 14, 2026, 9:47 AM MST"
    iso   -> UTC RFC 3339 (for datetime attributes and feeds)"""
    ts = to_ts(v)
    if ts is None: ts = int(NOW.timestamp())
    if style == "iso": return iso(ts)
    local = _dt(ts).astimezone(TZ); now = NOW.astimezone(TZ)
    if style == "long": return f"{local.strftime('%b %-d, %Y, %-I:%M %p')} {_TZ_ABBR.get(local.strftime('%Z'), 'MST')}"
    if style == "short": return local.strftime("%b %-d") if local.year == now.year else local.strftime("%b %-d, %Y")
    s = int(NOW.timestamp()) - ts
    if s < 3600: return f"{max(1, s // 60)}m ago"
    if s < 86400 and local.date() == now.date(): return f"{s // 3600}h ago"
    if local.date() == (now - dt.timedelta(days=1)).date(): return "Yesterday"
    if s < 86400: return f"{s // 3600}h ago"
    return local.strftime("%b %-d") if local.year == now.year else local.strftime("%b %-d, %Y")

def time_tag(ts, style="rel", est=False, cls=""):
    """<time datetime="UTC"> with the formatted local text; relative times carry data-ts for the client-side refresher
    unless the timestamp is estimated (ts<=0 upstream)."""
    ts = to_ts(ts) or int(NOW.timestamp())
    attrs = f' datetime="{iso(ts)}"'
    if style == "rel" and not est: attrs += f' data-ts="{ts}"'
    if cls: attrs += f' class="{esc(cls)}"'
    return f"<time{attrs}>{esc(fmt_date(ts, style))}</time>"
