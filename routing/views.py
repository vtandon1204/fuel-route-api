import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from routing.models import RoutePlan
from routing.serializers import RoutePlanRequestSerializer, RoutePlanSerializer
from routing.services.route_planner import RoutePlanningError, plan_route


class RoutePlanView(APIView):
    """
    POST /api/route-plans/
        body: {"start_location": "...", "finish_location": "..."}
        -> plans a route, chooses the cheapest feasible fuel stops, persists
           the plan, and returns it (including a map_url you can open in a
           browser).

    GET /api/route-plans/<id>/
        -> re-fetch a previously computed plan (no external calls at all).
    """

    def post(self, request):
        request_serializer = RoutePlanRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        start_location = request_serializer.validated_data["start_location"]
        finish_location = request_serializer.validated_data["finish_location"]

        try:
            planned = plan_route(start_location, finish_location)
        except RoutePlanningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        fuel_stops_payload = [
            {
                "station_name": stop.station.name,
                "address": stop.station.address,
                "city": stop.station.city,
                "state": stop.station.state,
                "price_per_gallon": float(stop.station.price_per_gallon),
                "latitude": stop.station.latitude,
                "longitude": stop.station.longitude,
                "mile_marker": round(stop.mile_marker, 1),
                "gallons_purchased": round(stop.gallons_purchased, 2),
                "cost_usd": round(stop.cost_usd, 2),
            }
            for stop in planned.fuel_plan.stops
        ]

        route_plan = RoutePlan.objects.create(
            start_location=planned.start_location,
            finish_location=planned.finish_location,
            start_latitude=planned.start_lat,
            start_longitude=planned.start_lon,
            finish_latitude=planned.finish_lat,
            finish_longitude=planned.finish_lon,
            total_distance_miles=planned.total_distance_miles,
            total_duration_seconds=planned.total_duration_seconds,
            total_fuel_cost_usd=round(planned.fuel_plan.total_cost_usd, 2),
            total_gallons=round(planned.fuel_plan.total_gallons, 2),
            route_geometry=[[lat, lon] for lat, lon in planned.geometry],
            fuel_stops=fuel_stops_payload,
        )

        serializer = RoutePlanSerializer(route_plan, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RoutePlanDetailView(APIView):
    def get(self, request, plan_id):
        route_plan = get_object_or_404(RoutePlan, id=plan_id)
        serializer = RoutePlanSerializer(route_plan, context={"request": request})
        return Response(serializer.data)


def route_plan_map_view(request, plan_id):
    """
    A small server-rendered Leaflet map (OpenStreetMap tiles, no API key)
    showing the planned route and the chosen fuel stops. This is the
    "map displaying the planned route" deliverable - open the URL from the
    POST response's `map_url` field in a browser.
    """
    route_plan = get_object_or_404(RoutePlan, id=plan_id)
    context = {
        "route_plan": route_plan,
        "geometry_json": json.dumps(route_plan.route_geometry),
        "fuel_stops_json": json.dumps(route_plan.fuel_stops),
    }
    return render(request, "routing/map.html", context)


def api_root(request):
    """
    Simple API root that lists available endpoints.
    """
    base = request.build_absolute_uri("/api/")
    data = {
        "message": "Fuel Route API",
        "endpoints": {
            "create_route_plan": f"{base}route-plans/",
            "get_route_plan": f"{base}route-plans/<plan_id>/",
            "route_map": f"{base}route-plans/<plan_id>/map/",
        },
    }
    return JsonResponse(data)
