import pytest

from core.ingestion.parsers.base import ParseError
from core.ingestion.parsers.csv_parser import parse_csv


@pytest.mark.parametrize("content", [b"amount,amount\n10,20\n", b"amount, amount\n10,20\n", b"amount,\n10,20\n", b"amount,currency\n10,USD,extra\n"])
def test_ambiguous_or_surplus_csv_values_are_never_silently_dropped(content):
    with pytest.raises(ParseError):
        parse_csv(content)
