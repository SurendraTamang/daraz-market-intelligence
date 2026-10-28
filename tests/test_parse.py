import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from daraz.utils import parse_sold_count, to_float, to_int  # noqa: E402


def test_parse_sold_count():
    assert parse_sold_count("2.7K sold") == 2700
    assert parse_sold_count("10K+ sold") == 10000
    assert parse_sold_count("2M sold") == 2_000_000
    assert parse_sold_count("500 sold") == 500
    assert parse_sold_count("1 sold") == 1
    assert parse_sold_count("") == 0
    assert parse_sold_count(None) == 0
    assert parse_sold_count("sold") == 0


def test_to_float():
    assert to_float("685") == 685.0
    assert to_float("24% Off") == 24.0
    assert to_float("4.6477") == 4.6477
    assert to_float(None) is None
    assert to_float("") is None


def test_to_int():
    assert to_int("457") == 457
    assert to_int(None) is None


if __name__ == "__main__":
    test_parse_sold_count()
    test_to_float()
    test_to_int()
    print("ok")
