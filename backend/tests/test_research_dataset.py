"""Human evidence, versioning, connected-component leakage and export refusals."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.eval.dataset import (
    DatasetError,
    build_export,
    connected_components,
    records_bytes,
    snapshot_session,
    validate_assignments,
    validate_dataset,
)
from tests.test_research_support import research_records


def test_versioned_human_dataset_has_event_disjoint_support():
    records = research_records()
    result = validate_dataset(records)
    assert result["dataset_version"] == "synthetic-unit-test-v1"
    assert all(s["positive"] == s["negative"] == 3 for s in result["support"].values())
    assert all(s["independent_groups"] == 3 for s in result["support"].values())
    assert len(set(result["group_by_pair"].values())) == 9
    assert records_bytes(records) == records_bytes(list(reversed(records)))


@pytest.mark.parametrize("field", ["event_id", "claim_a_id", "article_a_id", "canonical_article_a_id", "article_content_hash_a", "text_a"])
def test_shared_event_claim_article_hash_or_text_cannot_cross_splits(field):
    records = research_records()
    source = records[0]
    target = next(r for r in records if r["split"] == "dev")
    if field == "canonical_article_a_id":
        target[field] = source["article_a_id"]
    elif field == "text_a":
        target[field] = "  " + source[field].upper().replace(" ", "  ") + " "
    else:
        target[field] = source[field]
    with pytest.raises(DatasetError, match="Leakage:.*component|Leakage:.*group"):
        validate_dataset(records)


def test_connected_claim_article_overlap_is_transitive():
    records = research_records()
    middle = next(r for r in records if r["split"] == "dev")
    last = next(r for r in records if r["split"] == "test")
    middle["article_a_id"] = records[0]["article_a_id"]
    last["claim_b_id"] = middle["claim_b_id"]
    groups = connected_components(records)
    assert any({"train", "dev", "test"} == {r["split"] for r in group} for group in groups)
    with pytest.raises(DatasetError, match="Leakage"):
        validate_dataset(records)


@pytest.mark.parametrize("origin", ["automatic", "legacy", "test"])
def test_weak_gold_is_refused_even_with_two_voters(origin):
    records = research_records()
    records[0]["provenance"]["gold_origin"] = origin
    for vote in records[0]["human_labels"]:
        vote["origin"] = origin
    with pytest.raises(DatasetError, match="human gold"):
        validate_dataset(records)


def test_one_identity_disagreement_or_copied_evidence_is_refused():
    for alteration in ("same_user", "disagree", "copied_pair"):
        records = research_records()
        votes = records[0]["human_labels"]
        if alteration == "same_user":
            votes[1]["annotator_user_id"] = votes[0]["annotator_user_id"]
            votes[1]["annotator"] = votes[0]["annotator"]
        elif alteration == "disagree":
            votes[1]["label"] = "DISTINCT"
        else:
            votes[1]["pair_id"] = records[1]["pair_id"]
        with pytest.raises(DatasetError, match="distinct authenticated|different pair"):
            validate_dataset(records)


def test_unagreed_mutation_types_cannot_become_mutation_gold():
    records = research_records(mutations=True)
    records[0]["human_labels"][1]["mutation_types"] = ["HEDGING_SHIFT"]
    with pytest.raises(DatasetError, match="mutation gold"):
        validate_dataset(records)


@pytest.mark.parametrize("field,value", [("split", "unassigned"), ("event_id", "unassigned"), ("cosine_score", 1.2), ("cosine_score", float("nan")), ("cosine_score", True), ("text_a", ""), ("article_a_id", None), ("schema_version", "v0"), ("provenance", None)])
def test_invalid_or_unassigned_records_are_actionably_refused(field, value):
    records = research_records()
    records[0][field] = value
    with pytest.raises(DatasetError):
        validate_dataset(records)


def test_insufficient_dataset_and_mixed_versions_are_refused():
    with pytest.raises(DatasetError, match="Insufficient train"):
        validate_dataset(research_records()[:2])
    records = research_records()
    records[0]["dataset_version"] = "another-version"
    with pytest.raises(DatasetError, match="Mixed dataset versions"):
        validate_dataset(records)


def test_duplicate_reversed_pair_is_refused_without_deleting_history():
    records = research_records()
    duplicate = deepcopy(records[0])
    duplicate["pair_id"] = "another-pair-id"
    duplicate["claim_a_id"], duplicate["claim_b_id"] = duplicate["claim_b_id"], duplicate["claim_a_id"]
    for vote in duplicate["human_labels"]:
        vote["pair_id"] = duplicate["pair_id"]
    records.append(duplicate)
    with pytest.raises(DatasetError, match="historical votes are retained"):
        validate_dataset(records)
    assert len(records) == 19  # Validation does not delete any row/vote.


def test_export_rejects_or_explicitly_reports_unassigned_human_gold():
    records = research_records()
    records[0]["event_id"] = records[0]["event_group"] = "unassigned"
    records[0]["split"] = "unassigned"
    audit = build_export(records, "synthetic-unit-test-v1")
    assert len(audit["records"]) == 18
    assert audit["manifest"]["exclusions"]["unassigned_event_or_split"] == 1
    with pytest.raises(DatasetError, match="unassigned event/split"):
        build_export(records, "synthetic-unit-test-v1", publication=True)
    partial = build_export(records, "synthetic-unit-test-v1", publication=True, allow_incomplete=True)
    assert len(partial["records"]) == 17 and partial["manifest"]["source_pair_count"] == 18
    assert partial["manifest"]["publication_ready"] is False
    assert any("explicitly excluded" in w for w in partial["manifest"]["warnings"])


def test_split_assignment_requires_whole_component_and_preserves_freeze():
    records = research_records()[:2]
    for record in records:
        record["event_id"] = record["event_group"] = "unassigned"
        record["split"] = "unassigned"
    records[1]["article_a_id"] = records[0]["article_a_id"]
    changes = [{"pair_id": r["pair_id"], "event_group": "curated-event", "split": "test"} for r in records]
    with pytest.raises(DatasetError, match="entire connected"):
        validate_assignments(deepcopy(records), changes[:1])
    frozen = deepcopy(records)
    validate_assignments(frozen, changes)
    validate_assignments(frozen, changes)
    with pytest.raises(DatasetError, match="frozen"):
        validate_assignments(frozen, [{**changes[0], "split": "train"}])


@pytest.mark.asyncio
async def test_postgres_export_snapshot_is_repeatable_read_read_only(monkeypatch):
    db = AsyncMock()
    db.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    context = AsyncMock()
    context.__aenter__.return_value = db
    monkeypatch.setattr("app.db.postgres.async_session_maker", lambda: context)
    async with snapshot_session() as session:
        assert session is db
    db.connection.assert_awaited_once_with(execution_options={"isolation_level": "REPEATABLE READ"})
    assert str(db.execute.call_args.args[0]) == "SET TRANSACTION READ ONLY"
    db.rollback.assert_awaited_once()
