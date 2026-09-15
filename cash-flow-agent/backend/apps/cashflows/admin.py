from django.contrib import admin

from .models import CashFlowItem, CashPosition


@admin.register(CashPosition)
class CashPositionAdmin(admin.ModelAdmin):
    list_display = ("user", "bank_balance", "available_cash", "emergency_fund", "liquidity_threshold")


@admin.register(CashFlowItem)
class CashFlowItemAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "kind", "amount", "start_date", "frequency")
    list_filter = ("kind", "frequency")
