"""Explain a rejected formula plan to the planner, rule by rule.

The engine and grounding checks raise short codes. A retry that only sees
"missing_prepaid_or_balance" cannot tell what to change, so each code carries
what it means and how to fix the plan. Explanations only guide the retry; every
rule still rejects the plan the same way.
"""
from app.services.calculator.formula_engine import FormulaError

HINTS = {
    "missing_prepaid_or_balance": "outputs에 prepaid(이미 낸 세액)와 balance(추가 납부·환급액) 중 하나만 있습니다. 둘을 함께 쓰거나 둘 다 빼세요. prepaid를 쓰면 total에서 prepaid를 빼는 subtract step을 만들어 그 step을 balance로 내보내세요.",
    "balance_mismatch": "balance 값이 total-prepaid와 다릅니다. balance step을 total과 prepaid를 인수로 하는 subtract로 계산하세요.",
    "invalid_output_roles": "outputs에는 total이 정확히 한 개, prepaid와 balance는 각각 최대 한 개여야 합니다.",
    "component_total_mismatch": "component 합계가 total과 다릅니다. total을 component들을 더하는 add step으로 계산하세요.",
    "negative_tax_or_prepaid": "balance 외의 출력(total·component·prepaid)이 음수입니다. 단계의 순서와 인수를 확인하세요.",
    "invalid_output": "outputs의 step_id가 steps에 없거나 원화(KRW) 단위가 아닙니다.",
    "missing_rounding_mode": "원화 금액에 반올림 방식이 필요한 단계가 있습니다. 원문 근거가 있는 rounding을 지정하세요.",
    "rounding_non_money": "원화가 아닌 값(비율·개수)에 반올림을 지정했습니다. rounding을 none으로 두세요.",
    "money_squared": "원화끼리 곱했습니다. 금액에는 비율(ratio)이나 개수(count)를 곱하세요.",
    "incompatible_units": "단위가 맞지 않는 값을 더하거나 뺐습니다. KRW·ratio·count를 구분하세요.",
    "invalid_arity": "연산의 인수 개수가 맞지 않습니다. add·multiply·min·max는 2개 이상, subtract·divide는 2개, progressive·round는 1개입니다.",
    "invalid_division": "0으로 나누거나 허용되지 않는 나눗셈입니다.",
    "unknown_or_forward_reference": "args가 아직 정의되지 않았거나 없는 value/step ID를 참조합니다. 앞에서 정의한 ID만 쓰세요.",
    "duplicate_step": "step ID가 중복됐습니다.",
    "duplicate_value": "value ID가 중복됐습니다.",
    "duplicate_table": "table ID가 중복됐습니다.",
    "invalid_decimal": "숫자 문자열 형식이 잘못됐습니다. 금액은 원 단위 숫자, 비율은 0.14 같은 소수로 쓰세요.",
    "invalid_rate": "세율이 0~1 범위의 소수가 아닙니다.",
    "invalid_progressive_input": "progressive에는 원화 과세표준 하나와 table_id를 넘기세요.",
    "incomplete_rate_table": "세율표 구간이 과세표준을 덮지 못합니다. 필요한 구간까지 bands를 채우세요.",
    "unordered_bands": "세율표 bands를 상한 오름차순으로 정렬하세요.",
    "unbounded_middle_band": "상한 없는 구간은 마지막 구간에만 둘 수 있습니다.",
    "numeric_limit": "계산 값이 허용 범위를 벗어났습니다. 단위와 단계를 확인하세요.",
    "non_arithmetic_constant": "constant는 0, 1, 100만 쓸 수 있습니다. 법정 금액·세율은 law 값으로 두고 rule_id를 연결하세요.",
    "ungrounded_rate_table": "세율표가 연결한 원문 줄에 없습니다. 세율표의 각 구간을 원문 span_ids로 연결하세요.",
    "ungrounded_rate_band": "세율표의 한 구간이 원문에 없습니다. 원문에 적힌 구간과 세율만 쓰세요.",
    "unconfirmed_rate_or_unstated_assumption": "원문에서 확인되지 않은 세율을 쓰거나 가정을 assumptions에 밝히지 않았습니다.",
    "unknown_step_rule": "step의 rule_ids가 rules에 없습니다.",
    "invalid_rule_source": "rule이 제공된 근거 ID나 원문 줄을 가리키지 않습니다.",
    "invalid_source_span": "span_id가 그 근거의 원문 줄이 아닙니다.",
    "ungrounded_law_value": "법정 값이 연결한 원문 줄에 없습니다. 원문에 적힌 금액·비율만 law 값으로 쓰고 그 줄을 rule로 연결하세요.",
    "unconfirmed_user_value": "사용자 값의 quote가 사용자 발언의 연속 원문이 아니거나 값과 다릅니다. 질문에 실제로 있는 표현과 값만 쓰고, 없는 값은 assumption으로 밝히세요.",
    "reference_date_changed": "reference_date를 바꾸지 마세요. 제공된 기준일을 그대로 쓰세요.",
    "unverified_or_undated_source": "검증되지 않았거나 시행일이 없는 근거를 rule로 연결했습니다. 공식 원문 근거만 쓰세요.",
    "source_after_reference_date": "기준일보다 늦게 시행되는 근거를 연결했습니다. 기준일에 시행 중인 원문만 쓰세요.",
}


def formula_feedback(error):
    """Rule code plus its meaning and fix; other errors (schema validation) pass through."""
    text = str(error)
    code = text.split(":", 1)[0]  # some codes carry the offending value ID after ':'
    if isinstance(error, FormulaError) and code in HINTS:
        return f"{text}: {HINTS[code]}"
    return text[:400]
