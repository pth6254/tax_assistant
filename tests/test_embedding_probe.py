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


def test_candidates_are_ranked_by_exact_cosine_per_article(tmp_path):
    import numpy as np
    from evaluation import embedding_candidate as candidate

    run = tmp_path / "run"
    (run / "m").mkdir(parents=True)
    docs = [{"law": "A법", "article": "제1조", "kind": "article", "text": "a"},
            {"law": "A법", "article": "제1조", "kind": "clause", "text": "a1"},
            {"law": "B법", "article": "제2조", "kind": "article", "text": "b"}]
    (run / "docs.jsonl").write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in docs) + "\n",
                                    encoding="utf-8")
    dataset = tmp_path / "set.json"
    dataset.write_text(json.dumps({"cases": [
        {"id": "q1", "tier": "colloquial", "query": "?", "required": [{"law": "B법", "article": "제2조"}],
         "acceptable": []}]}, ensure_ascii=False), encoding="utf-8")
    # The clause of 제1조 is closest, then 제2조: the article appears once, ahead of 제2조.
    np.save(run / "m" / "docs.npy", np.array([[0, 1], [1, 0.1], [1, 0.5]], dtype=np.float32))
    np.save(run / "m" / "queries.npy", np.array([[1, 0]], dtype=np.float32))
    (run / "m" / "model.json").write_text('{"model": "test"}', encoding="utf-8")
    summary = candidate.score(run, "m", dataset)
    rows = json.loads((run / "m" / "results.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["top"] == [["A법", "제1조"], ["B법", "제2조"]]
    assert rows[0]["rank"] == 2 and summary["all"]["hit@1"] == 0.0


def test_the_paired_comparison_counts_cases_only_one_model_finds(tmp_path):
    from evaluation import embedding_candidate as candidate

    def write(name, ranks):
        (tmp_path / name).mkdir()
        rows = [{"id": f"c{i}", "rank": r} for i, r in enumerate(ranks)]
        (tmp_path / name / "results.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    write("base", [1, None, 9, 2, 3])
    write("new", [1, 2, 3, 4, None])
    result = candidate.compare(tmp_path, "base", "new", k=5)
    assert result["only_base"] == 1 and result["only_new"] == 2
    assert result["only_new_ids"] == ["c1", "c2"] and result["sign_test_p"] == 1.0
