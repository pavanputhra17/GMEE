"""Read-only export of versioned human-gold JSONL plus a deterministic manifest.

From the repository root:
  backend/.venv/Scripts/python.exe backend/scripts/export_research_dataset.py \
    --output dataset-v1.jsonl --dataset-version v1

--allow-incomplete explicitly excludes/reports unassigned human-gold pairs;
it never permits weak gold, duplicate pairs, or cross-split leakage. The
snapshot does not assign splits or mutate any database record.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.exc import SQLAlchemyError

from app.services.eval.dataset import (
    DatasetError,
    build_export,
    collect_export_records,
    records_bytes,
    snapshot_session,
)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only human-consensus research export (no pseudo-gold)")
    parser.add_argument("--output", type=Path, required=True, help="New JSONL snapshot path; existing files are never overwritten")
    parser.add_argument("--dataset-version", required=True, help="Explicit immutable dataset version (1–128 characters)")
    parser.add_argument("--manifest", type=Path, help="Defaults to <output>.manifest.json")
    parser.add_argument("--allow-incomplete", action="store_true", help="Exclude and report unassigned human-gold pairs; never bypass leakage/consensus validation")
    args = parser.parse_args(argv)
    manifest_path = args.manifest or Path(str(args.output) + ".manifest.json")
    try:
        if not args.dataset_version.strip() or len(args.dataset_version) > 128:
            raise DatasetError("--dataset-version must be 1–128 nonblank characters")
        if args.output.resolve() == manifest_path.resolve():
            raise DatasetError("Dataset and manifest must have different output paths")
        if args.output.exists() or manifest_path.exists():
            raise DatasetError("Dataset/manifest output already exists; choose a new version/path rather than overwriting a frozen snapshot")
        async with snapshot_session() as db:
            records = await collect_export_records(db, args.dataset_version)
        exported = build_export(records, args.dataset_version, publication=True, allow_incomplete=args.allow_incomplete)
        data = records_bytes(exported["records"])
        manifest = json.dumps(exported["manifest"], sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("xb") as file:
            file.write(data)
        with manifest_path.open("xb") as file:
            file.write(manifest)
    except DatasetError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(f"REFUSED: read-only database export failed ({type(exc).__name__}); verify credentials and apply the gmee01 -> gmee02 -> gmee03 migration chain before exporting", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"REFUSED: cannot create snapshot artifacts: {exc}", file=sys.stderr)
        return 2
    print(f"Exported {len(exported['records'])} human-gold records: {args.output}")
    print(f"SHA-256: {exported['manifest']['records_sha256']}; manifest: {manifest_path}")
    for warning in exported["manifest"]["warnings"]:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
