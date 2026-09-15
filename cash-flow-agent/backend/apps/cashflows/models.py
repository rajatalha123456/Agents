from django.conf import settings
from django.db import models


class CashPosition(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cash_position")
    bank_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    available_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    emergency_fund = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    liquidity_threshold = models.DecimalField(
        max_digits=14, decimal_places=2, default=10000,
        help_text="Alert when projected liquidity falls below this amount.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_current_cash(self):
        return self.bank_balance + self.available_cash

    def __str__(self):
        return f"CashPosition({self.user_id})"


class CashFlowItem(models.Model):
    class Kind(models.TextChoices):
        CONTRIBUTION = "contribution", "Contribution"
        WITHDRAWAL = "withdrawal", "Withdrawal"
        PAYOUT = "payout", "Payout"

    class Frequency(models.TextChoices):
        ONE_TIME = "one_time", "One-time"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        YEARLY = "yearly", "Yearly"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cashflow_items")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField()
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.ONE_TIME)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.kind}:{self.name} ({self.user_id})"
