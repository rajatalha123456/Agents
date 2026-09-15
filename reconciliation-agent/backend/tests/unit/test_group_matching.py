from decimal import Decimal
from datetime import date

import pytest

from core.config import GroupMatchGuardrails
from core.matching.exact import MatchRecord
from core.matching.grouping import CandidateExplosion, find_group_matches


def rec(id_, side, amount, direction="CR"):
    return MatchRecord(id_, side, "account", "USD", Decimal(amount), direction, date(2026, 9, 1), "REF")


def test_one_credit_equals_three_gl_lines_nets_zero():
    side_a = [rec("a1", "SOURCE_A", "300.00", "CR")]
    side_b = [rec("b1", "SOURCE_B", "100.00", "DR"), rec("b2", "SOURCE_B", "100.00", "DR"), rec("b3", "SOURCE_B", "100.00", "DR")]
    matches = find_group_matches(side_a, side_b, Decimal("0.01"), GroupMatchGuardrails())
    assert len(matches) == 1
    assert set(matches[0].side_a_ids) == {"a1"}
    assert set(matches[0].side_b_ids) == {"b1", "b2", "b3"}
    assert abs(matches[0].net_amount) <= Decimal("0.01")


def test_no_subset_sums_to_zero_returns_empty():
    side_a = [rec("a1", "SOURCE_A", "300.00", "CR")]
    side_b = [rec("b1", "SOURCE_B", "50.00", "DR"), rec("b2", "SOURCE_B", "60.00", "DR")]
    assert find_group_matches(side_a, side_b, Decimal("0.01"), GroupMatchGuardrails()) == []


def test_candidate_pool_over_cap_raises_explosion():
    guardrails = GroupMatchGuardrails(max_candidate_pool_per_group=2)
    side_a = [rec("a1", "SOURCE_A", "10.00")]
    side_b = [rec("b1", "SOURCE_B", "5.00"), rec("b2", "SOURCE_B", "5.00")]
    with pytest.raises(CandidateExplosion):
        find_group_matches(side_a, side_b, Decimal("0.01"), guardrails)


def test_records_not_reused_across_groups():
    side_a = [rec("a1", "SOURCE_A", "100.00", "CR"), rec("a2", "SOURCE_A", "100.00", "CR")]
    side_b = [rec("b1", "SOURCE_B", "100.00", "DR"), rec("b2", "SOURCE_B", "100.00", "DR")]
    matches = find_group_matches(side_a, side_b, Decimal("0.01"), GroupMatchGuardrails())
    used_a = [id_ for m in matches for id_ in m.side_a_ids]
    used_b = [id_ for m in matches for id_ in m.side_b_ids]
    assert len(used_a) == len(set(used_a))
    assert len(used_b) == len(set(used_b))
