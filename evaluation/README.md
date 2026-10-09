# GMEE Evaluation Harness

This directory contains the benchmarking, dataset download, and evaluation infrastructure for GMEE (Global Misinformation Evolution Engine).

## Directory Structure

```text
evaluation/
  README.md
  data/
    baselines/       # Downloaded benchmark datasets (LIAR, ClaimBuster, MultiFC, FEVER)
    claim_pairs/     # Annotation schema, templates, and annotated claim pairs
    verdicts/        # Verification datasets and intermediate outputs
  scripts/           # Evaluation and baseline benchmark runners
  results/           # Output metrics in JSON and Markdown formats
```

---

## Evaluation Scripts & CLI Instructions

### 1. Download Benchmark Datasets (`download_datasets.py`)
Downloads publicly available datasets (LIAR, ClaimBuster, MultiFC, FEVER dev) and writes a download manifest.

```bash
python evaluation/scripts/download_datasets.py --output evaluation/data/baselines/
```

### 2. Claim Extraction Evaluator (`eval_claim_extraction.py`)
Evaluates claim extraction precision, recall, and F1 on LIAR or ClaimBuster test sets.

```bash
# Evaluate on LIAR test set:
python evaluation/scripts/eval_claim_extraction.py \
  --dataset liar \
  --data-path evaluation/data/baselines/liar_test.csv \
  --output evaluation/results/claim_extraction_liar.json \
  --sample-size 500

# Evaluate on ClaimBuster test set:
python evaluation/scripts/eval_claim_extraction.py \
  --dataset claimbuster \
  --data-path evaluation/data/baselines/claimbuster_test.csv \
  --output evaluation/results/claim_extraction_claimbuster.json \
  --sample-size 500
```

### 3. Mutation Detection Evaluator (`eval_mutation_detection.py`)
Evaluates embedding-based mutation detection against human-annotated claim pairs.

```bash
python evaluation/scripts/eval_mutation_detection.py \
  --pairs evaluation/data/claim_pairs/pairs_annotated.csv \
  --output evaluation/results/mutation_detection.json \
  --threshold 0.85
```

### 4. Verdict Engine Evaluator & Ablation (`eval_verdict_engine.py`)
Evaluates Verdict Engine probabilistic verification and performs a signal ablation sweep.

```bash
python evaluation/scripts/eval_verdict_engine.py \
  --data evaluation/data/baselines/fever_dev.jsonl \
  --output evaluation/results/verdict_engine.json \
  --sample-size 300
```

### 5. Graph Quality Evaluator (`eval_graph_quality.py`)
Directly inspects the PostgreSQL store to compute temporal validity rate, semantic consistency, and graph connectivity metrics.

```bash
python evaluation/scripts/eval_graph_quality.py \
  --db-url "postgresql+asyncpg://postgres:postgres@localhost:55432/gmee" \
  --output evaluation/results/graph_quality.json
```
