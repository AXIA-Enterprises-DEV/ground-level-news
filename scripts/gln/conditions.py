"""River, weather and air-quality conditions for the Colorado River region (DECISIONS.md section 13).

Data: NWS api.weather.gov (points -> gridpoint forecast, active alerts by forecast zone), Open-Meteo US AQI
(no key), USGS instantaneous values for the Colorado and Virgin rivers. Every piece is optional: a failed
call leaves its key missing and pages render without it.

Public API:
    fetch_conditions() -> dict          {"fetched": iso, "cities": {key: {...}}, "alerts": [...], "rivers": [...]}
    write_conditions(out_dir) -> dict   writes <out_dir>/data/conditions.json and returns the dict
    render_strip(cond, region_key=None, limit=14) -> str   compact <ul class="cond"> fragment ("" when empty)
    aqi_label(value) -> str

SOURCES_DISABLED=1 returns {}. When TRACKER_BASE is a local directory (tests, offline builds) the saved
tests/fixtures/feeds/conditions.json is returned instead of hitting the network.
"""
import os, sys, json, time, pathlib, datetime as dt
from concurrent.futures import ThreadPoolExecutor
import requests
from .config import ROOT, SRC
from .text import esc

UA = "GroundLevelNews/1.0 (news@groundlevelnews.com)"
TIMEOUT = 10
FIXTURE = ROOT / "tests/fixtures/feeds/conditions.json"
STALE_HOURS = 48

# Cities: NWS forecast zones (competitive.md section 4) plus the county zone, and taxonomy region keys.
CITIES = [
    {"key": "bullhead-city", "name": "Bullhead City", "lat": 35.1478, "lon": -114.5683,
     "zones": ["AZZ571", "AZZ002", "NVZ022", "NVZ026", "AZC015"], "regions": ["bullhead-city", "laughlin", "mohave-valley", "mohave-county", "colorado-river"]},
    {"key": "lake-havasu-city", "name": "Lake Havasu City", "lat": 34.4839, "lon": -114.3225,
     "zones": ["AZZ002", "AZZ576", "AZC015"], "regions": ["lake-havasu-city", "mohave-county", "colorado-river"]},
    {"key": "kingman", "name": "Kingman", "lat": 35.1894, "lon": -114.0530,
     "zones": ["AZZ001", "AZZ576", "AZC015"], "regions": ["kingman", "mohave-county"]},
    {"key": "mesquite", "name": "Mesquite", "lat": 36.8055, "lon": -114.0672,
     "zones": ["NVZ016"], "regions": ["mesquite", "clark-county"]},
    {"key": "boulder-city", "name": "Boulder City", "lat": 35.9786, "lon": -114.8325,
     "zones": ["NVZ025", "NVZ020"], "regions": ["boulder-city", "clark-county", "lake-mead"]},
    {"key": "lake-mead", "name": "Lake Mead", "lat": 36.0160, "lon": -114.7377,
     "zones": ["NVZ025", "AZZ570"], "regions": ["lake-mead", "colorado-river"]},
]
ALERT_ZONES = ["AZZ002", "AZZ571", "AZZ570", "AZZ576", "AZZ001", "NVZ022", "NVZ026", "NVZ025", "NVZ016", "NVZ017", "NVZ020"]
SITES = {
    "09421500": {"name": "Colorado River below Hoover Dam", "regions": ["lake-mead", "boulder-city", "colorado-river"]},
    "09423000": {"name": "Colorado River below Davis Dam", "regions": ["laughlin", "bullhead-city", "mohave-valley", "colorado-river"]},
    "09427520": {"name": "Colorado River below Parker Dam", "regions": ["lake-havasu-city", "colorado-river"]},
    "09415000": {"name": "Virgin River at Littlefield", "regions": ["mesquite"]},
}
AQI_BANDS = [(50, "Good"), (100, "Moderate"), (150, "Unhealthy for Sensitive Groups"), (200, "Unhealthy"), (300, "Very Unhealthy"), (10**6, "Hazardous")]


def aqi_label(v):
    try: v = float(v)
    except (TypeError, ValueError): return ""
    return next(lbl for hi, lbl in AQI_BANDS if v <= hi)


