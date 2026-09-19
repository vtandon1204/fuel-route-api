from rest_framework import serializers

from routing.models import RoutePlan


class RoutePlanRequestSerializer(serializers.Serializer):
    start_location = serializers.CharField(max_length=255, trim_whitespace=True)
    finish_location = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_start_location(self, value):
        if not value.strip():
            raise serializers.ValidationError("start_location cannot be blank.")
        return value

    def validate_finish_location(self, value):
        if not value.strip():
            raise serializers.ValidationError("finish_location cannot be blank.")
        return value


class FuelStopSerializer(serializers.Serializer):
    station_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    price_per_gallon = serializers.FloatField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    mile_marker = serializers.FloatField()
    gallons_purchased = serializers.FloatField()
    cost_usd = serializers.FloatField()


class RoutePlanSerializer(serializers.ModelSerializer):
    fuel_stops = FuelStopSerializer(many=True)
    map_url = serializers.SerializerMethodField()

    class Meta:
        model = RoutePlan
        fields = [
            "id",
            "start_location",
            "finish_location",
            "start_latitude",
            "start_longitude",
            "finish_latitude",
            "finish_longitude",
            "total_distance_miles",
            "total_duration_seconds",
            "total_fuel_cost_usd",
            "total_gallons",
            "route_geometry",
            "fuel_stops",
            "map_url",
            "created_at",
        ]

    def get_map_url(self, obj):
        request = self.context.get("request")
        path = f"/api/route-plans/{obj.id}/map/"
        return request.build_absolute_uri(path) if request else path
