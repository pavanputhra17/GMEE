"""Run the actual sklearn protocol on synthetic unit cases, never the live corpus."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree

import pytest

from app.services.eval.artifacts import write_artifacts
from app.services.eval.dataset import DatasetError, records_bytes, validate_dataset
from app.services.eval.metrics import best_f1_threshold
from app.services.eval.research import (
    ExperimentConfig,
    grouped_bootstrap_differences,
    load_jsonl,
    run_experiment,
)
from tests.test_research_support import research_records

CONFIG = ExperimentConfig(seed=1729, bootstrap=20)


@pytest.fixture(scope="module")
def fitted_experiment():
    return run_experiment(research_records(mutations=True), config=CONFIG)


def test_protocol_probability_semantics_and_multi_feature_ablations(fitted_experiment):
    report, predictions, _ = fitted_experiment
    assert report["status"] == "held_out_human_evaluation" and not report["publication_ready"]
    assert set(report["methods"]) == {"tfidf", "cosine", "cosine_calibrated", "logistic_all", "logistic_without_cosine", "logistic_without_entity", "logistic_without_lexical"}
    for name, method in report["methods"].items():
        assert method["fitted_on"] == "train" and method["threshold_selected_on"] == "dev"
        assert "best_f1" not in method["test"]
        if name in ("tfidf", "cosine"):
            assert method["test"]["brier"] is method["test"]["ece"] is None
            assert method["test_reliability"] == []
        else:
            assert method["test"]["brier"] is not None and method["test"]["ece"] is not None
    assert len(predictions) == 18 * 7
    assert all(p["probability"] is None for p in predictions if p["model"] in ("cosine", "tfidf"))
    assert all(0 <= p["probability"] <= 1 for p in predictions if p["score_kind"] == "calibrated_probability")


def test_deterministic_report_predictions_states_and_bootstrap(fitted_experiment):
    first = fitted_experiment
    second = run_experiment(list(reversed(research_records(mutations=True))), config=CONFIG)
    assert first == second
    assert len(first[0]["source_sha256"]) >= 7
    assert "scikit-learn" in first[0]["versions"]


def test_test_text_features_and_labels_cannot_change_training_or_dev_selection():
    records = research_records()
    report, _, states = run_experiment(records, config=CONFIG)
    modified = deepcopy(records)
    for record in modified:
        if record["split"] != "test":
            continue
        record["text_a"] += " zzqxqqonlytestzzz"
        record["cosine_score"] = -record["cosine_score"]
        record["features"]["entity_jaccard"] = 0.33
        record["gold_label"] = "DISTINCT" if record["gold_label"] != "DISTINCT" else "SAME_STORY"
        for vote in record["human_labels"]:
            vote["label"] = record["gold_label"]
    changed, _, changed_states = run_experiment(modified, config=CONFIG)
    assert states == changed_states
    assert "zqx" not in changed_states["tfidf"]["vocabulary"]
    for name in report["methods"]:
        assert report["methods"][name]["fitted_state_sha256"] == changed["methods"][name]["fitted_state_sha256"]
        assert report["methods"][name]["threshold"] == changed["methods"][name]["threshold"]
        assert report["methods"][name]["dev"] == changed["methods"][name]["dev"]


def test_cosine_threshold_selected_on_dev_not_test(fitted_experiment):
    report, predictions, _ = fitted_experiment
    dev = [p for p in predictions if p["split"] == "dev" and p["model"] == "cosine"]
    selected = best_f1_threshold([p["score"] for p in dev], [p["gold_relatedness"] for p in dev])
    assert report["methods"]["cosine"]["threshold"] == selected["threshold"]
    assert all(p["dev_threshold"] == selected["threshold"] for p in predictions if p["model"] == "cosine")


def test_group_calibration_fold_evidence_never_contains_dev_or_test(fitted_experiment):
    report, _, states = fitted_experiment
    train = set(report["training_pair_ids"])
    held_out = set(report["dev_pair_ids"] + report["test_pair_ids"])
    group_by_pair = report["validation"]["group_by_pair"]
    for name, state in states.items():
        if not name.startswith("logistic"):
            continue
        for fold in state["folds"]:
            fit, calibration = set(fold["fit_pair_ids"]), set(fold["calibration_pair_ids"])
            assert fit | calibration == train
            assert not (fit | calibration) & held_out
            assert not {group_by_pair[p] for p in fit} & {group_by_pair[p] for p in calibration}


def test_no_train_entity_evidence_cannot_be_enabled_from_test():
    records = research_records()
    for record in records:
        if record["split"] == "train":
            record["features"]["entity_jaccard"] = None
    report, _, _ = run_experiment(records, config=CONFIG)
    assert "logistic_without_entity" not in report["methods"]
    assert "entity_jaccard" not in report["methods"]["logistic_all"]["features"]
    assert any("no entity_jaccard evidence in train" in warning for warning in report["warnings"])


def test_mutation_predictions_are_actual_analyzer_outputs_and_separate(fitted_experiment):
    from app.services.verdict.mutation_diff import diff_versions

    report, predictions, _ = fitted_experiment
    mutation = report["mutation_evaluation"]
    assert mutation["status"] == "evaluated" and mutation["n_gold_pairs"] == 6
    assert mutation["analyzer"].endswith("mutation_diff.diff_versions")
    assert mutation["macro_f1"] is not None
    for prediction in predictions:
        actual = diff_versions(prediction["text_a"], prediction["text_b"])["mutation_types"]
        assert prediction["predicted_mutation_types"] == sorted(set(actual))
    assert mutation["errors"]  # Unrelated pairs must not magically get gold-based predictions.
    assert all("false_negative_pair_ids" in analysis for analysis in report["test_error_analysis"].values())


def test_missing_mutation_gold_is_reported_unavailable():
    report, predictions, _ = run_experiment(research_records(), config=CONFIG)
    assert report["mutation_evaluation"]["status"] == "unavailable"
    assert all(p["predicted_mutation_types"] is None for p in predictions)


def test_grouped_paired_bootstrap_uses_components_and_fixed_thresholds():
    all_records = research_records()
    validation = validate_dataset(all_records)
    test = [r for r in all_records if r["split"] == "test"]
    labels = [r["gold_label"] != "DISTINCT" for r in test]
    scores = {"perfect": [0.9 if y else 0.1 for y in labels], "flipped": [0.1 if y else 0.9 for y in labels]}
    args = (test, scores, {"perfect": 0.5, "flipped": 0.5}, validation["group_by_pair"], 50, 1729)
    bootstrap = grouped_bootstrap_differences(*args)
    assert bootstrap == grouped_bootstrap_differences(*args)
    assert bootstrap["independent_groups"] == 3 and bootstrap["valid_resamples"] == 50
    assert bootstrap["paired"] and bootstrap["thresholds_frozen_from"] == "dev"
    f1 = bootstrap["comparisons"][0]["metrics"]["f1"]
    assert f1["ci95"]["low"] == f1["ci95"]["high"] == f1["observed"]


def test_artifacts_actual_hashes_csv_predictions_and_svg(fitted_experiment, tmp_path):
    report, predictions, states = deepcopy(fitted_experiment)
    directory = tmp_path / "experiment"
    manifest = write_artifacts(report, predictions, states, directory)
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    for filename in ("pr.svg", "f1.svg", "reliability.svg"):
        root = ElementTree.fromstring((directory / filename).read_text(encoding="utf-8"))
        assert root.tag.endswith("svg")
    assert json.loads((directory / "pair_predictions.json").read_text(encoding="utf-8")) == predictions
    assert (directory / "pair_predictions.csv").read_text(encoding="utf-8").count("\n") == len(predictions) + 1
    markdown = (directory / "report.md").read_text(encoding="utf-8")
    assert "not certify publication validity" in markdown and "Raw cosine" in markdown
    with pytest.raises(DatasetError, match="not empty"):
        write_artifacts(report, predictions, states, directory)


def test_actual_cli_accepts_versioned_human_jsonl_and_refuses_weak_gold(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = root / "backend" / "scripts" / "run_research_experiment.py"
    dataset = tmp_path / "synthetic-unit-only.jsonl"
    dataset.write_bytes(records_bytes(research_records()))
    command = [sys.executable, str(script), "--dataset", str(dataset), "--output-dir", str(tmp_path / "run"), "--bootstrap", "20", "--seed", "1729"]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=90, check=False)
    assert completed.returncode == 0, completed.stderr
    report = json.loads((tmp_path / "run" / "report.json").read_text(encoding="utf-8"))
    assert report["dataset_sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert report["publication_ready"] is False
    weak = research_records()
    weak[0]["provenance"]["gold_origin"] = "automatic"
    dataset.write_bytes(records_bytes(weak))
    command[command.index(str(tmp_path / "run"))] = str(tmp_path / "refused")
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=90, check=False)
    assert completed.returncode == 2 and "human gold" in completed.stderr
    assert not (tmp_path / "refused").exists()


def test_jsonl_duplicate_fields_are_not_silently_overwritten(tmp_path):
    path = tmp_path / "ambiguous.jsonl"
    path.write_text('{"gold_label":"DISTINCT","gold_label":"SAME_STORY"}\n', encoding="utf-8")
    with pytest.raises(DatasetError, match="Duplicate JSON field"):
        load_jsonl(path)
