"""합성 구간으로 기존 산술 동작을 검증한다. 실제 법정 세율 검증은 아니다."""

from decimal import Decimal

import pytest

from app.services.calculator.brackets import apply_progressive_tax


@pytest.mark.parametrize(
    ("taxable", "expected"),
    [
        (-1, (0, "0%")),
        (0, (0, "0%")),
        (1, (0, "10%")),
        (99, (9, "10%")),
        (100, (10, "10%")),
        (101, (10, "20%")),
        (200, (30, "20%")),
        (201, (30, "30%")),
        (250, (45, "30%")),
    ],
)
def test_progressive_boundaries_and_input_order(taxable, expected):
    brackets = [
        {"bracket_from": 100, "rate": Decimal("0.2"), "progressive_deduction": 10},
        {"bracket_from": 0, "rate": Decimal("0.1"), "progressive_deduction": 0},
        {"bracket_from": 200, "rate": Decimal("0.3"), "progressive_deduction": 30},
    ]
    before = [dict(row) for row in brackets]
    assert apply_progressive_tax(taxable, brackets) == expected
    assert brackets == before


def test_empty_brackets():
    assert apply_progressive_tax(100, []) == (0, "0%")


def test_single_rate():
    brackets = [{"bracket_from": 0, "rate": 0.4, "progressive_deduction": 0}]
    assert apply_progressive_tax(123, brackets) == (49, "40%")


def test_negative_tax_is_clamped():
    brackets = [{"bracket_from": 0, "rate": 0.1, "progressive_deduction": 50}]
    assert apply_progressive_tax(100, brackets) == (0, "10%")
