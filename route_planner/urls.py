from django.urls import path
from .views import RoutePlannerView

urlpatterns = [
    path('plan/', RoutePlannerView.as_view(), name='route-planner'),
]