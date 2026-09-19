from django.urls import path

from routing import views

app_name = "routing"

urlpatterns = [
    path("", views.api_root, name="api-root"),
    path("route-plans/", views.RoutePlanView.as_view(), name="route-plan-create"),
    path("route-plans/<uuid:plan_id>/", views.RoutePlanDetailView.as_view(), name="route-plan-detail"),
    path("route-plans/<uuid:plan_id>/map/", views.route_plan_map_view, name="route-plan-map"),
]
