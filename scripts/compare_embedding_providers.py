"""Compare v1 and v2 embedding providers before a cutover."""
import argparse
import asyncio
import math

from app.services.embedding_service import close_http_client, embed_texts_for_version


DEFAULT_TEXTS = [
    "종합소득세 신고 기한은 언제인가요?",
    "소득세법 제59조의4 세액공제 요건",
    "부가가치세법 시행령 관련 매입세액 공제",
    "법인세 중간예납 계산 방법",
    "상속세 및 증여세법상 증여재산 공제",
]


def cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("texts", nargs="*", default=DEFAULT_TEXTS)
    parser.add_argument("--minimum-cosine", type=float, default=0.99)
    args = parser.parse_args()
    try:
        old, new = await asyncio.gather(
            embed_texts_for_version(args.texts, "v1"),
            embed_texts_for_version(args.texts, "v2"),
        )
        scores = [cosine(a, b) for a, b in zip(old, new)]
        for text, score in zip(args.texts, scores):
            print(f"{score:.8f}\t{text}")
        minimum = min(scores)
        print(f"minimum={minimum:.8f} average={sum(scores) / len(scores):.8f}")
        return 0 if minimum >= args.minimum_cosine else 2
    finally:
        await close_http_client()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
