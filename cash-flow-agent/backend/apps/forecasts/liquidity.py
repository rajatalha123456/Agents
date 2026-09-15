from decimal import Decimal

from apps.assets.models import Asset
from apps.cashflows.models import CashPosition

LIQUIDITY_WEIGHTS = {
    Asset.LiquidityLevel.HIGH: Decimal("1.0"),
    Asset.LiquidityLevel.MEDIUM: Decimal("0.6"),
    Asset.LiquidityLevel.LOW: Decimal("0.2"),
}


def band_for_score(score: int) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Moderate Risk"
    return "High Risk"


def compute_liquidity(user):
    cash_position, _ = CashPosition.objects.get_or_create(user=user)
    assets = list(Asset.objects.filter(user=user))

    current_cash = cash_position.total_current_cash
    total_assets_value = sum((a.current_value for a in assets), Decimal("0"))
    total_value = current_cash + total_assets_value

    liquid_value = current_cash
    for asset in assets:
        liquid_value += asset.current_value * LIQUIDITY_WEIGHTS[asset.liquidity_level]

    score = 0 if total_value == 0 else int(round((liquid_value / total_value) * 100))
    score = max(0, min(100, score))

    return {
        "score": score,
        "band": band_for_score(score),
        "current_cash": current_cash,
        "total_assets_value": total_assets_value,
        "total_liquid_value": liquid_value,
        "total_value": total_value,
    }
