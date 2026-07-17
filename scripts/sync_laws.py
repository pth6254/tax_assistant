"""
scripts/sync_laws.py — 법령 개정 자동 동기화

이미 수집된 법률/시행령/시행규칙(law_articles의 distinct law_name)을 전부
재수집하여 조문 내용이 바뀐 경우(=개정)를 감지하고 최신 버전으로 교체한다.
법령해석례(law_type='법령해석례')는 "개정"이라는 개념이 다르므로 대상에서 제외한다
(신규 유권해석 수집은 scripts/ingest_interpretations.py를 별도 실행).

OS 스케줄러(cron, Windows 작업 스케줄러)에 등록해 주기적으로 실행하는 것을 전제로 하며,
하나라도 실패하면 non-zero exit code를 반환해 스케줄러/모니터링이 실패를 감지할 수 있게 한다.

사용법:
  python scripts/sync_laws.py                 # 임베딩 없이 재수집 (개정 감지만)
  python scripts/sync_laws.py --embed         # 개정된 조문의 임베딩까지 새로 생성

cron 등록 예시 (매일 새벽 3시):
  0 3 * * * cd /path/to/tax_assistant && ./venv/bin/python scripts/sync_laws.py --embed >> logs/sync_laws.log 2>&1

Windows 작업 스케줄러 등록 예시:
  프로그램/스크립트: python.exe
  인수 추가:         scripts\\sync_laws.py --embed
  시작 위치:          (프로젝트 루트 경로)
  트리거:            매일, 원하는 시각
  실패 알림:         "작업이 실패하는 경우" 조건에서 이메일/알림 액션 연결 가능
                     (종료 코드가 0이 아니면 작업 스케줄러가 "실패"로 기록함)
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import close_pool, get_pool
from app.services.law.ingestion_service import ingest_law
from app.utils.embeddings import close_http_client


async def _list_synced_laws() -> list[dict]:
    """현재 DB에 수집되어 있는 법률/시행령/시행규칙의 (law_name, tax_type) 목록.

    law_type이 아닌 '법령해석례 제외'로 필터링한다 — law_type 파싱 태그명 버그로
    기존에 수집된 행들이 law_type=''로 저장되어 있을 수 있기 때문(재동기화하면 교정됨).
    """
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT DISTINCT law_name, tax_type
        FROM law_articles
        WHERE is_current = TRUE AND law_type <> '법령해석례'
        ORDER BY law_name
        """
    )
    return [{"law_name": r["law_name"], "tax_type": r["tax_type"]} for r in rows]


async def main(args: argparse.Namespace) -> int:
    print("DB 연결 중...")
    await get_pool()
    print("DB 연결 완료\n")

    exit_code = 0
    try:
        targets = await _list_synced_laws()
        if not targets:
            print("동기화 대상 법령이 없습니다 (먼저 scripts/ingest_laws.py로 수집하세요).")
            return 0

        print(f"동기화 대상 {len(targets)}개 법령\n")

        total_amended  = 0
        total_inserted = 0
        failures: list[str] = []

        for target in targets:
            law_name = target["law_name"]
            try:
                result = await ingest_law(
                    law_name=law_name, tax_type=target["tax_type"], embed=args.embed,
                )
                amended = result["amended_count"]
                total_amended  += amended
                total_inserted += result["inserted_count"]
                marker = " ⚠️ 개정 감지" if amended else ""
                print(f"  '{law_name}' — 신규 {result['inserted_count']} | 개정 {amended} | 실패 {result['failed_count']}{marker}")
                if result["failed_count"]:
                    failures.append(f"{law_name} (조문 저장 실패 {result['failed_count']}건)")
            except Exception as e:
                print(f"  '{law_name}' — 동기화 실패: {e}")
                failures.append(f"{law_name} ({e})")

        print(f"\n{'='*50}")
        print(f"동기화 완료 — 개정 감지 {total_amended}건 | 신규 조문 {total_inserted}건")
        if failures:
            print(f"실패 {len(failures)}건:")
            for f in failures:
                print(f"  - {f}")
            exit_code = 1
        print(f"{'='*50}")

    finally:
        await close_pool()
        await close_http_client()
        print("\nDB 연결 종료")

    return exit_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="법령 개정 자동 동기화 스크립트")
    parser.add_argument("--embed", action="store_true", help="개정된 조문의 임베딩까지 생성")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args)))
