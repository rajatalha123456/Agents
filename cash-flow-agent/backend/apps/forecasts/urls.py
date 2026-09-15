from django.urls import path

from .views import DashboardSummaryView, ForecastCompareView, ForecastView

urlpatterns = [
    path("forecast/", ForecastView.as_view(), name="forecast"),
    path("forecast/compare/", ForecastCompareView.as_view(), name="forecast-compare"),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="dashboard-summary"),
]
