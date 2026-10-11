"""Read a virtual asset (코인) tax question into calculator inputs plus stated assumptions.

The sale and purchase amounts must be written. A coin bought before 2027 may use its 2026-12-31 price as the
acquisition cost; when the user gives that price it is used, otherwise the actual cost is (which can only
overstate the tax) and the result says so. Lending income, non-residents and coin-to-coin swaps return None.
"""
from dataclasses import dataclass
import re

from app.services.calculator.capital_gains_inputs import BUY_VERB, SELL_VERB, _amount
from app.services.calculator.financial_inputs import ambiguous_thousands

COIN = re.compile(r"가상자산|암호화폐|가상화폐|코인|비트코인|이더리움|리플|솔라나|도지|테더|USDT", re.I)
UNSUPPORTED = re.compile(r"대여|스테이킹|이자|에어드랍|채굴|비거주|코인\s*끼리|교환|NFT", re.I)
YEAR_END = r"2026년\s*(?:12월\s*31일|말)\s*(?:시가|가격|시세)|2026년말\s*시가"
BOUGHT_BEFORE_2027 = re.compile(r"20(?:1\d|2[0-6])년|작년|재작년|예전에|몇\s*년\s*전|오래\s*전|2027년\s*(?:전|이전)")


@dataclass
class StatedInputs:
    params: dict
    assumptions: list


@dataclass
class MissingInputs:
    """Facts the calculator needs and must not assume; the chat asks for them."""
    labels: list


def stated_virtual_asset_inputs(query, history=None):
    texts = [str(m.get("content", "")) for m in (history or []) if m.get("role") == "user"][-2:] + [query]
    text = "\n".join(texts)
    if not COIN.search(text) or UNSUPPORTED.search(text):
        return None
    if unclear := ambiguous_thousands(text):
        return MissingInputs([f"'{amount}'의 단위(천만원인지 천원인지)" for amount in unclear])
    try:
        transfer = _amount(r"양도가액|매도가|판 금액|판매가", SELL_VERB, texts)
        acquisition = _amount(r"취득가액|매수가|산 금액|구입가", BUY_VERB, texts)
        expenses = _amount(r"수수료|필요경비|경비", None, texts)
        year_end = _amount(YEAR_END, None, texts)
    except ValueError:
        return None
    if transfer is None:
        return None
    if acquisition is None:
        return MissingInputs(["가상자산을 산 금액(취득가액)"])
    before = year_end is not None or bool(BOUGHT_BEFORE_2027.search(text))
    assumptions = ["같은 해 다른 가상자산 손익은 없다고 보았습니다(있으면 총평균법으로 합쳐 계산해야 합니다)."]
    if before and year_end is None:
        assumptions.append("2027년 전부터 보유한 가상자산은 2026년 12월 31일 시가가 실제 취득가액보다 크면 그 시가를 취득가액으로 "
                           "합니다. 시가를 알려주지 않아 실제 취득가액으로 계산했습니다(세금이 더 크게 나올 수 있음).")
    if expenses is None:
        assumptions.append("거래수수료 등 필요경비는 0원으로 보았습니다.")
    return StatedInputs({"transfer_price": transfer, "acquisition_price": acquisition, "expenses": expenses or 0,
                         "held_before_2027": before, "value_2026_end": year_end or 0}, assumptions)
