"""The same Korean analyzer is used for BM25 documents and questions."""
from functools import lru_cache
import re
from threading import Lock
import unicodedata


ANALYZER_VERSION = 'kiwi-0.24-tax-v1'
_STOPWORDS = {'무엇', '어떤', '어떻게', '경우', '설명', '문제', '질문', '확인',
              '관련', '해당', '다음', '사항', '내용', '방법', '가능', '여부', '자료',
              '정도', '때문', '위한', '것', '등', '수', '법', '조', '항', '호', '원'}
_ALIASES = {'부가세': '부가가치세', '종소세': '종합소득세'}
_COMPOUNDS = ('매입세액', '매출세액', '기업업무추진비', '손금불산입', '손금산입',
              '증여재산공제', '금융소득', '배당소득', '이자소득', '종합소득세',
              '부가가치세', '세금계산서', '결손금', '소급공제', '상여처분')
_kiwi = None
_lock = Lock()


def _analyzer():
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi(num_workers=1)
        for word in _COMPOUNDS:
            _kiwi.add_user_word(word, 'NNG')
    return _kiwi


def analyze_many(texts):
    normalized = [unicodedata.normalize('NFC', text).lower() for text in texts]
    # Serialize access to the shared native analyzer; never block the event loop.
    with _lock:
        tokenized = list(_analyzer().tokenize(normalized))
    output = []
    for text, tokens in zip(normalized, tokenized):
        terms = [token.form for token in tokens
                 if (token.tag.startswith('NN') or token.tag in {'SL', 'SN'})
                 and len(token.form) >= 2 and token.form not in _STOPWORDS]
        terms.extend('ref:' + number + (':' + branch if branch else '')
                     for number, branch in re.findall(r'제\s*(\d+)\s*조(?:\s*의\s*(\d+))?', text))
        output.append(terms)
    return output


@lru_cache(maxsize=512)
def analyze_query(text):
    # Aliases expand retrieval vocabulary only; they establish no legal equivalence.
    expanded = text
    for alias, term in _ALIASES.items():
        if alias in text:
            expanded += ' ' + term
    return tuple(dict.fromkeys(analyze_many([expanded])[0]))
