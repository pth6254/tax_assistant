"""Encode the exported documents and questions with a sentence-transformers model (no project imports).

Runs in a separate environment that has torch and sentence-transformers, e.g.
    python evaluation/embedding_encode.py --run evaluation/runs/embedding-candidates \
        --model nlpai-lab/KURE-v3 --name kure-v3
Questions go through encode_query and documents through encode_document, so each model gets the
prompts it was trained with (KURE-v3: "query: " / "passage: "). Long documents are cut at --max-tokens.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--truncate-dim", type=int)
    args = parser.parse_args()

    run = Path(args.run)
    docs = [json.loads(line)["text"] for line in (run / "docs.jsonl").open(encoding="utf-8")]
    queries = [json.loads(line)["query"] for line in (run / "queries.jsonl").open(encoding="utf-8")]
    model = SentenceTransformer(args.model, device="cuda", model_kwargs={"dtype": "bfloat16"},
                                truncate_dim=args.truncate_dim)
    model.max_seq_length = args.max_tokens

    start = time.perf_counter()
    doc_vectors = model.encode_document(docs, batch_size=args.batch_size, normalize_embeddings=True,
                                        show_progress_bar=True, convert_to_numpy=True)
    doc_seconds = time.perf_counter() - start
    start = time.perf_counter()
    query_vectors = model.encode_query(queries, batch_size=args.batch_size, normalize_embeddings=True,
                                       convert_to_numpy=True)
    query_seconds = time.perf_counter() - start
    single = []
    for query in queries[:20]:
        begin = time.perf_counter()
        model.encode_query([query], normalize_embeddings=True)
        single.append(time.perf_counter() - begin)

    folder = run / args.name
    folder.mkdir(parents=True, exist_ok=True)
    np.save(folder / "docs.npy", doc_vectors.astype(np.float32))
    np.save(folder / "queries.npy", query_vectors.astype(np.float32))
    info = {"model": args.model, "dimension": int(doc_vectors.shape[1]), "max_tokens": args.max_tokens,
            "docs_seconds": round(doc_seconds, 1), "queries_seconds": round(query_seconds, 2),
            "single_query_median_seconds": round(float(np.median(single)), 4)}
    (folder / "model.json").write_text(json.dumps(info), encoding="utf-8")
    print(json.dumps(info))


if __name__ == "__main__":
    main()
