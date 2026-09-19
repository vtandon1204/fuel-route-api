# Fuel Route Optimizer API

A Django + DRF API that plans a road trip between two US locations and
figures out the cheapest way to fuel it, given a 500-mile vehicle range and
10 MPG fuel efficiency.

**POST a start and finish location → get back:**
- The driving route (distance, duration, full geometry)
- The optimal (cheapest, feasible) set of fuel stops along the way
- The total estimated fuel cost for the trip
- A link to an actual map you can open in a browser

---

## Quickstart

```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt

python manage.py migrate
python manage.py load_fuel_prices   # one-time: loads + geocodes data/fuel_prices.csv

python manage.py runserver
```

Then:

```bash
curl -X POST http://127.0.0.1:8000/api/route-plans/ \
  -H "Content-Type: application/json" \
  -d '{"start_location": "Los Angeles, CA", "finish_location": "Chicago, IL"}'
```

Open the `map_url` from the response in a browser to see the route + fuel
stops plotted on an OpenStreetMap map.

### Docker, if you'd rather not set up a venv

```bash
docker compose up --build
```

### Running tests

```bash
python manage.py test routing -v 2
```

16 tests, all mocking the external geocoding/routing calls (no network
needed to run them) - unit tests for the distance/projection math, unit
tests for the fuel-stop optimizer's DP (including a case that specifically
checks it doesn't fall into the "greedy" trap of always using the nearest
station), and integration tests against the actual HTTP endpoints.

---

## API

### `POST /api/route-plans/`

