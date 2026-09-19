from django.test import SimpleTestCase

from routing.services import geo_utils


class HaversineTests(SimpleTestCase):
    def test_same_point_is_zero_distance(self):
        self.assertAlmostEqual(geo_utils.haversine_miles(40.0, -75.0, 40.0, -75.0), 0.0, places=6)

    def test_known_distance_los_angeles_to_new_york(self):
        # Approximate great-circle distance LA -> NYC is ~2,445 miles.
        la = (34.0522, -118.2437)
        nyc = (40.7128, -74.0060)
        distance = geo_utils.haversine_miles(*la, *nyc)
        self.assertGreater(distance, 2400)
        self.assertLess(distance, 2500)


class CumulativeMilesTests(SimpleTestCase):
    def test_cumulative_miles_monotonic_increasing(self):
        points = [(40.0, -75.0), (40.1, -75.0), (40.2, -75.0), (40.3, -75.0)]
        cumulative = geo_utils.build_cumulative_miles(points)
        self.assertEqual(cumulative[0], 0.0)
        self.assertEqual(len(cumulative), len(points))
        for a, b in zip(cumulative, cumulative[1:]):
            self.assertGreater(b, a)


class DecimateRouteTests(SimpleTestCase):
    def test_decimation_keeps_endpoints(self):
        points = [(40.0, -75.0 - 0.001 * i) for i in range(500)]
        cumulative = geo_utils.build_cumulative_miles(points)
        thin_points, thin_miles = geo_utils.decimate_route(points, cumulative, step_miles=1.0)
        self.assertEqual(thin_points[0], points[0])
        self.assertEqual(thin_points[-1], points[-1])
        # Should be meaningfully smaller than the original for a long route.
        self.assertLess(len(thin_points), len(points))


class ProjectPointOntoRouteTests(SimpleTestCase):
    def test_point_on_route_has_near_zero_distance(self):
        points = [(40.0, -75.0), (41.0, -75.0), (42.0, -75.0)]
        cumulative = geo_utils.build_cumulative_miles(points)
        projection = geo_utils.project_point_onto_route(41.0, -75.0, points, cumulative)
        self.assertAlmostEqual(projection.distance_to_route_miles, 0.0, places=3)
        self.assertAlmostEqual(projection.cumulative_miles_at_nearest_point, cumulative[1], places=3)

    def test_point_far_from_route_has_large_distance(self):
        points = [(40.0, -75.0), (41.0, -75.0)]
        cumulative = geo_utils.build_cumulative_miles(points)
        projection = geo_utils.project_point_onto_route(40.5, -80.0, points, cumulative)
        self.assertGreater(projection.distance_to_route_miles, 100)
