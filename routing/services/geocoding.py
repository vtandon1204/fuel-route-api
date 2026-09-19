"""
Thin wrapper around the free, keyless OpenStreetMap Nominatim geocoding
service. Results are cached (by normalized query string) so the same
"Los Angeles, CA" -> (lat, lon) lookup never hits the network twice.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache


class GeocodingError(Exception):
    """Raised when a location string can't be resolved to coordinates."""


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    display_name: str


def _cache_key(query: str) -> str:
    digest = hashlib.sha256(query.strip().lower().encode()).hexdigest()
    return f"geocode:{digest}"


def geocode_location(query: str) -> GeocodeResult:
    """
    Resolve a free-text location (e.g. "Chicago, IL" or a full street
    address) to coordinates, restricted to the US per the assignment spec.
    """
    if not query or not query.strip():
        raise GeocodingError("Location string is empty.")

    key = _cache_key(query)
    cached = cache.get(key)
    if cached is not None:
        return GeocodeResult(**cached)

    try:
        response = requests.get(
            f"{settings.NOMINATIM_BASE_URL}/search",
            params={
                "q": query,
                "format": "jsonv2",
                "countrycodes": "us",
                "limit": 1,
            },
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.EXTERNAL_HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GeocodingError(f"Geocoding service request failed: {exc}") from exc

    results = response.json()
    if not results:
        raise GeocodingError(f"Could not find a US location matching '{query}'.")

    top = results[0]
    result = GeocodeResult(
        latitude=float(top["lat"]),
        longitude=float(top["lon"]),
        display_name=top.get("display_name", query),
    )

    cache.set(key, result.__dict__)
    return result
