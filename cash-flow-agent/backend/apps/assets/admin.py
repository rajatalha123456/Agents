from django.contrib import admin

from .models import Asset


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "asset_type", "current_value", "liquidity_level", "maturity_date")
    list_filter = ("asset_type", "liquidity_level")
