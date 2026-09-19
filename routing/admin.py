from django.contrib import admin

from routing.models import FuelStation, RoutePlan


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "state", "price_per_gallon", "latitude", "longitude")
    list_filter = ("state",)
    search_fields = ("name", "city", "address")


@admin.register(RoutePlan)
class RoutePlanAdmin(admin.ModelAdmin):
    list_display = ("id", "start_location", "finish_location", "total_distance_miles", "total_fuel_cost_usd", "created_at")
    readonly_fields = [f.name for f in RoutePlan._meta.fields]
