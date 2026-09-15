from decimal import Decimal

EXPECTED = "expected"
BEST = "best"
WORST = "worst"

SCENARIOS = [BEST, EXPECTED, WORST]

SCENARIO_MULTIPLIERS = {
    BEST: {
        "income_mult": Decimal("1.10"),
        "withdrawal_mult": Decimal("0.90"),
        "maturity_growth_mult": Decimal("1.5"),
        "apply_maturity_shock": False,
    },
    EXPECTED: {
        "income_mult": Decimal("1.00"),
        "withdrawal_mult": Decimal("1.00"),
        "maturity_growth_mult": Decimal("0"),
        "apply_maturity_shock": False,
    },
    WORST: {
        "income_mult": Decimal("0.90"),
        "withdrawal_mult": Decimal("1.15"),
        "maturity_growth_mult": Decimal("0"),
        "apply_maturity_shock": True,
    },
}
