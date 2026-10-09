# mypy: disallow-untyped-defs=False, disallow-incomplete-defs=False, disallow-any-generics=False

"""Persistent alert evaluation runner — one pass over recent corpus activity.

Detects corroboration / contradiction signals, claim mutations and story-cluster
bursts, then upserts them into the `alerts` table (deduplicated on kind+subject:
a re-run only refreshes `last_seen_at`). The same routine backs
`POST /api/v1/alerts/evaluate` (admin) and `GET /api/v1/alerts/feed`.

Usage: python scripts/run_alerts.py [window_hours]   # default 6
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import async_session_maker
from app.services.alerts import evaluate_alerts


async def main() -> None:
    window_hours = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    async with async_session_maker() as db:
        summary = await evaluate_alerts(db, window_hours=window_hours)
    print(json.dumps({"window_hours": window_hours, **summary}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
