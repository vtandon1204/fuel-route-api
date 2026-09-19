"""
Thin wrapper around the free, keyless OSRM public routing server
(router.project-osrm.org), which provides the actual road-network route
+ geometry between two points. This is the single "map/routing API" call
the assignment cares about minimizing - one call per /api/route-plan/
request, cached by rounded start/finish coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

METERS_PER_MILE = 1609.344


class RoutingError(Exception):
    """Raised when a route can't be computed between two points."""


@dataclass
class RouteResult:
    distance_miles: float
    duration_seconds: float
    geometry: list[tuple[float, float]]  # list of (lat, lon)


def _cache_key(start_lat: float, start_lon: float, finish_lat: float, finish_lon: float) -> str:
    # Round to ~11m precision - plenty for caching without merging distinct requests.
    return "osrm_route:{:.5f},{:.5f}:{:.5f},{:.5f}".format(
        start_lat, start_lon, finish_lat, finish_lon
    )


def get_driving_route(
    start_lat: float, start_lon: float, finish_lat: float, finish_lon: float
) -> RouteResult:
    key = _cache_key(start_lat, start_lon, finish_lat, finish_lon)
    cached = cache.get(key)
    if cached is not None:
        return RouteResult(
            distance_miles=cached["distance_miles"],
            duration_seconds=cached["duration_seconds"],
            geometry=[tuple(p) for p in cached["geometry"]],
        )

    # OSRM expects "lon,lat;lon,lat" ordering.
    coordinates = f"{start_lon},{start_lat};{finish_lon},{finish_lat}"
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coordinates}"

    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.EXTERNAL_HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RoutingError(f"Routing service request failed: {exc}") from exc

    payload = response.json()
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise RoutingError(
            f"No drivable route found between the given points "
            f"(provider said: {payload.get('code', 'unknown error')})."
        )

    route = payload["routes"][0]
    distance_miles = route["distance"] / METERS_PER_MILE
    duration_seconds = route["duration"]

    # GeoJSON coordinates are [lon, lat] - flip to (lat, lon) for the rest of the app.
    geometry = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]

    cache.set(
        key,
        {
            "distance_miles": distance_miles,
            "duration_seconds": duration_seconds,
            "geometry": geometry,
        },
    )

    return RouteResult(distance_miles=distance_miles, duration_seconds=duration_seconds, geometry=geometry)
