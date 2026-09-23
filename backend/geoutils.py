"""Geo math helpers: distance, bearing, and moving a point along a heading.

Accurate enough for a city-scale delivery simulation (equirectangular
approximation over short distances)."""
import math

_EARTH_M = 6_371_000.0
_M_PER_DEG_LAT = 111_320.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two WGS-84 points, in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2.0 * _EARTH_M * math.asin(min(1.0, math.sqrt(a)))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return haversine_m(lat1, lng1, lat2, lng2) / 1000.0


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2 (0=N, 90=E)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lng2 - lng1)
    y = math.sin(dlmb) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlmb)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def move_position(lat: float, lng: float, heading_deg: float, distance_m: float):
    """Move `distance_m` from (lat, lng) along `heading_deg`."""
    h = math.radians(heading_deg)
    dlat = (distance_m * math.cos(h)) / _M_PER_DEG_LAT
    dlng = (distance_m * math.sin(h)) / (_M_PER_DEG_LAT * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))
