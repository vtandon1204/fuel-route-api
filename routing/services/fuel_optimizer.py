"""
The heart of the assignment: given a route polyline and the vehicle's
range/MPG, choose which fuel stations to stop at (and how much to buy at
each) so that the trip is completed without running out of fuel, at the
lowest possible total cost.

Algorithm
---------
1. Corridor filter: cheaply narrow ~8,000 stations down to the handful
   actually near the route, using a lat/lon bounding-box query in the DB.
2. Projection: for each candidate station, find where along the route
   (cumulative miles from the start) it sits, and how far off the route
   it is. Drop anything farther than FUEL_STATION_CORRIDOR_MILES away.
3. Optimal stop selection: this is the classic "gas station on a line"
   problem. Model it as a DAG shortest-path / dynamic program:
     - Nodes are the start (mile 0), every candidate station (at its
       projected mile marker), and the finish (mile = total distance).
     - A directed edge exists from node i to a later node j only if the
       gap (m_j - m_i) is within the vehicle's *effective* range (max
       range minus a safety margin).
     - The cost of an edge i -> j is the price at station i multiplied by
       the gallons needed to cover that gap (edges leaving the start are
       free, since the vehicle departs with a full tank).
     - Because nodes are already sorted by position, dp[j] = min over
       feasible i<j of dp[i] + cost(i, j) computed in a single left-to-right
       pass gives the true minimum-cost route, not just a greedy
       approximation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.conf import settings

from routing.models import FuelStation
from routing.services import geo_utils


class NoFeasibleRouteError(Exception):
    """
    Raised when there's a gap along the route longer than the vehicle's
    effective range with no fuel station in the corridor to bridge it.
    """


@dataclass
class FuelStop:
    station: FuelStation
    mile_marker: float
    distance_from_route_miles: float
    gallons_purchased: float
    cost_usd: float


@dataclass
class FuelPlan:
    stops: list[FuelStop] = field(default_factory=list)
    total_cost_usd: float = 0.0
    total_gallons: float = 0.0


def _candidate_stations(route_points: list[geo_utils.RoutePoint]) -> list[FuelStation]:
    """Cheap bounding-box pre-filter using the DB before precise geometry checks."""
    min_lat, max_lat, min_lon, max_lon = geo_utils.bounding_box(
        route_points, padding_miles=settings.FUEL_STATION_CORRIDOR_MILES
    )
    return list(
        FuelStation.objects.filter(
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lon,
            longitude__lte=max_lon,
            latitude__isnull=False,
            longitude__isnull=False,
        )
    )


def find_stations_along_route(
    route_points: list[geo_utils.RoutePoint],
) -> list[tuple[FuelStation, float, float]]:
    """
    Returns (station, mile_marker, distance_from_route_miles) tuples for
    every station within FUEL_STATION_CORRIDOR_MILES of the route,
    sorted by mile_marker ascending.
    """
    cumulative_miles = geo_utils.build_cumulative_miles(route_points)
    thin_points, thin_miles = geo_utils.decimate_route(route_points, cumulative_miles, step_miles=2.0)

    candidates = _candidate_stations(route_points)
    if not candidates:
        return []

    query_points = [(s.latitude, s.longitude) for s in candidates]
    projections = geo_utils.project_points_onto_route_batch(query_points, thin_points, thin_miles)

    matches = [
        (station, projection.cumulative_miles_at_nearest_point, projection.distance_to_route_miles)
        for station, projection in zip(candidates, projections)
        if projection.distance_to_route_miles <= settings.FUEL_STATION_CORRIDOR_MILES
    ]

    matches.sort(key=lambda m: m[1])
    return matches


def optimize_fuel_stops(
    total_distance_miles: float,
    stations_on_route: list[tuple[FuelStation, float, float]],
    max_range_miles: float | None = None,
    mpg: float | None = None,
    safety_margin_miles: float | None = None,
) -> FuelPlan:
    """
    Runs the DP described in the module docstring and returns the
    minimum-cost set of fuel stops (possibly empty, if the whole trip
    fits in one tank).
    """
    max_range_miles = max_range_miles or settings.VEHICLE_MAX_RANGE_MILES
    mpg = mpg or settings.VEHICLE_MPG
    safety_margin_miles = (
        settings.VEHICLE_RANGE_SAFETY_MARGIN_MILES if safety_margin_miles is None else safety_margin_miles
    )
    effective_range = max_range_miles - safety_margin_miles

    if total_distance_miles <= effective_range:
        # Whole trip fits on a single full tank - no stops, no purchases.
        return FuelPlan(stops=[], total_cost_usd=0.0, total_gallons=0.0)

    # Node 0 = start (free/full tank), nodes 1..n = stations, node n+1 = finish.
    nodes: list[dict] = [{"mile": 0.0, "price": None, "station": None, "dist_off_route": 0.0}]
    for station, mile, dist_off_route in stations_on_route:
        nodes.append(
            {
                "mile": mile,
                "price": float(station.price_per_gallon),
                "station": station,
                "dist_off_route": dist_off_route,
            }
        )
    nodes.append({"mile": total_distance_miles, "price": None, "station": None, "dist_off_route": 0.0})

    n = len(nodes)
    INF = float("inf")
    dp = [INF] * n
    parent = [-1] * n
    dp[0] = 0.0

    for i in range(n):
        if dp[i] == INF:
            continue
        for j in range(i + 1, n):
            gap = nodes[j]["mile"] - nodes[i]["mile"]
            if gap > effective_range:
                # Nodes are sorted by mile, so once the gap is too big it
                # only grows further for larger j - stop scanning from i.
                break
            if gap < 0:
                continue
            leg_cost = 0.0 if i == 0 else (gap / mpg) * nodes[i]["price"]
            if dp[i] + leg_cost < dp[j]:
                dp[j] = dp[i] + leg_cost
                parent[j] = i

    if dp[n - 1] == INF:
        raise NoFeasibleRouteError(
            "No combination of fuel stations along this route keeps the vehicle "
            "within its range - there's a gap longer than the vehicle's "
            "effective range with no station in the search corridor."
        )

    # Reconstruct the chosen stop sequence (excluding the synthetic start/finish nodes).
    path = []
    cur = n - 1
    while cur != -1:
        path.append(cur)
        cur = parent[cur]
    path.reverse()

    stops = []
    total_cost = 0.0
    total_gallons = 0.0
    for a, b in zip(path, path[1:]):
        if a == 0:
            continue  # no purchase for the initial full tank
        gap = nodes[b]["mile"] - nodes[a]["mile"]
        gallons = gap / mpg
        cost = gallons * nodes[a]["price"]
        total_cost += cost
        total_gallons += gallons
        stops.append(
            FuelStop(
                station=nodes[a]["station"],
                mile_marker=nodes[a]["mile"],
                distance_from_route_miles=nodes[a]["dist_off_route"],
                gallons_purchased=gallons,
                cost_usd=cost,
            )
        )

    return FuelPlan(stops=stops, total_cost_usd=total_cost, total_gallons=total_gallons)
