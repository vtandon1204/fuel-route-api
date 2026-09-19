# Data files

### `fuel_prices.csv`
The fuel price list provided with the assessment (`fuel-prices-for-be-assessment.csv`),
copied here unmodified. Columns: OPIS Truckstop ID, Truckstop Name, Address,
City, State, Rack ID, Retail Price.

### `us_cities.csv`
A free, public-domain lookup of ~29,700 US cities with their approximate
center latitude/longitude, sourced from the
[kelvins/US-Cities-Database](https://github.com/kelvins/US-Cities-Database)
project (MIT licensed), trimmed to just `city,state,lat,lon` and de-duplicated.

This file exists so that `python manage.py load_fuel_prices` can resolve each
fuel station's *city* to approximate coordinates **once, offline, at load
time** - without making ~8,000 individual calls to a geocoding API (which
would be slow, rate-limited, and unnecessary). About 92% of the rows in
`fuel_prices.csv` match a city in this table; the rest (mostly Canadian
truck stops present in the source file, e.g. Ontario/Alberta/BC entries)
are loaded with `latitude`/`longitude` left `NULL` and are simply never
candidates for a route (the assignment scope is USA-only anyway).

**Trade-off, stated plainly:** station coordinates are city-center
approximations, not exact truck-stop GPS pins. For a take-home exercise
against a price list that only provides city/state, this is a reasonable
and clearly-documented approximation - see the "Design decisions &
trade-offs" section of the root `README.md` for the full reasoning.
