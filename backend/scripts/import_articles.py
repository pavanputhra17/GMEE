"""Import the friend-exported articles CSV into GMEE Postgres.

Honors the backend's own conventions:
  - content_hash = sha256("{title.lower()}:{content.lower()}")
    (matches CollectionOrchestrator._generate_content_hash)
  - Sources are created per unique source_url (type=rss) and referenced
  - INSERT ... ON CONFLICT (url) DO NOTHING  (same as collection cycle)
  - Original article UUIDs, timestamps, statuses are preserved

Usage (from backend/, venv active):
  set -a && source ../.env && set +a
  set POSTGRES_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/gmee
  python scripts/import_articles.py ../dataaa/gmee_articles_export.csv
"""

import asyncio
import csv
import hashlib
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from app.db.postgres import async_session_maker as AsyncSessionLocal  # noqa: E402


def content_hash(title: str, content: str | None) -> str:
    t = (title or "").strip().lower()
    c = (content or "").strip().lower()
    return hashlib.sha256(f"{t}:{c}".encode("utf-8")).hexdigest()


def parse_ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("+00:00", "+00:00"))
    except ValueError:
        return None


async def main(csv_path: str) -> None:
    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"CSV rows: {len(rows)}")

    # ---- 1. sources ----
    sources: dict[str, tuple[str, str]] = {}
    for r in rows:
        su = r["source_url"]
        if su and su not in sources:
            sources[su] = (r["source_name"], r["source_type"])
    print(f"unique sources: {len(sources)}")

    async with AsyncSessionLocal() as db:
        # upsert sources by url_or_identifier
        src_ids: dict[str, uuid.UUID] = {}
        for su, (name, stype) in sources.items():
            res = await db.execute(
                text("SELECT id FROM sources WHERE url_or_identifier = :u"),
                {"u": su},
            )
            got = res.scalar()
            if got is None:
                sid = uuid.uuid4()
                await db.execute(
                    text(
                        "INSERT INTO sources (id, name, type, url_or_identifier, is_active) "
                        "VALUES (:id, :name, CAST(:t AS sourcetypeenum), :u, true)"
                    ),
                    {"id": sid, "name": name, "t": stype, "u": su},
                )
                src_ids[su] = sid
            else:
                src_ids[su] = got
        await db.commit()
        print(f"sources ready: {len(src_ids)}")

        # ---- 2. articles in batches ----
        inserted = skipped = 0
        BATCH = 500
        for off in range(0, len(rows), BATCH):
            chunk = rows[off : off + BATCH]
            params: list[dict] = []
            for r in chunk:
                url = r["url"].strip()
                if not url:
                    skipped += 1
                    continue
                ch = content_hash(r["title"], r["cleaned_content"] or r["content"])
                params.append(
                    {
                        "id": uuid.UUID(r["id"]),
                        "source_id": src_ids[r["source_url"]],
                        "title": r["title"],
                        "url": url,
                        "content": r["content"] or None,
                        "published_at": parse_ts(r["published_at"]),
                        "author": r["author"] or None,
                        "raw_metadata_json": "{}",
                        "content_hash": ch,
                        "collected_at": parse_ts(r["collected_at"]),
                        "language": r["language"] or None,
                        "processing_status": r["processing_status"] or "processed",
                        "cleaned_content": r["cleaned_content"] or None,
                        "word_count": int(r["word_count"]) if r["word_count"].isdigit() else None,
                        "domain": r["domain"] or None,
                        "processed_at": parse_ts(r["processed_at"]),
                        "nlp_status": r["nlp_status"] or "pending",
                    }
                )

            if not params:
                continue

            stmt = text(
                """
                INSERT INTO articles (
                    id, source_id, title, url, content, published_at, author,
                    raw_metadata, content_hash, collected_at, language,
                    processing_status, cleaned_content, word_count, domain,
                    processed_at, nlp_status
                ) VALUES (
                    :id, :source_id, :title, :url, :content, :published_at, :author,
                    CAST(:raw_metadata_json AS jsonb), :content_hash, :collected_at, :language,
                    CAST(:processing_status AS processingstatusenum), :cleaned_content,
                    :word_count, :domain, :processed_at,
                    CAST(:nlp_status AS nlpstatusenum)
                )
                ON CONFLICT (url) DO NOTHING
                """
            )
            res = await db.execute(stmt, params)
            inserted += res.rowcount or 0
            skipped += len(params) - (res.rowcount or 0)
            await db.commit()
            print(f"  batch {off // BATCH + 1}: +{res.rowcount} (cumulative {inserted})")

        print(f"\nDONE. inserted={inserted} skipped(existing/invalid)={skipped}")

        # ---- 3. verify ----
        for label, q in [
            ("articles", "SELECT COUNT(*) FROM articles"),
            ("sources", "SELECT COUNT(*) FROM sources"),
            ("domains", "SELECT COUNT(DISTINCT domain) FROM articles"),
            ("date range", "SELECT MIN(published_at)::date, MAX(published_at)::date FROM articles"),
        ]:
            res = await db.execute(text(q))
            print(f"{label}: {res.all()[0]}")


if __name__ == "__main__":
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "../dataaa/gmee_articles_export.csv"
    asyncio.run(main(csv_file))
