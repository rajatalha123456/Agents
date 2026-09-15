from rest_framework import generics, viewsets

from .models import CashFlowItem, CashPosition
from .serializers import CashFlowItemSerializer, CashPositionSerializer


class CashPositionView(generics.RetrieveUpdateAPIView):
    serializer_class = CashPositionSerializer

    def get_object(self):
        obj, _ = CashPosition.objects.get_or_create(user=self.request.user)
        return obj


class CashFlowItemViewSet(viewsets.ModelViewSet):
    serializer_class = CashFlowItemSerializer

    def get_queryset(self):
        qs = CashFlowItem.objects.filter(user=self.request.user).order_by("start_date")
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
