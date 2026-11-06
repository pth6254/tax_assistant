"""Scoring of the embedding retrieval probe and the shape of its dataset (no database)."""
import json
from pathlib import Path

from evaluation import embedding_probe as probe
from evaluation.build_embedding_set import COLLOQUIAL

DATASET = Path(__file__).resolve().parents[1] / "evaluation" / "datasets" / "embedding_retrieval.json"


def test_an_acceptable_article_counts_as_a_hit_at_its_rank():
    case = {"required": [{"law": "소득세법", "article": "제89조"}],
            "acceptable": [{"law": "소득세법 시행령", "article": "제154조"}]}
    ranked = [("소득세법", "제88조"), ("소득세법 시행령", "제154조"), ("소득세법", "제89조")]
    assert probe.first_hit(ranked, probe.targets(case)) == 2
    assert probe.first_hit(ranked[:1], probe.targets(case)) is None


def test_scores_are_per_tier_and_a_miss_counts_against_every_cutoff():
    rows = [{"tier": "colloquial", "explicit_reference": False, "rank": 1, "seconds": 0.1},
            {"tier": "colloquial", "explicit_reference": False, "rank": 7, "seconds": 0.3},
            {"tier": "interpretation", "explicit_reference": True, "rank": None, "seconds": 0.2},
            {"tier": "interpretation", "explicit_reference": False, "rank": 3, "seconds": 0.2}]
    summary = probe.summarize(rows)
    assert summary["colloquial"]["hit@1"] == 0.5 and summary["colloquial"]["hit@10"] == 1.0
    assert summary["interpretation"]["hit@20"] == 0.5
    assert summary["interpretation_without_article_number"]["cases"] == 1
    assert summary["all"]["mrr@20"] == round((1 + 1 / 7 + 1 / 3) / 4, 3)
    assert "legacy" not in summary


def test_the_dataset_keeps_its_tiers_and_every_case_has_one_required_article():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    assert dataset["tiers"] == {tier: sum(c["tier"] == tier for c in cases) for tier in dataset["tiers"]}
    assert len({c["id"] for c in cases}) == len(cases)
    assert all(len(c["required"]) == 1 and c["query"].strip() for c in cases)
    assert dataset["tiers"]["colloquial"] == len(COLLOQUIAL)
