from datetime import date
from decimal import Decimal

from apps.assets.models import Asset
from apps.cashflows.models import CashFlowItem, CashPosition

LARGE_WITHDRAWAL_RATIO = Decimal("0.20")
MATURITY_LOOKAHEAD_DAYS = 60


def generate_alerts(user, buckets):
    cash_position, _ = CashPosition.objects.get_or_create(user=user)
    current_cash = cash_position.total_current_cash
    threshold = cash_position.liquidity_threshold
    alerts = []

    low_liquidity_flagged = False
    cash_gap_flagged = False
    for bucket in buckets:
        if not low_liquidity_flagged and bucket["closing_cash"] < threshold:
            alerts.append({
                "type": "low_liquidity",
                "message": f"Projected liquidity may fall below {threshold} in {bucket['label']}.",
                "period": bucket["label"],
            })
            low_liquidity_flagged = True
        if not cash_gap_flagged and bucket["closing_cash"] < 0:
            alerts.append({
                "type": "cash_flow_gap",
                "message": f"Projected cash flow gap in {bucket['label']} — closing balance goes negative.",
                "period": bucket["label"],
            })
            cash_gap_flagged = True
        if low_liquidity_flagged and cash_gap_flagged:
            break

    if current_cash > 0:
        for item in CashFlowItem.objects.filter(user=user, kind=CashFlowItem.Kind.WITHDRAWAL):
            if item.amount > current_cash * LARGE_WITHDRAWAL_RATIO:
                alerts.append({
                    "type": "large_withdrawal",
                    "message": f"'{item.name}' of {item.amount} is a large upcoming withdrawal (over 20% of current cash).",
                    "period": item.start_date.isoformat(),
                })

    today = date.today()
    for asset in Asset.objects.filter(user=user, maturity_date__isnull=False):
        days_out = (asset.maturity_date - today).days
        if 0 <= days_out <= MATURITY_LOOKAHEAD_DAYS:
            alerts.append({
                "type": "asset_maturity",
                "message": f"Asset '{asset.name}' matures on {asset.maturity_date.isoformat()}.",
                "period": asset.maturity_date.isoformat(),
            })

    return alerts