def _get(session, url, **params):
    r = session.get(url, params=params or None, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _warn(msg): print(f"WARN conditions: {msg}", file=sys.stderr)


# ----------------------------------------------------------------------------- fetchers
def _forecast(session, city):
    pts = _get(session, f"https://api.weather.gov/points/{city['lat']:.4f},{city['lon']:.4f}")["properties"]
    fc = _get(session, pts["forecast"])["properties"]
    periods = [{"name": p.get("name"), "temperature": p.get("temperature"), "unit": p.get("temperatureUnit", "F"),
                "shortForecast": p.get("shortForecast"), "icon": p.get("icon"), "startTime": p.get("startTime"),
                "isDaytime": p.get("isDaytime")} for p in (fc.get("periods") or [])[:2]]
    zone = (pts.get("forecastZone") or "").rsplit("/", 1)[-1]
    return {"forecast": periods, "forecast_updated": fc.get("updateTime") or fc.get("updated"), "nws_zone": zone or None,
            "nws_url": f"https://forecast.weather.gov/MapClick.php?lat={city['lat']}&lon={city['lon']}"}


def _alerts(session):
    data = _get(session, "https://api.weather.gov/alerts/active", zone=",".join(ALERT_ZONES))
    out = []
    for f in data.get("features") or []:
        p = f.get("properties") or {}
        ugc = ((p.get("geocode") or {}).get("UGC") or []) + [z.rsplit("/", 1)[-1] for z in (p.get("affectedZones") or [])]
        out.append({"id": p.get("id") or f.get("id"), "event": p.get("event"), "headline": p.get("headline"), "severity": p.get("severity"),
                    "urgency": p.get("urgency"), "areas": p.get("areaDesc"), "onset": p.get("onset"), "expires": p.get("expires") or p.get("ends"),
                    "zones": sorted(set(ugc)), "link": f.get("id") or p.get("@id") or "https://www.weather.gov/vef/"})
    return out


def _aqi(session):
    lat = ",".join(f"{c['lat']:.4f}" for c in CITIES); lon = ",".join(f"{c['lon']:.4f}" for c in CITIES)
    data = _get(session, "https://air-quality-api.open-meteo.com/v1/air-quality", latitude=lat, longitude=lon, current="us_aqi", timezone="America/Phoenix")
    if isinstance(data, dict): data = [data]
    out = {}
    for city, d in zip(CITIES, data):
        cur = (d or {}).get("current") or {}
        if cur.get("us_aqi") is None: continue
        out[city["key"]] = {"value": int(round(cur["us_aqi"])), "category": aqi_label(cur["us_aqi"]), "time": cur.get("time"), "source": "Open-Meteo (CAMS)"}
    return out


def _rivers(session, now):
    data = _get(session, "https://waterservices.usgs.gov/nwis/iv/", sites=",".join(SITES), parameterCd="00060,00065", period="P2D", format="json")
    rows = {}
    for ts in (data.get("value") or {}).get("timeSeries") or []:
        site = ts["sourceInfo"]["siteCode"][0]["value"]; var = ts["variable"]["variableCode"][0]["value"]
        vals = [v for v in (ts.get("values") or [{}])[0].get("value") or [] if v.get("value") not in (None, "", "-999999")]
        if not vals: continue
        last = vals[-1]
        try: when = dt.datetime.fromisoformat(last["dateTime"])
        except ValueError: continue
        if (now - when).total_seconds() > STALE_HOURS * 3600: continue
        row = rows.setdefault(site, {"site": site, "name": SITES.get(site, {}).get("name") or ts["sourceInfo"]["siteName"].title(),
                                     "usgs_name": ts["sourceInfo"]["siteName"], "regions": SITES.get(site, {}).get("regions", []),
                                     "time": when.isoformat(), "link": f"https://waterdata.usgs.gov/monitoring-location/{site}/"})
        try: num = float(last["value"])
        except ValueError: continue
        if var == "00060": row["flow_cfs"] = int(round(num))
        elif var == "00065": row["gage_ft"] = round(num, 2)
    return [rows[s] for s in SITES if s in rows]


# ----------------------------------------------------------------------------- public
def fetch_conditions(now=None):
    """Fetch everything concurrently (10s timeouts, each piece optional). Never raises."""
    if os.environ.get("SOURCES_DISABLED") == "1": return {}
    if "://" not in SRC:
        for cand in (pathlib.Path(SRC) / "feeds/conditions.json", FIXTURE):
            if cand.exists():
                try: return json.loads(cand.read_text(encoding="utf-8"))
                except Exception as e: _warn(f"bad fixture {cand}: {e}")
        return {}
    now = now or dt.datetime.now(dt.timezone.utc)
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.5"})
    cond = {"fetched": now.replace(microsecond=0).isoformat(), "cities": {}, "alerts": [], "rivers": []}
    for c in CITIES: cond["cities"][c["key"]] = {"key": c["key"], "name": c["name"], "lat": c["lat"], "lon": c["lon"], "regions": c["regions"], "zones": c["zones"]}
    jobs = {"alerts": lambda: _alerts(s), "aqi": lambda: _aqi(s), "rivers": lambda: _rivers(s, now)}
    for c in CITIES: jobs[f"fc:{c['key']}"] = (lambda c=c: _forecast(s, c))
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="cond") as ex:
        futs = {k: ex.submit(fn) for k, fn in jobs.items()}
        for k, fut in futs.items():
            try: res = fut.result(timeout=TIMEOUT * 3)
            except Exception as e: _warn(f"{k}: {type(e).__name__}: {str(e)[:140]}"); continue
            if k == "alerts": cond["alerts"] = res
            elif k == "rivers": cond["rivers"] = res
            elif k == "aqi":
                for ck, v in res.items(): cond["cities"][ck]["aqi"] = v
            else: cond["cities"][k[3:]].update(res)
    for c in cond["cities"].values():
        zones = set(c["zones"])
        c["alerts"] = [a["id"] for a in cond["alerts"] if zones & set(a.get("zones") or [])]
    ok = [k for k, c in cond["cities"].items() if c.get("forecast")]
    print(f"conditions: {len(ok)}/{len(CITIES)} forecasts, {len(cond['alerts'])} alerts, {len(cond['rivers'])} gauges, aqi for {sum(1 for c in cond['cities'].values() if c.get('aqi'))}", file=sys.stderr)
    return cond


