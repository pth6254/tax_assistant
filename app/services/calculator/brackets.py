"""계산기별 DB 세율 구간에 공통으로 적용하는 산술 로직."""


def apply_progressive_tax(taxable: int, brackets: list[dict]) -> tuple[int, str]:
    """과세표준 × 세율 - 누진공제. 기존 구간 경계와 절사 방식을 유지한다.

    단일세율은 bracket_from=0인 구간 하나로 처리한다.
    """
    for b in sorted(brackets, key=lambda x: x['bracket_from'], reverse=True):
        if taxable > b['bracket_from']:
            tax = int(taxable * float(b['rate'])) - b['progressive_deduction']
            return max(0, tax), f"{int(float(b['rate']) * 100)}%"
    return 0, "0%"
