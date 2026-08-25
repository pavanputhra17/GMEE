"""One-time scrub: strip HTML from article titles and claim texts.

The friend's scraper embedded <a href=...><img align="left">...</a> markup in
some titles (Sky News liveblog entries) and those leaked into extracted
claims. This script:
  1. strips tags + entities, collapses whitespace
  2. fixes titles in place
  3. deletes claims whose text WAS pure markup (no real sentence remains)
  4. re-embeds + re-verdicts touched claims (via re-extract flag)
"""

import html as htmllib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db.postgres import async_session_maker  # noqa: E402

TAG_RE = re.compile(r"<[^>]+>")


def clean(raw: str) -> str:
    s = TAG_RE.sub(" ", raw)
    s = htmllib.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


async def main() -> None:
    async with async_session_maker() as db:
        # ---- titles ----
        rows = (
            await db.execute(
                text("SELECT id::text, title FROM articles WHERE title LIKE '%<%'")
            )
        ).all()
        fixed = 0
        for aid, raw in rows:
            t = clean(raw)
            if not t:
                continue
            await db.execute(
                text("UPDATE articles SET title = :t WHERE id = CAST(:i AS uuid)"),
                {"t": t[:500], "i": aid},
            )
            fixed += 1
        print(f"titles cleaned: {fixed}")

        # ---- claims: clean text; delete if nothing real remains ----
        crows = (
            await db.execute(
                text("SELECT id::text, claim_text FROM claims WHERE claim_text LIKE '%<%'")
            )
        ).all()
        cleaned = deleted = 0
        for cid, raw in crows:
            t = clean(raw)
            # a surviving fragment must look like prose (>=25 chars, has spaces/verbs-ish)
            if len(t) >= 25 and " " in t and not t.lower().startswith(("http", "more", "read")):
                await db.execute(
                    text(
                        "UPDATE claims SET claim_text = :t, verdict = NULL, "
                        "verdict_probability = NULL, verdict_rationale = NULL, "
                        "verdict_evidence = NULL, embedding = NULL "
                        "WHERE id = CAST(:i AS uuid)"
                    ),
                    {"t": t, "i": cid},
                )
                cleaned += 1
            else:
                await db.execute(
                    text("DELETE FROM claims WHERE id = CAST(:i AS uuid)"), {"i": cid}
                )
                deleted += 1
        print(f"claims cleaned: {cleaned}, deleted (pure markup): {deleted}")

        await db.commit()

        # ---- verify ----
        res = await db.execute(
            text("SELECT COUNT(*) FROM articles WHERE title LIKE '%<%'")
        )
        print(f"articles still containing '<': {res.scalar()}")
        res = await db.execute(
            text("SELECT COUNT(*) FROM claims WHERE claim_text LIKE '%<%'")
        )
        print(f"claims still containing '<': {res.scalar()}")
        res = await db.execute(
            text("SELECT COUNT(*) FROM claims WHERE embedding IS NULL")
        )
        print(f"claims needing re-embed+re-verdict: {res.scalar()}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
