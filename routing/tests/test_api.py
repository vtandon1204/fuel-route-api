from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from routing.models import FuelStation
from routing.services import geocoding, osrm


def fake_geocode(query):
    """Deterministic stand-in for Nominatim: 'Start' and 'Finish' map to two
    points ~700 miles apart on a simple east-west line along latitude 35."""
    points = {
        "start city, tx": geocoding.GeocodeResult(35.0, -100.0, "Start City, TX, USA"),
        "finish city, tx": geocoding.GeocodeResult(35.0, -90.0, "Finish City, TX, USA"),
    }
    key = query.strip().lower()
    if key not in points:
        raise geocoding.GeocodingError(f"Unknown test location: {query}")
    return points[key]


def fake_route(start_lat, start_lon, finish_lat, finish_lon):
    """A straight line of points between start and finish, ~700 miles, so the
    optimizer has to choose a fuel stop."""
    steps = 50
    geometry = [
        (
            start_lat + (finish_lat - start_lat) * i / steps,
            start_lon + (finish_lon - start_lon) * i / steps,
        )
        for i in range(steps + 1)
    ]
    return osrm.RouteResult(distance_miles=690.0, duration_seconds=36000.0, geometry=geometry)


class RoutePlanAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # A cheap station roughly at the midpoint of the fake route (lon ~ -95).
        FuelStation.objects.create(
            opis_id=1,
            name="Midpoint Fuel Stop",
            address="123 Main St",
            city="Midtown",
            state="TX",
            price_per_gallon=Decimal("2.75"),
            latitude=35.0,
            longitude=-95.0,
        )
        # A far-off station that should NOT be picked up (way off the corridor).
        FuelStation.objects.create(
            opis_id=2,
            name="Faraway Fuel Stop",
            address="1 Nowhere Rd",
            city="Elsewhere",
            state="TX",
            price_per_gallon=Decimal("1.00"),
            latitude=45.0,
            longitude=-95.0,
        )

    @patch("routing.services.route_planner.osrm.get_driving_route", side_effect=fake_route)
    @patch("routing.services.route_planner.geocoding.geocode_location", side_effect=fake_geocode)
    def test_post_route_plan_returns_expected_shape_and_picks_up_station(self, mock_geocode, mock_route):
        url = reverse("routing:route-plan-create")
        response = self.client.post(
            url,
            {"start_location": "Start City, TX", "finish_location": "Finish City, TX"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        data = response.data

        self.assertIn("id", data)
        self.assertIn("map_url", data)
        self.assertEqual(data["total_distance_miles"], 690.0)
        self.assertEqual(len(data["fuel_stops"]), 1)
        self.assertEqual(data["fuel_stops"][0]["station_name"], "Midpoint Fuel Stop")
        self.assertGreater(float(data["total_fuel_cost_usd"]), 0)

        mock_geocode.assert_called()
        mock_route.assert_called_once()

    @patch("routing.services.route_planner.osrm.get_driving_route", side_effect=fake_route)
    @patch("routing.services.route_planner.geocoding.geocode_location", side_effect=fake_geocode)
    def test_get_route_plan_after_creation(self, mock_geocode, mock_route):
        create_url = reverse("routing:route-plan-create")
        create_response = self.client.post(
            create_url,
            {"start_location": "Start City, TX", "finish_location": "Finish City, TX"},
            format="json",
        )
        plan_id = create_response.data["id"]

        detail_url = reverse("routing:route-plan-detail", args=[plan_id])
        detail_response = self.client.get(detail_url)

        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["id"], plan_id)

    def test_post_missing_fields_returns_400(self):
        url = reverse("routing:route-plan-create")
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, 400)

    @patch(
        "routing.services.route_planner.geocoding.geocode_location",
        side_effect=geocoding.GeocodingError("nope"),
    )
    def test_unresolvable_location_returns_422(self, mock_geocode):
        url = reverse("routing:route-plan-create")
        response = self.client.post(
            url,
            {"start_location": "???", "finish_location": "Finish City, TX"},
            format="json",
        )
        self.assertEqual(response.status_code, 422)

    @patch("routing.services.route_planner.osrm.get_driving_route", side_effect=fake_route)
    @patch("routing.services.route_planner.geocoding.geocode_location", side_effect=fake_geocode)
    def test_map_view_renders_html(self, mock_geocode, mock_route):
        create_url = reverse("routing:route-plan-create")
        create_response = self.client.post(
            create_url,
            {"start_location": "Start City, TX", "finish_location": "Finish City, TX"},
            format="json",
        )
        plan_id = create_response.data["id"]

        map_url = reverse("routing:route-plan-map", args=[plan_id])
        map_response = self.client.get(map_url)

        self.assertEqual(map_response.status_code, 200)
        self.assertIn(b"leaflet", map_response.content.lower())
