"""Sparse Okapi BM25 over immutable token lists (no database or model calls).

Positive Robertson/Lucene IDF, term-frequency saturation and document-length
normalization. Query duplicates do not create extra votes. Search visits only
postings for matching terms; scores are never interpreted as cosine similarity.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
import heapq
import math


@dataclass(frozen=True)
class BM25Hit:
    index: int
    score: float


class BM25Index:
    def __init__(self, documents, *, k1=1.2, b=0.75):
        if not math.isfinite(k1) or k1 <= 0 or not 0 <= b <= 1:
            raise ValueError('invalid_bm25_parameters')
        self.k1, self.b = k1, b
        self.lengths = []
        self.postings = defaultdict(list)
        for index, tokens in enumerate(documents):
            counts = Counter(tokens)
            self.lengths.append(sum(counts.values()))
            for term, frequency in counts.items():
                self.postings[term].append((index, frequency))
        self.count = len(self.lengths)
        self.average_length = sum(self.lengths) / self.count if self.count else 0
        self.idf = {term: math.log1p((self.count - len(rows) + 0.5) / (len(rows) + 0.5))
                    for term, rows in self.postings.items()}

    def search(self, terms, top_k=15, allowed=None):
        if not self.average_length or top_k <= 0:
            return []
        scores = self.scores(terms, allowed)
        ranked = heapq.nsmallest(top_k, scores, key=lambda index: (-scores[index], index))
        return [BM25Hit(index, scores[index]) for index in ranked if scores[index] > 0]

    def scores(self, terms, allowed=None):
        scores = defaultdict(float)
        if not self.average_length:
            return scores
        for term in dict.fromkeys(terms):
            for index, frequency in self.postings.get(term, ()):
                if allowed is not None and index not in allowed:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * self.lengths[index] / self.average_length)
                scores[index] += self.idf[term] * frequency * (self.k1 + 1) / denominator
        return scores


class BM25Fields:
    """Weighted sum of independently length-normalized title and body BM25.

    A matching legal article title should not be diluted by its long body or by
    an unrelated provision mentioning the query terms in citations. This is a
    field score, not a semantic relevance or legal authority judgment.
    """
    def __init__(self, titles, bodies, title_weight=2.0):
        if len(titles) != len(bodies) or not math.isfinite(title_weight) or title_weight < 0:
            raise ValueError('invalid_bm25_fields')
        self.title = BM25Index(titles)
        self.body = BM25Index(bodies)
        self.title_weight = title_weight

    def search(self, terms, top_k=15, allowed=None):
        if top_k <= 0:
            return []
        terms = tuple(terms)
        scores = self.body.scores(terms, allowed)
        for index, score in self.title.scores(terms, allowed).items():
            scores[index] += self.title_weight * score
        ranked = heapq.nsmallest(top_k, scores, key=lambda index: (-scores[index], index))
        return [BM25Hit(index, scores[index]) for index in ranked if scores[index] > 0]
