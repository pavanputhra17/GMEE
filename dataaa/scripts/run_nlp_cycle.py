# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Run one NLP cycle (claims + entities + embeddings) over pending articles.

Usage:
  python scripts/run_nlp_cycle.py [max_articles]
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import async_session_maker
from app.services.nlp.embedding_service import EmbeddingService
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.nlp_orchestrator import NLPOrchestrator


async def main() -> None:
    max_articles = int(sys.argv[1]) if len(sys.argv) > 1 else 10

    EmbeddingService.load_model()
    EntityExtractor.load_model()

    orch = NLPOrchestrator()
    orch.max_articles = max_articles

    async with async_session_maker() as db:
        summary = await orch.run_nlp_cycle(db)

    print("\n=== NLP CYCLE SUMMARY ===")
    print(f"processed:        {summary.total_processed}")
    print(f"status counts:    {summary.status_counts}")
    print(f"claims extracted: {summary.claims_extracted}")
    if summary.errors:
        print(f"errors ({len(summary.errors)}):")
        for e in summary.errors[:5]:
            print(f"  - {e[:160]}")


if __name__ == "__main__":
    asyncio.run(main())
