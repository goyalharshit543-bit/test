"""Place-name ↔ coordinates service (geocoding).

Turns a typed place name into lat/lng ("Indiranagar, Bengaluru" → 12.9784, 77.6408)
and, when the user clicks the map, a lat/lng back into a readable place name.

Providers, tried in order:
  1. Google Geocoding API  — used automatically when GOOGLE_MAPS_API_KEY is set
  2. OpenStreetMap Nominatim — free, no key needed (default)

Results are cached in memory so repeated searches are instant and we stay
well inside the free-tier usage policies (max ~1 request/second, so every
network call is also rate-limited per provider).
"""
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from backend.config import settings

log = logging.getLogger("geocode")

_UA = "SkyCart-DroneDelivery/1.0 (educational project)"
_cache: Dict[str, Any] = {}          # cache_key -> result
_last_call: Dict[str, float] = {}    # provider -> monotonic time of last network call
_MIN_INTERVAL = 1.05                 # seconds between network calls per provider


def _http_json(url: str, headers: Optional[Dict[str, str]] = None,
               timeout: float = 6.0) -> Any:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _throttle(provider: str) -> None:
    """Keep each provider to ≈1 request/second (Nominatim usage policy)."""
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call.get(provider, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last_call[provider] = time.monotonic()


# ── Google ──────────────────────────────────────────────────────────
def _google_geocode(query: str = "", latlng: str = "") -> Optional[List[Dict[str, Any]]]:
    if not settings.GOOGLE_MAPS_API_KEY:
        return None
    params = {"key": settings.GOOGLE_MAPS_API_KEY}
    if query:
        params["address"] = query
    if latlng:
        params["latlng"] = latlng
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(params)
    try:
        _throttle("google")
        data = _http_json(url)
    except Exception as exc:
        log.warning("Google geocode failed: %s", exc)
        return None
    out = []
    for r in data.get("results", [])[:5]:
        loc = r["geometry"]["location"]
        out.append({
            "label": r.get("formatted_address", ""),
            "lat": loc["lat"],
            "lng": loc["lng"],
            "source": "google",
        })
    return out


# ── Nominatim (OpenStreetMap) ───────────────────────────────────────
def _nominatim_search(query: str) -> List[Dict[str, Any]]:
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&addressdetails=1&q="
           + urllib.parse.quote(query))
    try:
        _throttle("nominatim")
        rows = _http_json(url)
    except Exception as exc:
        log.warning("Nominatim search failed: %s", exc)
        return []
    out = []
    for r in rows:
        out.append({
            "label": r.get("display_name", query),
            "lat": float(r["lat"]),
            "lng": float(r["lon"]),
            "source": "osm",
        })
    return out


def _nominatim_reverse(lat: float, lng: float) -> Optional[str]:
    url = ("https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=18&addressdetails=1"
           f"&lat={lat}&lon={lng}")
    try:
        _throttle("nominatim")
        data = _http_json(url)
    except Exception as exc:
        log.warning("Nominatim reverse failed: %s", exc)
        return None
    return data.get("display_name")


# ── public API ──────────────────────────────────────────────────────
def search_places(query: str) -> List[Dict[str, Any]]:
    """Autocomplete: 'indira nagar' → up to 5 labelled coordinate candidates."""
    query = (query or "").strip()
    if len(query) < 3:
        return []
    key = f"search:{query.lower()}"
    if key in _cache:
        return _cache[key]

    results = _google_geocode(query=query) or _nominatim_search(query)
    _cache[key] = results
    if len(_cache) > 600:  # simple cap so the cache can't grow forever
        _cache.pop(next(iter(_cache)))
    return results


def reverse_geocode(lat: float, lng: float) -> Optional[str]:
    """Coordinates → human-readable place name (None if lookup fails)."""
    key = f"rev:{round(lat, 5)},{round(lng, 5)}"
    if key in _cache:
        return _cache[key]

    name = _google_geocode(latlng=f"{lat},{lng}")
    name = name[0]["label"] if name else _nominatim_reverse(lat, lng)
    _cache[key] = name
    return name


def resolve_place(query: str) -> Optional[Dict[str, Any]]:
    """One best match for a typed place name — used by the orders API and SkyBot."""
    results = search_places(query)
    return results[0] if results else None
