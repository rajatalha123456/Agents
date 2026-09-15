import calendar
from datetime import date, timedelta
from decimal import Decimal

from apps.assets.models import Asset
from apps.cashflows.models import CashFlowItem, CashPosition

from .scenarios import SCENARIO_MULTIPLIERS


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def expand_recurrence(item, range_start: date, range_end: date):
    """Return list of (date, amount) occurrences of a cash-flow item within [range_start, range_end)."""
    occurrences = []
    cursor = item.start_date
    horizon_cap = range_end
    end_cap = item.end_date or horizon_cap

    if item.frequency == CashFlowItem.Frequency.ONE_TIME:
        if range_start <= cursor < range_end:
            occurrences.append((cursor, item.amount))
        return occurrences

    step_weeks = {"weekly": 1}
    guard = 0
    while cursor < range_end and cursor <= end_cap and guard < 2000:
        guard += 1
        if cursor >= range_start:
            occurrences.append((cursor, item.amount))
        if item.frequency == CashFlowItem.Frequency.WEEKLY:
            cursor = cursor + timedelta(weeks=1)
        elif item.frequency == CashFlowItem.Frequency.MONTHLY:
            cursor = add_months(cursor, 1)
        elif item.frequency == CashFlowItem.Frequency.QUARTERLY:
            cursor = add_months(cursor, 3)
        elif item.frequency == CashFlowItem.Frequency.YEARLY:
            cursor = add_months(cursor, 12)
        else:
            break
    return occurrences


def build_monthly_buckets(user, horizon_months=12, scenario="expected", extra_item=None):
    cash_position, _ = CashPosition.objects.get_or_create(user=user)
    items = list(CashFlowItem.objects.filter(user=user))
    if extra_item is not None:
        items.append(extra_item)
    assets = list(Asset.objects.filter(user=user, maturity_date__isnull=False))

    mult = SCENARIO_MULTIPLIERS[scenario]
    today = date.today()
    opening = cash_position.total_current_cash

    buckets = []
    for i in range(horizon_months):
        period_start = add_months(today, i)
        period_end = add_months(today, i + 1)

        contributions_total = Decimal("0")
        payouts_total = Decimal("0")
        withdrawals_total = Decimal("0")
        maturities_total = Decimal("0")
        maturing_assets = []

        for item in items:
            for _, amount in expand_recurrence(item, period_start, period_end):
                if item.kind == CashFlowItem.Kind.CONTRIBUTION:
                    contributions_total += amount * mult["income_mult"]
                elif item.kind == CashFlowItem.Kind.PAYOUT:
                    payouts_total += amount * mult["income_mult"]
                elif item.kind == CashFlowItem.Kind.WITHDRAWAL:
                    withdrawals_total += amount * mult["withdrawal_mult"]

        for asset in assets:
            if period_start <= asset.maturity_date < period_end:
                value = asset.current_value
                if mult["maturity_growth_mult"] > 0:
                    value += asset.current_value * (asset.expected_return / Decimal("100")) * mult["maturity_growth_mult"]
                if mult["apply_maturity_shock"] and asset.liquidity_level in (Asset.LiquidityLevel.MEDIUM, Asset.LiquidityLevel.LOW):
                    value *= Decimal("0.9")
                maturities_total += value
                maturing_assets.append({"id": asset.id, "name": asset.name, "amount": value})

        inflow = contributions_total + payouts_total + maturities_total
        outflow = withdrawals_total
        closing = opening + inflow - outflow

        buckets.append({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "label": period_start.strftime("%b %Y"),
            "opening_cash": opening,
            "contributions": contributions_total,
            "payouts": payouts_total,
            "asset_maturities": maturities_total,
            "maturing_assets": maturing_assets,
            "withdrawals": withdrawals_total,
            "inflow": inflow,
            "outflow": outflow,
            "closing_cash": closing,
        })
        opening = closing

    return buckets
