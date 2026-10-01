"""MMR orders scoped candidates while preserving every provision and pin.

Relevance comes from retrieval ranking, redundancy from candidate vectors. This
does not certify legal relevance and never removes exceptions or dependencies.
"""
import numpy as np


def mmr_order(rows, vectors, *, pinned=(), lambda_mult=0.85):
    if not 0 <= lambda_mult <= 1:
        raise ValueError('invalid_mmr_lambda')
    if len(rows) < 3:
        return list(rows)
    identity = lambda r: (r.law_name, r.article_no)
    # Pins keep their exact slots, including late graph/exception supplements.
    # Promoting every pin to the front can displace more relevant fused sources.
    pinned = set(pinned) | {identity(r) for r in rows[:2]}
    fixed = {i for i, row in enumerate(rows) if identity(row) in pinned}
    selected = []
    remaining = [i for i in range(len(rows)) if i not in fixed]
    normalized = {}
    for i, row in enumerate(rows):
        vector = vectors.get(row.source_id)
        if vector is None:
            continue
        vector = np.asarray(vector, dtype=float)
        norm = np.linalg.norm(vector)
        if norm > 0 and np.all(np.isfinite(vector)):
            normalized[i] = vector / norm
    if len(normalized) < 2:
        return list(rows)
    for position in range(len(rows)):
        if position in fixed:
            selected.append(position)
            continue
        scores = []
        for i in remaining:
            # Rank-based relevance keeps lexical and vector scales separate.
            relevance = 1.0 / (i + 1)
            similarities = [float(np.dot(normalized[i], normalized[j])) for j in selected
                            if i in normalized and j in normalized
                            and normalized[i].shape == normalized[j].shape]
            redundant = max([0.0, *similarities])
            score = lambda_mult * relevance - (1 - lambda_mult) * redundant
            scores.append((score, -i, i))
        score, _, index = max(scores)
        rows[index].retrieval_scores['mmr'] = score
        selected.append(index)
        remaining.remove(index)
    return [rows[i] for i in selected]
