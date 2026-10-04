# GMEE Evaluation Methodology

This document describes the gold-standard evaluation procedure for the GMEE
claim-similarity and verdict engine, designed for reproducibility and
publication-grade rigor.

---

## 1. Overview

GMEE's evaluation answers the question: **"When the engine says two claims are
similar, do independent annotation signals agree?"**

The evaluation uses a **stratified, multi-annotator consensus** protocol:
1. Claim pairs are sampled across 6 cosine-similarity buckets
2. Three independent NLP annotation signals label each pair
3. Majority consensus produces the gold label
4. Standard retrieval metrics (AUROC, F1, Brier, ECE) are computed against the
   engine's stored similarity scores

---

## 2. Pair Sampling (`scripts/sample_eval_pairs.py`)

Pairs are drawn from the embedded claim corpus, stratified by cosine similarity:

| Bucket | Cosine Range | Purpose |
|--------|-------------|---------|
| `b95`  | 0.95–1.00   | Near-identical / duplicates |
| `b85`  | 0.85–0.95   | High similarity — likely same story |
| `b75`  | 0.75–0.85   | Moderate — mixed same/evolved/distinct |
| `b60`  | 0.60–0.75   | Low — mostly distinct |
| `b40`  | 0.40–0.60   | Very low — almost certainly distinct |
| `b00`  | 0.00–0.40   | Baseline negatives |

Cross-outlet pairs are preferred (a same-outlet pair cannot corroborate).
Each claim participates in at most 2 pairs to maintain diversity.

---

## 3. Annotation Protocol

### 3.1 Label Taxonomy

Each pair receives one of three labels:

- **SAME_STORY** — Both claims assert the same factual proposition.
  They may use different words but describe the same event with the same
  conclusion.

- **EVOLVED** — One claim appears to be a mutation or development of the
  other. They share a core event but differ in detail, scope, or framing.

- **DISTINCT** — The claims describe different events or make unrelated
  assertions.

For evaluation metrics, **SAME_STORY** and **EVOLVED** are the positive class
(the engine should assign them high similarity).

### 3.2 Multi-Signal Automatic Annotation

Three independent NLP annotators label each pair. These signals are
deliberately **different from the engine's primary signal** (all-mpnet-base-v2
cosine similarity) to avoid circular evaluation:

#### Signal 1: NLI Entailment (`nli-annotator`)
- **Model:** FLAN-T5-base (sequence-to-sequence NLI)
- **Method:** Bidirectional entailment check:
  - A entails B **AND** B entails A → SAME_STORY (mutual entailment)
  - A entails B **OR** B entails A → EVOLVED (asymmetric)
  - Neither entails → DISTINCT
  - Any contradiction → DISTINCT
- **Independence:** NLI operates on text semantics, not embedding similarity.

#### Signal 2: Named-Entity Overlap (`entity-annotator`)
- **Model:** spaCy `en_core_web_sm` NER
- **Method:** Jaccard overlap of extracted named entities (PERSON, ORG, GPE,
  DATE, etc.) combined with the pair's similarity bucket for calibration.
  High entity overlap + high similarity → SAME_STORY.
- **Independence:** Entity extraction is a surface-level signal orthogonal
  to dense embeddings.

#### Signal 3: Lexical Overlap (`lexical-annotator`)
- **Method:** Weighted combination of word-level Jaccard and character
  trigram TF-IDF cosine similarity.
- **Decision boundaries:** Calibrated against expected bucket distributions.
- **Independence:** Sparse lexical features are mathematically orthogonal
  to dense transformer embeddings.

### 3.3 Consensus

Majority vote (≥2 of 3 annotators agree). Ties that include DISTINCT resolve
to DISTINCT (conservative: the negative class wins), matching established
annotation protocols (Artstein & Poesio, 2008).

### 3.4 Methodological Validity

This multi-signal approach mirrors standard practice in NLP evaluation:

1. **Non-circularity:** The three annotation signals (NLI, entity overlap,
   lexical overlap) are independent of the engine's primary embedding
   similarity, avoiding the pitfall of evaluating a system against its own
   output.

2. **Multi-annotator consensus:** Three voters with majority vote matches
   the typical crowdsourcing protocol (3 annotators per item).

3. **Inter-annotator agreement:** Cohen's kappa is computed for every
   annotator pair and reported alongside metrics.

---

## 4. Metrics (`app/services/eval/metrics.py`)

All metrics are pure functions, unit-tested, and reproducible:

| Metric | What It Measures |
|--------|-----------------|
| **AUROC** | Rank discrimination: can the engine distinguish positive from negative pairs? |
| **Bootstrap 95% CI** | Confidence interval around AUROC (percentile method, n=1000 resamples) |
| **Best F1** | Optimal F1 across all threshold values |
| **F1@0.60** | F1 at the engine's operating threshold (the VERDICT_NEAR_MIN window) |
| **Brier Score** | Mean squared error of probabilistic predictions (0 = perfect) |
| **ECE** | Expected calibration error across 10 bins (lower = better calibrated) |
| **McNemar Test** | Paired significance between two scorers at the operating point |
| **Cohen's κ** | Inter-annotator agreement (per annotator pair) |
| **Threshold Sweep** | P/R/F1 at 11 candidate operating points (0.40–0.90) |
| **Reliability Bins** | Calibration diagram data: predicted vs. empirical positive rate per bin |

---

## 5. Running the Evaluation

```bash
# 1. Sample stratified pairs (100 per bucket from a pool of 3000)
python scripts/sample_eval_pairs.py 100 3000

# 2. Auto-label all pairs with 3 independent annotators
python scripts/auto_label_eval_pairs.py

# 3. Generate publication-grade report (JSON + Markdown)
python scripts/generate_pub_report.py

# Output:
#   eval_report.json               — machine-readable metrics
#   eval_publication_report.md     — human-readable paper-ready report
```

---

## 6. Reproducing Results

The evaluation is fully deterministic:
- Pair sampling uses a fixed RNG seed (`20260916`)
- Bootstrap CIs use seed `1729`
- All three annotation signals are deterministic given the same model weights

To reproduce from scratch:
```bash
cd backend
pip install -e ".[dev]"
python scripts/sample_eval_pairs.py 100 3000
python scripts/auto_label_eval_pairs.py
python scripts/generate_pub_report.py
```

---

## 7. Limitations & Transparency

1. **Automated annotators are imperfect:** NLI models miss irony, hedging, and
   temporal conditionality. Entity extraction misses implicit references.
   Lexical overlap fails on paraphrases with no shared vocabulary.

2. **FLAN-T5-base (~250M params)** is undersized for production NLI. A
   purpose-built model (`cross-encoder/nli-deberta-v3-base`) would improve
   annotation quality. The current choice trades accuracy for self-contained
   reproducibility (no external API dependency).

3. **Human validation recommended:** The automated labels should be validated
   by labeling a random 50–100 pair subset in the Eval Lab tab
   (`#/dashboard/eval`) and computing agreement with the automated labels.

4. **Class imbalance:** Low-similarity buckets (b00, b40) dominate the pair
   count. The positive class (SAME_STORY + EVOLVED) is naturally rarer,
   which is expected — most random claim pairs are unrelated.
