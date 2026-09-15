from rest_framework import serializers

from .models import CashFlowItem, CashPosition


class CashPositionSerializer(serializers.ModelSerializer):
    total_current_cash = serializers.ReadOnlyField()

    class Meta:
        model = CashPosition
        fields = [
            "id", "bank_balance", "available_cash", "emergency_fund",
            "liquidity_threshold", "total_current_cash", "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]


class CashFlowItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowItem
        fields = [
            "id", "kind", "name", "amount", "start_date",
            "frequency", "end_date", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
