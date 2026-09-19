from decimal import Decimal

from django.test import SimpleTestCase

from routing.models import FuelStation
from routing.services import fuel_optimizer


def make_station(opis_id, price, name=None):
    return FuelStation(
        opis_id=opis_id,
        name=name or f"Station {opis_id}",
        address="",
        city="Testville",
        state="TX",
        price_per_gallon=Decimal(str(price)),
    )


class OptimizeFuelStopsTests(SimpleTestCase):
    """
    max_range=500, safety_margin=25 -> effective_range=475, mpg=10
    (the project defaults), passed explicitly here so the test doesn't
    silently break if the defaults ever change.
    """

    def test_trip_within_one_tank_needs_no_stops(self):
        plan = fuel_optimizer.optimize_fuel_stops(
            total_distance_miles=400,
            stations_on_route=[],
            max_range_miles=500,
            mpg=10,
            safety_margin_miles=25,
        )
        self.assertEqual(plan.stops, [])
        self.assertEqual(plan.total_cost_usd, 0.0)
        self.assertEqual(plan.total_gallons, 0.0)

    def test_prefers_cheaper_distant_station_over_pricier_near_one(self):
        # Station A (near, expensive) could be used alone, but it's cheaper
        # to skip it and use the free initial tank to reach the further,
        # cheaper station B instead.
        station_a = make_station(1, "3.00")
        station_b = make_station(2, "2.50")
        stations_on_route = [(station_a, 300.0, 0.5), (station_b, 450.0, 0.5)]

        plan = fuel_optimizer.optimize_fuel_stops(
            total_distance_miles=600,
            stations_on_route=stations_on_route,
            max_range_miles=500,
            mpg=10,
            safety_margin_miles=25,
        )

        self.assertEqual(len(plan.stops), 1)
        self.assertEqual(plan.stops[0].station, station_b)
        self.assertAlmostEqual(plan.total_cost_usd, 37.50, places=2)
        self.assertAlmostEqual(plan.total_gallons, 15.0, places=2)

    def test_requires_two_mandatory_stops_when_gap_too_large_for_one(self):
        station_a = make_station(1, "2.00")
        station_b = make_station(2, "4.00")
        stations_on_route = [(station_a, 400.0, 0.1), (station_b, 850.0, 0.1)]

        plan = fuel_optimizer.optimize_fuel_stops(
            total_distance_miles=900,
            stations_on_route=stations_on_route,
            max_range_miles=500,
            mpg=10,
            safety_margin_miles=25,
        )

        self.assertEqual(len(plan.stops), 2)
        self.assertEqual(plan.stops[0].station, station_a)
        self.assertEqual(plan.stops[1].station, station_b)
        # A -> B: 450mi / 10mpg * $2.00 = $90.00 ; B -> finish: 50mi / 10mpg * $4.00 = $20.00
        self.assertAlmostEqual(plan.total_cost_usd, 110.00, places=2)
        self.assertAlmostEqual(plan.total_gallons, 50.0, places=2)

    def test_raises_when_no_feasible_path_exists(self):
        station_a = make_station(1, "3.00")
        stations_on_route = [(station_a, 100.0, 0.1)]

        with self.assertRaises(fuel_optimizer.NoFeasibleRouteError):
            fuel_optimizer.optimize_fuel_stops(
                total_distance_miles=1000,
                stations_on_route=stations_on_route,
                max_range_miles=500,
                mpg=10,
                safety_margin_miles=25,
            )

    def test_picks_cheapest_among_multiple_reachable_options(self):
        cheap = make_station(1, "2.00")
        mid = make_station(2, "2.80")
        pricey = make_station(3, "3.50")
        stations_on_route = [(pricey, 100.0, 0.1), (mid, 200.0, 0.1), (cheap, 400.0, 0.1)]

        plan = fuel_optimizer.optimize_fuel_stops(
            total_distance_miles=700,
            stations_on_route=stations_on_route,
            max_range_miles=500,
            mpg=10,
            safety_margin_miles=25,
        )

        # 700 - 400 = 300 remaining after reaching the cheap station, well within range.
        self.assertEqual(len(plan.stops), 1)
        self.assertEqual(plan.stops[0].station, cheap)
        self.assertAlmostEqual(plan.total_cost_usd, 60.00, places=2)  # 300/10 * 2.00
