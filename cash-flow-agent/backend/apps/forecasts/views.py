from datetime import date

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assets.models import Asset
from apps.cashflows.models import CashFlowItem, CashPosition

from .alerts import generate_alerts
from .engine import build_monthly_buckets
from .liquidity import compute_liquidity
from .scenarios import EXPECTED, SCENARIOS


def _parse_horizon(request, default=12):
    try:
        horizon = int(request.query_params.get("horizon", default))
    except (TypeError, ValueError):
        horizon = default
    return max(1, min(horizon, 60))


class ForecastView(APIView):
    def get(self, request):
        horizon = _parse_horizon(request)
        scenario = request.query_params.get("scenario", EXPECTED)
        if scenario not in SCENARIOS:
            scenario = EXPECTED

        buckets = build_monthly_buckets(request.user, horizon_months=horizon, scenario=scenario)
        return Response({
            "horizon_months": horizon,
            "scenario": scenario,
            "buckets": buckets,
            "liquidity": compute_liquidity(request.user),
            "alerts": generate_alerts(request.user, buckets),
        })


class ForecastCompareView(APIView):
    def get(self, request):
        horizon = _parse_horizon(request)
        result = {}
        for scenario in SCENARIOS:
            buckets = build_monthly_buckets(request.user, horizon_months=horizon, scenario=scenario)
            result[scenario] = buckets
        return Response({"horizon_months": horizon, "scenarios": result})


class DashboardSummaryView(APIView):
    def get(self, request):
        user = request.user
        liquidity = compute_liquidity(user)
        buckets = build_monthly_buckets(user, horizon_months=6, scenario=EXPECTED)
        alerts = generate_alerts(user, buckets)

        today = date.today()
        upcoming_withdrawals = list(
            CashFlowItem.objects.filter(user=user, kind=CashFlowItem.Kind.WITHDRAWAL, start_date__gte=today)
            .order_by("start_date")[:5]
            .values("id", "name", "amount", "start_date", "frequency")
        )
        upcoming_payouts = list(
            CashFlowItem.objects.filter(user=user, kind=CashFlowItem.Kind.PAYOUT, start_date__gte=today)
            .order_by("start_date")[:5]
            .values("id", "name", "amount", "start_date", "frequency")
        )
        upcoming_contributions = list(
            CashFlowItem.objects.filter(user=user, kind=CashFlowItem.Kind.CONTRIBUTION, start_date__gte=today)
            .order_by("start_date")[:5]
            .values("id", "name", "amount", "start_date", "frequency")
        )
        upcoming_maturities = list(
            Asset.objects.filter(user=user, maturity_date__gte=today)
            .order_by("maturity_date")[:5]
            .values("id", "name", "current_value", "maturity_date")
        )

        return Response({
            "current_cash": liquidity["current_cash"],
            "total_assets": liquidity["total_assets_value"],
            "total_liquid_assets": liquidity["total_liquid_value"],
            "liquidity_score": liquidity["score"],
            "liquidity_band": liquidity["band"],
            "six_month_forecast": buckets,
            "upcoming_withdrawals": upcoming_withdrawals,
            "upcoming_payouts": upcoming_payouts,
            "upcoming_contributions": upcoming_contributions,
            "upcoming_maturities": upcoming_maturities,
            "alerts": alerts,
        })
