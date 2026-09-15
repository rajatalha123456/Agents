from django.conf import settings
from django.db import models


class Asset(models.Model):
    class AssetType(models.TextChoices):
        CASH = "cash", "Cash"
        SAVINGS = "savings", "Savings Account"
        STOCKS = "stocks", "Stocks"
        BONDS = "bonds", "Bonds"
        MUTUAL_FUNDS = "mutual_funds", "Mutual Funds"
        ETFS = "etfs", "ETFs"
        FIXED_DEPOSIT = "fixed_deposit", "Fixed Deposit"
        REAL_ESTATE = "real_estate", "Real Estate"
        CRYPTO = "crypto", "Crypto"
        OTHER = "other", "Other Investments"

    class LiquidityLevel(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assets")
    name = models.CharField(max_length=255)
    asset_type = models.CharField(max_length=20, choices=AssetType.choices)
    current_value = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    liquidity_level = models.CharField(max_length=10, choices=LiquidityLevel.choices)
    expected_return = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    maturity_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.user_id})"