**Request**
```json
{
  "start_location": "Los Angeles, CA",
  "finish_location": "Chicago, IL"
}
```
Accepts city/state, full addresses, or landmark names - anything
[Nominatim](https://nominatim.openstreetmap.org) can resolve within the US.

**Response** (`201 Created`)
```json
{
  "id": "5f0b8b3e-...-9c2a",
  "start_location": "Los Angeles, California, United States",
  "finish_location": "Chicago, Illinois, United States",
  "start_latitude": 34.0537,
  "start_longitude": -118.2427,
  "finish_latitude": 41.8757,
  "finish_longitude": -87.6243,
  "total_distance_miles": 2015.4,
  "total_duration_seconds": 108320,
  "total_fuel_cost_usd": "465.32",
  "total_gallons": 154.2,
  "route_geometry": [[34.0537, -118.2427], ["..."], [41.8757, -87.6243]],
  "fuel_stops": [
    {
      "station_name": "PILOT TRAVEL CENTER #1243",
      "address": "I-40, EXIT 119",
      "city": "Winslow",
      "state": "AZ",
      "price_per_gallon": 3.226,
      "latitude": 35.02,
      "longitude": -110.7,
      "mile_marker": 465.6,
      "gallons_purchased": 21.7,
      "cost_usd": 70.0
    }
  ],
  "map_url": "http://127.0.0.1:8000/api/route-plans/5f0b8b3e-.../map/",
  "created_at": "2026-09-19T12:00:00Z"
}
```

| Status | Meaning |
|---|---|
| `201` | Plan created |
| `400` | Missing/invalid `start_location` or `finish_location` |
| `422` | A location couldn't be geocoded, or no drivable route / feasible fuel plan exists |

### `GET /api/route-plans/<id>/`
Re-fetches a previously computed plan. No external API calls at all.

### `GET /api/route-plans/<id>/map/`
An HTML page (Leaflet + OpenStreetMap tiles, no key needed) rendering the
route and fuel stops. This is the "map" deliverable - open it in a browser.

A ready-to-import Postman collection is at `postman/fuel-route-api.postman_collection.json`.

---

## Architecture

```
routing/
├── models.py                  FuelStation, RoutePlan
├── serializers.py             DRF request/response shaping
├── views.py                   POST/GET endpoints + the map HTML view
├── urls.py
├── templates/routing/map.html Leaflet map template
├── management/commands/
│   └── load_fuel_prices.py    one-time CSV load + offline geocoding
├── services/
│   ├── geocoding.py           Nominatim wrapper (cached)
│   ├── osrm.py                OSRM routing wrapper (cached)
│   ├── geo_utils.py           haversine, route decimation, point projection
│   ├── fuel_optimizer.py      the actual optimization algorithm
│   └── route_planner.py       orchestrates geocode -> route -> optimize
└── tests/
```

## Design decisions & trade-offs

**Minimizing external API calls (the assignment's main constraint).**
A request makes at most 3 external calls: geocode `start_location`,
geocode `finish_location`, and one call to OSRM for the route. All three
are cached (by normalized query / rounded coordinates), so repeat requests
for the same trip make zero external calls. The ~8,000 fuel station
coordinates are **never** geocoded live - see below.

**Why city-level station coordinates, resolved offline.**
`fuel_prices.csv` only has city/state, not lat/lon. Geocoding all ~8,000
rows live (or even once at server startup) against a rate-limited free API
would be slow and fragile. Instead, `load_fuel_prices` resolves each
station's city against a bundled offline lookup table of ~29,700 US cities
(`data/us_cities.csv`, see `data/README.md`) at data-load time - a one-time,
non-request-path operation. ~92% of stations resolve to coordinates; the
rest (mostly Canadian entries present in the source file) are simply never
route candidates. This is a deliberate accuracy/practicality trade-off:
station positions are city centers, not exact pump GPS coordinates. Good
enough to find "a station near mile 465 of the route," not good enough for
turn-by-turn pump-level directions.

**Choosing fuel stops: a real optimization, not a greedy heuristic.**
This is the classic "gas station on a line" problem. `fuel_optimizer.py`
finds every station within `FUEL_STATION_CORRIDOR_MILES` (default 5mi) of
the route, projects each onto a "mile marker" position along it, then runs
a dynamic program over those mile-ordered candidates: `dp[j]` = cheapest
way to reach station/finish `j`, considering every earlier reachable
station `i` (`dp[i] + cost(i→j)`), where an edge is only valid if the gap
is within the vehicle's effective range. Because candidates are sorted by
position, this is a single left-to-right pass, and it provably finds the
*minimum-cost* feasible sequence of stops - not just "always refuel at the
nearest station," which can be significantly more expensive (see
`test_prefers_cheaper_distant_station_over_pricier_near_one` for a
constructed example).

**Fuel cost accounting.** The vehicle is assumed to depart with a full
tank (no cost charged for that first tank), and "total fuel cost" is the
sum of `gallons bought x price` at each chosen stop. This is the standard
interpretation for this kind of exercise; it's called out here explicitly
because the prompt is genuinely ambiguous on it.

**Safety margin.** A 25-mile buffer (`VEHICLE_RANGE_SAFETY_MARGIN_MILES`)
is subtracted from the 500-mile max range before planning, so a stop is
never scheduled right at the theoretical empty-tank line - both realistic
(nobody drives to literally zero) and a hedge against the route-distance
vs. straight-line-projection approximation described above.

**Performance.** The corridor search (comparing every candidate station's
position to the route) is vectorized with numpy rather than nested Python
loops - on a simulated 2,700-mile cross-country route against the full
station table, it runs in well under 100ms; the DP itself is sub-millisecond.

**Why OSRM + Nominatim.** Both are free, keyless, public OpenStreetMap-based
services (`router.project-osrm.org`, `nominatim.openstreetmap.org`) -
satisfies "find a free API yourself" without requiring the reviewer to
provision any credentials to run this project.

## Known limitations

- The public OSRM/Nominatim demo servers are rate-limited and not meant for
  production load; for real use, self-host OSRM or use a paid provider
  (the code only needs `OSRM_BASE_URL`/`NOMINATIM_BASE_URL` changed).
- Station coordinates are city-center approximations (see above) - the
  corridor search can occasionally miss a station that's genuinely near the
  route but whose city center isn't, or vice versa.
- If a stretch of route has no fuel station within the corridor and it's
  longer than the vehicle's effective range, the API returns `422` rather
  than guessing - this is a real limitation of a 5-mile search corridor
  against a finite price list, not a bug.
- SQLite + a file-based cache are used for simplicity; swap for
  Postgres/Redis for a real deployment.

## Assumptions (from the assignment spec)

- USA only, vehicle range 500 miles, 10 MPG, fuel prices from the provided CSV.
- "Optimal" = lowest total cost, subject to never running out of fuel.
