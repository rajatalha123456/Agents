"""AICPA MUS misstatement evaluation / projection.

Certainty items contribute their actual misstatement. Other projectable
items contribute a tainting-weighted share of the interval. Judgmental
items are never projected. Understatements are never netted against
overstatements.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .selection import SelectionBasis
from .statistics import reliability_factor

__test__ = False  # module-level guard is irrelevant here; see TestedItem


@dataclass(frozen=True)
class TestedItem:
    __test__ = False  # prevent pytest from collecting this as a test class

    item_id: str
    book_value: float
    audit_value: float
    selection_basis: SelectionBasis

    @property
    def misstatement(self) -> float:
        return self.book_value - self.audit_value

    @property
    def tainting(self) -> float:
        if self.book_value == 0:
            return 0.0
        return self.misstatement / self.book_value


@dataclass(frozen=True)
class ProjectionResult:
    known_misstatement: float
    projected_misstatement: float
    most_likely_misstatement: float
    basic_precision: float
    incremental_allowance: float
    upper_misstatement_limit: float
    tolerable_misstatement: float
    projected_understatement: float
    judgmental_known_misstatement: float
    conclusion: str
    conclusion_basis: str
    projectable_count: int
    certainty_count: int
    judgmental_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_workpaper(self) -> dict:
        return {
            "known_misstatement": round(self.known_misstatement, 2),
            "projected_misstatement": round(self.projected_misstatement, 2),
            "most_likely_misstatement": round(self.most_likely_misstatement, 2),
            "basic_precision": round(self.basic_precision, 2),
            "incremental_allowance": round(self.incremental_allowance, 2),
            "allowance_for_sampling_risk": round(
                self.basic_precision + self.incremental_allowance, 2
            ),
            "upper_misstatement_limit": round(self.upper_misstatement_limit, 2),
            "tolerable_misstatement": round(self.tolerable_misstatement, 2),
            "projected_understatement": round(self.projected_understatement, 2),
            "judgmental_known_misstatement": round(
                self.judgmental_known_misstatement, 2
            ),
            "conclusion": self.conclusion,
            "conclusion_basis": self.conclusion_basis,
            "projectable_count": self.projectable_count,
            "certainty_count": self.certainty_count,
            "judgmental_count": self.judgmental_count,
            "warnings": list(self.warnings),
        }


_CONCLUSION_BASIS = {
    "ACCEPT": (
        "Upper misstatement limit does not exceed tolerable misstatement. "
        "The sample supports concluding the population is not materially "
        "misstated."
    ),
    "REJECT": (
        "Most likely misstatement exceeds tolerable misstatement. The "
        "population is concluded to be materially misstated based on the "
        "sample evidence."
    ),
    "INCONCLUSIVE": (
        "Most likely misstatement is within tolerable misstatement but the "
        "upper misstatement limit exceeds it. Extend testing, request "
        "adjustment of identified misstatements, or apply alternative "
        "procedures before concluding."
    ),
    "NO_PROJECTABLE_ITEMS": (
        "No projectable (statistical) items were tested; no statistical "
        "conclusion can be drawn on the population."
    ),
}


def tested_items_from_frame(
    frame,
    item_id_col: str = "item_id",
    book_value_col: str = "_amount",
    audit_value_col: str = "audit_value",
    basis_col: str = "_selection_basis",
) -> list[TestedItem]:
    items = []
    for _, row in frame.iterrows():
        items.append(
            TestedItem(
                item_id=row[item_id_col],
                book_value=float(row[book_value_col]),
                audit_value=float(row[audit_value_col]),
                selection_basis=SelectionBasis(row[basis_col]),
            )
        )
    return items


def project_misstatement(
    tested: list[TestedItem],
    sampling_interval: float,
    confidence_level: float,
    tolerable_misstatement: float,
) -> ProjectionResult:
    warnings: list[str] = []

    certainty = [t for t in tested if t.selection_basis == SelectionBasis.MUS_CERTAINTY]
    projectable_noncertainty = [
        t for t in tested if t.selection_basis.projectable
        and t.selection_basis != SelectionBasis.MUS_CERTAINTY
    ]
    judgmental = [t for t in tested if not t.selection_basis.projectable]

    if judgmental:
        warnings.append(
            f"{len(judgmental)} judgmental item(s) excluded from statistical "
            "projection; their known misstatement is reported separately."
        )

    judgmental_known = sum(t.misstatement for t in judgmental)

    known_certainty = sum(t.misstatement for t in certainty)

    understatement_items = [t for t in tested if t.misstatement < 0]
    if understatement_items:
        warnings.append(
            f"{len(understatement_items)} understatement(s) found; these are "
            "projected separately and never netted against overstatements. "
            "MUS is biased toward overstatements by design (proportional to "
            "recorded value) and systematically under-detects understated "
            "items -- consider a procedure directed at completeness."
        )
    for t in tested:
        if t.book_value > 0 and t.audit_value < 0:
            warnings.append(
                f"item {t.item_id}: audited value is negative relative to "
                "book value; review for reversed sign or misclassification."
            )

    overstatement_noncertainty = [t for t in projectable_noncertainty if t.tainting > 0]
    understatement_noncertainty = [t for t in projectable_noncertainty if t.tainting < 0]

    def capped_tainting(t: TestedItem) -> float:
        return min(t.tainting, 1.0) if t.tainting > 0 else t.tainting

    projected_over = sum(
        capped_tainting(t) * sampling_interval for t in overstatement_noncertainty
    )
    projected_under = sum(
        abs(capped_tainting(t)) * sampling_interval for t in understatement_noncertainty
    )

    projected_misstatement = projected_over

    basic_prec = reliability_factor(0, confidence_level) * sampling_interval

    ranked = sorted(overstatement_noncertainty, key=lambda t: t.tainting, reverse=True)
    incremental_allowance = 0.0
    for i, t in enumerate(ranked, start=1):
        rf_i = reliability_factor(i, confidence_level)
        rf_prev = reliability_factor(i - 1, confidence_level)
        increment = max(rf_i - rf_prev - 1.0, 0.0)
        incremental_allowance += increment * min(t.tainting, 1.0) * sampling_interval

    known = known_certainty
    most_likely = known + projected_misstatement
    uml = most_likely + basic_prec + incremental_allowance

    projectable_count = len(certainty) + len(projectable_noncertainty)
    if projectable_count == 0:
        conclusion = "INCONCLUSIVE"
        conclusion_basis = _CONCLUSION_BASIS["NO_PROJECTABLE_ITEMS"]
        warnings.append(_CONCLUSION_BASIS["NO_PROJECTABLE_ITEMS"])
    elif uml <= tolerable_misstatement:
        conclusion = "ACCEPT"
        conclusion_basis = _CONCLUSION_BASIS["ACCEPT"]
    elif most_likely > tolerable_misstatement:
        conclusion = "REJECT"
        conclusion_basis = _CONCLUSION_BASIS["REJECT"]
    else:
        conclusion = "INCONCLUSIVE"
        conclusion_basis = _CONCLUSION_BASIS["INCONCLUSIVE"]

    return ProjectionResult(
        known_misstatement=known,
        projected_misstatement=projected_misstatement,
        most_likely_misstatement=most_likely,
        basic_precision=basic_prec,
        incremental_allowance=incremental_allowance,
        upper_misstatement_limit=uml,
        tolerable_misstatement=tolerable_misstatement,
        projected_understatement=projected_under,
        judgmental_known_misstatement=judgmental_known,
        conclusion=conclusion,
        conclusion_basis=conclusion_basis,
        projectable_count=projectable_count,
        certainty_count=len(certainty),
        judgmental_count=len(judgmental),
        warnings=tuple(warnings),
    )
