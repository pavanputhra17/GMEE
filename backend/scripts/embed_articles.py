"""Semantic search over the article corpus using pgvector.

Embeds the query with the project's own model (all-mpnet-base-v2), then
runs pgvector cosine distance against article embeddings. On first use it
backfills embeddings for any article missing one (cached in the DB, so the
cost is paid once).
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def ensure_column() -> None:
    from sqlalchemy import text

    from app.db.postgres import async_session_maker

    async with async_session_maker() as db:
        await db.execute(
            text(
                """
                ALTER TABLE articles
                ADD COLUMN IF NOT EXISTS embedding vector(768)
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS articles_embedding_ix
                ON articles USING hnsw (embedding vector_cosine_ops)
                """
            )
        )
        await db.commit()


async def backfill(limit: int = 1000) -> int:
    from sqlalchemy import text

    from app.db.postgres import async_session_maker

    model = _load_model()
    async with async_session_maker() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT id, COALESCE(title,'') || '. ' || COALESCE(cleaned_content,'') AS body
                    FROM articles
                    WHERE embedding IS NULL AND processing_status='processed'
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            )
        ).all()
        if not rows:
            return 0
        vecs = model.encode(
            [r[1][:2000] for r in rows],
            batch_size=64,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        for (aid, _), v in zip(rows, vecs):
            lit = "[" + ",".join(f"{x:.6f}" for x in v.tolist()) + "]"
            await db.execute(
                text("UPDATE articles SET embedding = CAST(:v AS vector) WHERE id = CAST(:id AS uuid)"),
                {"v": lit, "id": str(aid)},
            )
        await db.commit()
        return len(rows)


_model = None


def _load_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-mpnet-base-v2")
    return _model


async def main() -> None:
    await ensure_column()
    total = 0
    while True:
        n = await backfill()
        total += n
        print(f"backfilled {total} embeddings so far", flush=True)
        if n == 0:
            break
    print(f"embedding backfill complete: {total} articles")


if __name__ == "__main__":
    asyncio.run(main())
