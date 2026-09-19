"""
One-time data-loading step (run via `python manage.py load_fuel_prices`).

This is intentionally NOT part of the request/response cycle: it reads the
provided fuel_prices.csv and enriches each row with approximate coordinates
using a bundled, offline US city/lat/lon lookup table (data/us_cities.csv,
~29,700 US cities, sourced from a public-domain dataset - see data/README.md).

Doing the city -> coordinates lookup here, once, at load time, is what lets
the live API avoid making ~8,000 geocoding calls (one per station) on every
request, or even once at startup. It only ever makes 2-3 external calls per
route-planning request (see routing/services/route_planner.py).
"""

import csv

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from routing.models import FuelStation


class Command(BaseCommand):
    help = "Load fuel station prices from data/fuel_prices.csv, geocoded via data/us_cities.csv."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing FuelStation rows before loading.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = FuelStation.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} existing FuelStation rows."))

        city_lookup = self._load_city_lookup()
        self.stdout.write(f"Loaded {len(city_lookup)} city/state coordinate lookups.")

        stations = []
        matched = 0
        unmatched = 0

        with open(settings.FUEL_PRICES_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                city = row["City"].strip()
                state = row["State"].strip().upper()
                key = (city.lower(), state)
                coords = city_lookup.get(key)

                if coords:
                    matched += 1
                else:
                    unmatched += 1

                stations.append(
                    FuelStation(
                        opis_id=int(row["OPIS Truckstop ID"]),
                        name=row["Truckstop Name"].strip(),
                        address=row["Address"].strip(),
                        city=city,
                        state=state,
                        rack_id=int(row["Rack ID"]) if row["Rack ID"] else None,
                        price_per_gallon=row["Retail Price"],
                        latitude=coords[0] if coords else None,
                        longitude=coords[1] if coords else None,
                    )
                )

        with transaction.atomic():
            FuelStation.objects.bulk_create(stations, batch_size=1000)

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(stations)} fuel stations "
                f"({matched} geocoded, {unmatched} without coordinates - "
                f"likely non-US cities in the source file, e.g. Canadian truck stops)."
            )
        )

    @staticmethod
    def _load_city_lookup() -> dict[tuple[str, str], tuple[float, float]]:
        lookup: dict[tuple[str, str], tuple[float, float]] = {}
        with open(settings.US_CITIES_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row["city"].strip().lower(), row["state"].strip().upper())
                lookup[key] = (float(row["lat"]), float(row["lon"]))
        return lookup
