"""FR-14 says conflicts must NEVER be silently merged. Trusting the LLM's
self-reported `conflict_flagged` alone is risky, so this adds a cheap
deterministic backstop: if the comparison table contains any row explicitly
marked CONFLICT, OR evidence was drawn from 2+ distinct approved documents
that were never compared, force conflict_flagged / open_issues so a human
reviewer notices either way.
"""
from typing import Dict, List


def verify_conflict_flag(llm_output: Dict, distinct_document_ids: List[str]) -> Dict:
    comparison_table = llm_output.get("comparison_table") or []
    llm_says_conflict = bool(llm_output.get("conflict_flagged", False))

    table_has_conflict = any(
        str(row.get("note", "")).strip().upper() == "CONFLICT" for row in comparison_table
    )

    multiple_uncompared_sources = len(set(distinct_document_ids)) >= 2 and not comparison_table

    final_flag = llm_says_conflict or table_has_conflict

    open_issues = list(llm_output.get("open_issues") or [])
    if multiple_uncompared_sources:
        open_issues.append(
            "Evidence was drawn from multiple approved documents that were not "
            "directly compared by the model — reviewer should confirm they agree."
        )

    llm_output["conflict_flagged"] = final_flag
    llm_output["open_issues"] = open_issues
    return llm_output
