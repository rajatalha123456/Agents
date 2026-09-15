from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CashFlowItemViewSet, CashPositionView

router = DefaultRouter()
router.register("items", CashFlowItemViewSet, basename="cashflow-item")

urlpatterns = [
    path("position/", CashPositionView.as_view(), name="cash-position"),
] + router.urls
