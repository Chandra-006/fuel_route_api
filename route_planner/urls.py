"""
route_planner/urls.py
----------------------
URL configuration for the route_planner app.
Maps the /plan/ endpoint to the RoutePlannerView.
"""

from django.urls import path
from .views import RoutePlannerView

urlpatterns = [
    # POST /api/route/plan/
    # This is the only endpoint in the app
    path('plan/', RoutePlannerView.as_view(), name='route-planner'),
]


# =============================================================================
# fuel_route/urls.py  (main project URLs — paste this in fuel_route/urls.py)
# =============================================================================
# from django.contrib import admin
# from django.urls import path, include
#
# urlpatterns = [
#     path('admin/', admin.site.urls),
#
#     # All route_planner URLs are prefixed with /api/route/
#     # So the full endpoint becomes: POST /api/route/plan/
#     path('api/route/', include('route_planner.urls')),
# ]