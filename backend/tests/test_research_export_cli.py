"""Exercise the exporter on an injected snapshot, without a live DB or mutations."""

from contextlib import asynccontextmanager
import hashlib
import json

import pytest

from scripts.export_research_dataset import main
from tests.test_research_support import research_records


@pytest.mark.asyncio
async def test_export_cli_exact_jsonl_hash_no_overwrites_or_db_changes(tmp_path, monkeypatch):
    sentinel = object()
    records = research_records()
    called = []

    @asynccontextmanager
    async def snapshot():
        yield sentinel

    async def collect(db, version):
        assert db is sentinel
        called.append(version)
        return records

    monkeypatch.setattr("scripts.export_research_dataset.snapshot_session", snapshot)
    monkeypatch.setattr("scripts.export_research_dataset.collect_export_records", collect)
    output = tmp_path / "dataset.jsonl"
    args = ["--output", str(output), "--dataset-version", "synthetic-unit-test-v1"]
    assert await main(args) == 0
    data = output.read_bytes()
    manifest = json.loads((tmp_path / "dataset.jsonl.manifest.json").read_text(encoding="utf-8"))
    assert manifest["records_sha256"] == hashlib.sha256(data).hexdigest()
    assert manifest["record_count"] == 18 and manifest["publication_ready"] is False
    assert len([json.loads(line) for line in data.splitlines()]) == 18
    assert await main(args) == 2
    assert output.read_bytes() == data and called == ["synthetic-unit-test-v1"]


@pytest.mark.asyncio
async def test_export_cli_refuses_unassigned_without_writing_artifacts(tmp_path, monkeypatch):
    records = research_records()
    records[0]["split"] = "unassigned"

    @asynccontextmanager
    async def snapshot():
        yield None

    async def collect(db, version):
        return records

    monkeypatch.setattr("scripts.export_research_dataset.snapshot_session", snapshot)
    monkeypatch.setattr("scripts.export_research_dataset.collect_export_records", collect)
    output = tmp_path / "unassigned.jsonl"
    assert await main(["--output", str(output), "--dataset-version", "synthetic-unit-test-v1"]) == 2
    assert not output.exists()