def write_conditions(out_dir, cond=None):
    cond = fetch_conditions() if cond is None else cond
    out = pathlib.Path(out_dir) / "data"; out.mkdir(parents=True, exist_ok=True)
    (out / "conditions.json").write_text(json.dumps(cond, ensure_ascii=False, indent=1), encoding="utf-8")
    return cond


def _fmt_num(n): return f"{int(n):,}"


def render_strip(cond, region_key=None, limit=14):
    """Compact accessible chip list. Classes are all prefixed `cond` so the UI layer can style them.
    region_key=None shows every city; otherwise cities/gauges whose `regions` include the key."""
    if not cond or not cond.get("cities"): return ""
    cities = [c for c in cond["cities"].values() if region_key is None or region_key in (c.get("regions") or [])]
    rivers = [r for r in cond.get("rivers") or [] if region_key is None or region_key in (r.get("regions") or [])]
    if not cities and not rivers: return ""
    by_id = {a.get("id"): a for a in cond.get("alerts") or []}
    alert_ids = []
    for c in cities:
        for aid in c.get("alerts") or []:
            if aid in by_id and aid not in alert_ids: alert_ids.append(aid)
    li = []
    for aid in alert_ids:
        a = by_id[aid]; sev = (a.get("severity") or "unknown").lower()
        meta = a.get("areas") or ""
        li.append(f'<li class="cond-item cond-alert cond-alert--{esc(sev)}"><a class="cond-link" href="{esc(a.get("link"))}" rel="noopener">'
                  f'<span class="cond-label">{esc(a.get("event") or "Weather alert")}</span></a>'
                  + (f' <span class="cond-meta">{esc(meta)}</span>' if meta else "") + "</li>")
    for c in cities:
        p = (c.get("forecast") or [None])[0]
        if p and p.get("temperature") is not None:
            li.append(f'<li class="cond-item cond-wx"><a class="cond-link" href="{esc(c.get("nws_url") or "https://www.weather.gov/vef/")}" rel="noopener" '
                      f'title="{esc(p.get("name"))}: {esc(p.get("shortForecast"))} (NWS)"><span class="cond-place">{esc(c["name"])}</span> '
                      f'<span class="cond-temp">{esc(p["temperature"])}°{esc(p.get("unit") or "F")}</span> <span class="cond-desc">{esc(p.get("shortForecast"))}</span></a></li>')
        q = c.get("aqi")
        if q and q.get("value") is not None:
            cls = (q.get("category") or "").lower().split(" ")[0] or "na"
            place = f'<span class="cond-place">{esc(c["name"])}</span> ' if len(cities) > 1 and not p else ""
            li.append(f'<li class="cond-item cond-aqi cond-aqi--{esc(cls)}" title="US AQI, Open-Meteo">{place}<span class="cond-label">AQI</span> '
                      f'<span class="cond-val">{esc(q["value"])}</span> <span class="cond-desc">{esc(q.get("category"))}</span></li>')
    for r in rivers:
        if r.get("flow_cfs") is not None: val = f'{_fmt_num(r["flow_cfs"])} cfs'
        elif r.get("gage_ft") is not None: val = f'{r["gage_ft"]:.1f} ft'
        else: continue
        li.append(f'<li class="cond-item cond-river"><a class="cond-link" href="{esc(r.get("link"))}" rel="noopener" title="USGS gauge {esc(r.get("site"))}">'
                  f'<span class="cond-place">{esc(r["name"])}</span> <span class="cond-val">{esc(val)}</span></a></li>')
    if not li: return ""
    return f'<ul class="cond" aria-label="River and weather conditions">{"".join(li[:limit])}</ul>'
