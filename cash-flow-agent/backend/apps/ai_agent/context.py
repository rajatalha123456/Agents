from apps.assets.models import Asset
from apps.cashflows.models import CashFlowItem
from apps.forecasts.engine import build_monthly_buckets
from apps.forecasts.liquidity import compute_liquidity
from apps.forecasts.scenarios import EXPECTED


def build_financial_context(user, horizon_months=12, scenario=EXPECTED, extra_item=None):
    buckets = build_monthly_buckets(user, horizon_months=horizon_months, scenario=scenario, extra_item=extra_item)
    liquidity = compute_liquidity(user)

    assets = list(
        Asset.objects.filter(user=user).values(
            "name", "asset_type", "current_value", "liquidity_level", "expected_return", "maturity_date"
        )
    )
    cashflow_items = list(
        CashFlowItem.objects.filter(user=user).values(
            "kind", "name", "amount", "start_date", "frequency", "end_date"
        )
    )

    return {
        "scenario": scenario,
        "horizon_months": horizon_months,
        "liquidity": liquidity,
        "assets": assets,
        "cashflow_items": cashflow_items,
        "forecast_buckets": buckets,
    }
