"""
Pure math helpers for working with lat/lon points and route polylines.
No external calls happen anywhere in this module - it's all geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.7613

RoutePoint = tuple[float, float]  # (lat, lon)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_MILES * c


def bounding_box(points: list[RoutePoint], padding_miles: float) -> tuple[float, float, float, float]:
    """
    Returns (min_lat, max_lat, min_lon, max_lon) for a set of points, padded
    outward by `padding_miles` so a cheap SQL filter can be used before doing
    precise (and more expensive) point-to-polyline distance checks.
    """
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)

    # ~69 miles per degree of latitude; longitude degrees shrink with cos(lat).
    lat_pad = padding_miles / 69.0
    mean_lat = math.radians((min_lat + max_lat) / 2)
    lon_pad = padding_miles / (69.0 * max(math.cos(mean_lat), 0.1))

    return (min_lat - lat_pad, max_lat + lat_pad, min_lon - lon_pad, max_lon + lon_pad)


@dataclass
class RouteProjection:
    """Where a point falls relative to a decimated route polyline."""

    distance_to_route_miles: float
    cumulative_miles_at_nearest_point: float


def build_cumulative_miles(points: list[RoutePoint]) -> list[float]:
    """Cumulative distance (miles) travelled along the polyline at each vertex."""
    cumulative = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + haversine_miles(lat1, lon1, lat2, lon2))
    return cumulative


def decimate_route(
    points: list[RoutePoint], cumulative_miles: list[float], step_miles: float = 1.0
) -> tuple[list[RoutePoint], list[float]]:
    """
    Thin a (potentially huge) route geometry down to ~1 point per step_miles.
    This keeps the O(stations x route_points) projection step fast without
    materially hurting accuracy, since fuel stations are matched to the
    nearest *city*, not an exact GPS pump location anyway.
    """
    if not points:
        return [], []

    thin_points = [points[0]]
    thin_miles = [cumulative_miles[0]]
    last_kept = cumulative_miles[0]

    for pt, miles in zip(points[1:], cumulative_miles[1:]):
        if miles - last_kept >= step_miles:
            thin_points.append(pt)
            thin_miles.append(miles)
            last_kept = miles

    if thin_points[-1] != points[-1]:
        thin_points.append(points[-1])
        thin_miles.append(cumulative_miles[-1])

    return thin_points, thin_miles


def project_point_onto_route(
    lat: float,
    lon: float,
    route_points: list[RoutePoint],
    route_cumulative_miles: list[float],
) -> RouteProjection:
    """
    Finds the nearest vertex of a (decimated) route polyline to (lat, lon)
    and returns both the distance to it and the route's cumulative mileage
    at that vertex. This is a nearest-vertex approximation rather than a
    true point-to-segment projection, which is more than accurate enough
    once the route has been decimated to ~1 point/mile.
    """
    best_dist = math.inf
    best_miles = 0.0

    for (plat, plon), miles in zip(route_points, route_cumulative_miles):
        d = haversine_miles(lat, lon, plat, plon)
        if d < best_dist:
            best_dist = d
            best_miles = miles

    return RouteProjection(distance_to_route_miles=best_dist, cumulative_miles_at_nearest_point=best_miles)


def project_points_onto_route_batch(
    query_points: list[RoutePoint],
    route_points: list[RoutePoint],
    route_cumulative_miles: list[float],
) -> list[RouteProjection]:
    """
    Vectorized (numpy) equivalent of calling project_point_onto_route() once
    per query point. With a corridor search comparing every candidate
    station to every (decimated) route vertex, the naive pure-Python nested
    loop is the dominant cost of a request; batching it as one matrix
    operation is what keeps a cross-country route search fast (well under a
    second even against the full ~8k station table).
    """
    if not query_points or not route_points:
        return [RouteProjection(math.inf, 0.0) for _ in query_points]

    import numpy as np

    q = np.radians(np.array(query_points))  # (M, 2)
    r = np.radians(np.array(route_points))  # (N, 2)
    r_miles = np.array(route_cumulative_miles)  # (N,)

    q_lat, q_lon = q[:, 0][:, None], q[:, 1][:, None]  # (M, 1)
    r_lat, r_lon = r[:, 0][None, :], r[:, 1][None, :]  # (1, N)

    d_lat = r_lat - q_lat
    d_lon = r_lon - q_lon
    a = np.sin(d_lat / 2) ** 2 + np.cos(q_lat) * np.cos(r_lat) * np.sin(d_lon / 2) ** 2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    distances = EARTH_RADIUS_MILES * c  # (M, N) miles from each query point to each route vertex

    nearest_idx = np.argmin(distances, axis=1)
    nearest_dist = distances[np.arange(len(query_points)), nearest_idx]
    nearest_miles = r_miles[nearest_idx]

    return [
        RouteProjection(distance_to_route_miles=float(d), cumulative_miles_at_nearest_point=float(m))
        for d, m in zip(nearest_dist, nearest_miles)
    ]
