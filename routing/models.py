import uuid

from django.db import models


class FuelStation(models.Model):
    """
    A single fuel-price record loaded from data/fuel_prices.csv, enriched
    with approximate coordinates (city-center lat/lon) so it can be placed
    on a route. See routing/management/commands/load_fuel_prices.py for how
    this table is populated.
    """

    opis_id = models.IntegerField(db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128)
    state = models.CharField(max_length=8)
    rack_id = models.IntegerField(null=True, blank=True)
    price_per_gallon = models.DecimalField(max_digits=8, decimal_places=5)

    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["price_per_gallon"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) - ${self.price_per_gallon}/gal"

    @property
    def is_located(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class RoutePlan(models.Model):
    """
    A persisted result of a /api/route-plan/ POST, so it can be re-fetched
    (GET) and rendered as a map (GET .../map/) without recomputing or
    re-hitting the external routing/geocoding APIs.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    start_location = models.CharField(max_length=255)
    finish_location = models.CharField(max_length=255)

    start_latitude = models.FloatField()
    start_longitude = models.FloatField()
    finish_latitude = models.FloatField()
    finish_longitude = models.FloatField()

    total_distance_miles = models.FloatField()
    total_duration_seconds = models.FloatField()
    total_fuel_cost_usd = models.DecimalField(max_digits=10, decimal_places=2)
    total_gallons = models.FloatField()

    # Raw route geometry as a list of [lat, lon] pairs (GeoJSON-ish, simplified).
    route_geometry = models.JSONField()

    # List of chosen fuel stops, each a dict with station info + purchase details.
    fuel_stops = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.start_location} -> {self.finish_location} ({self.id})"
