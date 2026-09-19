"""
Orchestrates a full route-plan request:
  1. Geocode start_location and finish_location -> coordinates
     (Nominatim, 2 calls, cached).
  2. Fetch the driving route between them -> geometry + distance
     (OSRM, 1 call, cached).
  3. Find fuel stations along the route and choose the cheapest feasible
     set of stops (pure local computation, no external calls).

Total external API calls per uncached request: 3 (well within the
assignment's "1 ideal, 2-3 acceptable" budget). Repeat requests for the
same start/finish are served entirely from cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from routing.services import fuel_optimizer, geocoding, osrm


class RoutePlanningError(Exception):
    """Wraps any failure in the geocode -> route -> optimize pipeline."""


@dataclass
class PlannedRoute:
    start_location: str
    finish_location: str
    start_lat: float
    start_lon: float
    finish_lat: float
    finish_lon: float
    total_distance_miles: float
    total_duration_seconds: float
    geometry: list[tuple[float, float]]
    fuel_plan: fuel_optimizer.FuelPlan


def plan_route(start_location: str, finish_location: str) -> PlannedRoute:
    try:
        start = geocoding.geocode_location(start_location)
        finish = geocoding.geocode_location(finish_location)
    except geocoding.GeocodingError as exc:
        raise RoutePlanningError(str(exc)) from exc

    try:
        route = osrm.get_driving_route(
            start.latitude, start.longitude, finish.latitude, finish.longitude
        )
    except osrm.RoutingError as exc:
        raise RoutePlanningError(str(exc)) from exc

    stations_on_route = fuel_optimizer.find_stations_along_route(route.geometry)

    try:
        fuel_plan = fuel_optimizer.optimize_fuel_stops(
            total_distance_miles=route.distance_miles,
            stations_on_route=stations_on_route,
        )
    except fuel_optimizer.NoFeasibleRouteError as exc:
        raise RoutePlanningError(str(exc)) from exc

    return PlannedRoute(
        start_location=start.display_name,
        finish_location=finish.display_name,
        start_lat=start.latitude,
        start_lon=start.longitude,
        finish_lat=finish.latitude,
        finish_lon=finish.longitude,
        total_distance_miles=route.distance_miles,
        total_duration_seconds=route.duration_seconds,
        geometry=route.geometry,
        fuel_plan=fuel_plan,
    )
