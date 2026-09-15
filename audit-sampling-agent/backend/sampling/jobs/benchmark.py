"""run_benchmark job: benchmark_ranking over stored outcomes."""
from __future__ import annotations

import uuid

import numpy as np
from sqlalchemy import select

from ..benchmark import benchmark_ranking
from ..db.audit_trail_pg import PgAuditTrail
from ..db.models import Benchmark, RiskScore
from ..db.session import tenant_session


async def run_benchmark(tenant_id: uuid.UUID, run_pk: uuid.UUID, label_col: str,
                         labels_by_item_id: dict[str, float], actor: str = "system") -> dict:
    """labels_by_item_id: confirmed-outcome labels keyed by item_id (1 = a
    confirmed finding, 0 = confirmed clean). This is the random control
    stratum's payoff -- it is how a label set is built without bias.
    """
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(RiskScore).where(RiskScore.tenant_id == tenant_id, RiskScore.run_id == run_pk)
        )
        rows = list(result.scalars())

        if not rows:
            raise ValueError(f"no risk_scores found for run {run_pk}; run risk scoring first")

        scores = np.array([float(r.risk_score) for r in rows])
        labels = np.array([labels_by_item_id.get(r.item_id, 0.0) for r in rows])

        report = benchmark_ranking(scores, labels)

        benchmark = Benchmark(
            tenant_id=tenant_id, run_id=run_pk, label_source=label_col,
            report={
                "k": report.k, "n": report.n, "findings_total": report.findings_total,
                "base_rate": report.base_rate, "precision": report.precision, "recall": report.recall,
                "lift": report.lift, "lift_ci_low": report.lift_ci_low, "lift_ci_high": report.lift_ci_high,
                "statement": report.statement(), "warnings": list(report.warnings),
            },
            verdict=report.verdict,
        )
        session.add(benchmark)
        await session.flush()

        trail = PgAuditTrail(tenant_id)
        await trail.append(session, actor=actor, action="benchmark.completed", subject=str(run_pk),
                            payload={"verdict": report.verdict})

    return {"verdict": report.verdict, "statement": report.statement()}
