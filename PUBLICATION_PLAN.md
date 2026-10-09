# GMEE — Publication-Level Implementation Plan

> **FOR AI AGENTS:** Read the RULES section first. Every rule is mandatory.
> Violating any rule — even partially — is grounds to stop and ask the user.
> Do not interpret ambiguity in your favour. When in doubt, ask.

---

## ══════════════════════════════════════════
## SECTION 0 — MANDATORY AI AGENT RULES
## ══════════════════════════════════════════

These rules apply to every AI agent, every session, for the entire duration
of this publication campaign. They override all other instructions.

---

### RULE 0 — Read Before You Act

Before writing a single line of code or text, the agent MUST:

1. Read this entire file.
2. Read `HANDOFF.md`.
3. Read `ARCHITECTURE.md`.
4. Identify the current phase (the first phase with unchecked `[ ]` tasks).
5. Confirm which specific task within that phase it will work on.

**An agent that skips this step MUST NOT proceed.**

---

### RULE 1 — One Phase at a Time

- Work on exactly **one phase at a time**.
- Do not begin Phase N+1 until every task in Phase N is checked `[x]`.
- Do not mark a task `[x]` unless the deliverable exists on disk and passes its stated verification command.
- If a phase is already complete, skip to the next incomplete phase.

---

### RULE 2 — Scope Freeze (No Unsolicited Changes)

The agent is **forbidden** from doing any of the following unless the user explicitly requests it in the current session:

- Refactoring existing working code
- Adding new API endpoints
- Changing the frontend UI or CSS
- Updating dependencies (`pyproject.toml`, `package.json`)
- Creating new database migrations (Alembic)
- Modifying Docker Compose or infra configs
- Changing `.env` or `.env.example`
- Renaming or moving existing files
- Adding comments or docstrings to files not touched by the current task

The only permitted changes are those required by the current task's **Deliverables** list. Everything else is out of scope.

---

### RULE 3 — No Hallucinated Results

When running evaluations or benchmarks, the agent MUST:

- Use real data. Never fabricate metric numbers.
- If a dataset download fails, report the error and ask the user — do not substitute dummy data.
- If a model inference is too slow, reduce the sample size and document the reduction — do not fill in results from memory.

Any evaluation file (`.json`, `.csv`, `.md`) containing fabricated numbers is worse than no file at all. **Fabrication invalidates the paper.**

---

### RULE 4 — Exact File Paths

Every deliverable in this plan specifies an exact file path relative to the repo root. The agent MUST create files at those exact paths. Do not create files in different directories without user approval.

---

### RULE 5 — Git Discipline

- Never run `git push` without explicit user instruction.
- Never run `git commit` without explicit user instruction.
- Stage only the files touched by the current task (`git add <specific files>` not `git add .`).
- When instructed to commit, use the exact commit message specified in the phase's commit block.

---

### RULE 6 — Test Gate

The full backend test suite must pass (`80 passed`) before and after every code change. Run:

```powershell
# from backend/
.venv\Scripts\python.exe -m pytest tests/ -q --tb=short
```

If tests drop below 80 passed, fix the regression before doing anything else. Do not proceed with paper tasks while tests are red.

---

### RULE 7 — No Style Opinions

The agent does not choose variable names, function signatures, or algorithm design freely. When implementation choices are needed that are not specified in this plan, the agent MUST ask the user before proceeding.

---

### RULE 8 — Cite Real Papers Only

Every reference in `related_work.md`, every comparison, every metric name must cite a real, verifiable paper. Use arXiv IDs or DOIs. Do not cite papers from memory without verifying the title and authors exist via web search.

---

### RULE 9 — Reproducibility First

Every script added under `evaluation/` MUST:

- Accept command-line arguments (not hard-coded paths).
- Print a human-readable summary to stdout.
- Write results to a JSON file.
- Be runnable with a single command documented in `evaluation/README.md`.

---

### RULE 10 — No Breaking API Changes

The public API (`/api/v1/*`) must remain backward-compatible throughout all phases. Adding new read-only endpoints is permitted. Changing existing endpoint schemas is forbidden.

---

## ══════════════════════════════════════════
## SECTION 1 — PROJECT STATE SNAPSHOT
## ══════════════════════════════════════════

### What exists and must NOT be rebuilt

| Component | Status | Location |
|---|---|---|
| FastAPI backend + all pipelines | ✅ Complete | `backend/app/` |
| PostgreSQL + pgvector + Neo4j + Redis | ✅ Configured | `infra/docker-compose.yml` |
| Claim extraction (Anthropic + HF fallback) | ✅ Complete | `backend/app/services/nlp/llm_client.py` |
| BGE-M3 embeddings via pgvector | ✅ Complete | `backend/app/services/nlp/embedding_service.py` |
| BERTopic clustering + UMAP | ✅ Complete | `backend/app/services/evolution/cluster_service.py` |
| Mutation detection (cosine chain + EVOLVED_FROM) | ✅ Complete | `backend/app/services/evolution/mutation_detector.py` |
| 5-signal Verdict Engine (log-odds fusion) | ✅ Complete | `backend/app/services/verdict/engine.py` |
| NLI stance via Flan-T5 | ✅ Complete | `backend/app/services/verdict/engine.py` |
| Neo4j graph (EVOLVED_FROM, SIMILAR_TO) | ✅ Complete | `backend/app/services/evolution/neo4j_writer.py` |
| React dashboard + demo telemetry | ✅ Complete | `frontend/src/` |
| 80/80 backend tests passing | ✅ Green | `backend/tests/` |
| Frontend lint + build clean | ✅ Green | `frontend/` |
| CI (GitHub Actions) | ✅ Green | `.github/workflows/` |

### What is missing (this plan fills these gaps)

1. **Evaluation harness** — no benchmark numbers exist
2. **Labeled dataset** — no human-annotated claim pairs exist
3. **Baseline comparisons** — no comparison to existing systems
4. **Ablation study** — no per-signal Verdict Engine ablation
5. **Corpus statistics** — no ingestion run documented
6. **Paper text** — not started
7. **arXiv submission** — not submitted

---

## ══════════════════════════════════════════
## SECTION 2 — PHASES
## ══════════════════════════════════════════

---

## PHASE 1 — Evaluation Infrastructure
### Goal: Build scripts to measure system performance. No paper-writing yet.
### Estimated effort: 5–7 days

---

### Task 1.1 — Create evaluation directory scaffold

**Deliverables** (create exactly these files, nothing else):

```
evaluation/
  README.md
  data/
    .gitkeep
    claim_pairs/
      .gitkeep
    verdicts/
      .gitkeep
    baselines/
      .gitkeep
  scripts/
    eval_claim_extraction.py
    eval_mutation_detection.py
    eval_verdict_engine.py
    eval_graph_quality.py
    download_datasets.py
  results/
    .gitkeep
```

**Permitted actions:**
- Create the directories and files listed above
- Write `evaluation/README.md` with run instructions for each script

**Forbidden actions:**
- Modifying any file outside `evaluation/`
- Writing functional code in scripts yet (stubs only at this step)

**Done when:**
```powershell
ls evaluation/scripts/  # 5 .py files
ls evaluation/data/     # claim_pairs/, verdicts/, baselines/ subdirs
```

---

### Task 1.2 — Download and prepare benchmark datasets

**Target datasets** (all publicly available, no sign-up required):

| Dataset | Purpose | Source |
|---|---|---|
| LIAR | Claim truthfulness labels (6-class) | HuggingFace `datasets` library |
| ClaimBuster scored claims | Claim-worthiness scores | Zenodo record 3609356 |
| MultiFC | Multi-domain fact check | GitHub: copenlu/multifc |
| FEVER dev set (19,998 rows) | Claim + evidence + label | fever.ai/resources.html |

**Script:** `evaluation/scripts/download_datasets.py`

**Required CLI interface:**
```bash
python evaluation/scripts/download_datasets.py --output evaluation/data/baselines/
```

**Required outputs:**
```
evaluation/data/baselines/
  liar_test.csv           # columns: id, statement, label
  claimbuster_test.csv    # columns: text, cfs_score
  multifc_test.csv        # columns: claimID, claim, label
  fever_dev.jsonl         # fields: claim, label (SUPPORTS/REFUTES/NOT ENOUGH INFO)
  download_manifest.json  # {dataset, filename, rows, downloaded_at}
```

**Done when:** `download_manifest.json` exists with all 4 datasets listed and row count > 0.

**Forbidden:** Using any dataset that requires a paid API key or institutional access.

---

### Task 1.3 — Claim extraction evaluator

**File:** `evaluation/scripts/eval_claim_extraction.py`

**What it measures:**

Run GMEE's `HuggingFaceLLMClient` on LIAR and ClaimBuster test sets.
Compare whether GMEE identifies claim-worthy sentences consistently with human labels.

**Exact metric definitions:**

```
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * P * R / (P + R)

Label mapping:
  LIAR: "true", "mostly-true", "half-true" → claim_worthy = 1
        "barely-true", "false", "pants-fire" → claim_worthy = 0
  ClaimBuster: cfs_score >= 0.5 → claim_worthy = 1
```

**Required CLI:**
```bash
python evaluation/scripts/eval_claim_extraction.py \
  --dataset liar \
  --data-path evaluation/data/baselines/liar_test.csv \
  --output evaluation/results/claim_extraction_liar.json \
  --sample-size 500
```

**Required JSON output schema:**
```json
{
  "dataset": "liar",
  "sample_size": 500,
  "precision": 0.0,
  "recall": 0.0,
  "f1": 0.0,
  "tp": 0, "fp": 0, "fn": 0, "tn": 0,
  "model_used": "google/flan-t5-base",
  "eval_timestamp": "ISO8601",
  "notes": ""
}
```

**Forbidden:**
- Modifying `HuggingFaceLLMClient` to improve scores
- Filtering test set to cherry-pick easier examples
- Running on fewer than 200 samples without documenting the reason

**Done when:** JSON file exists with non-zero `f1` value.

---

### Task 1.4 — Mutation detection evaluator + annotation scaffold

**Step A — Schema:**

Create `evaluation/data/claim_pairs/annotation_schema.json`:
```json
{
  "version": "1.0",
  "labels": {
    "EVOLVED_FROM": "Claim B is a semantic mutation of Claim A — same core assertion, different framing, emphasis, or added/dropped details. Both refer to the same real-world event.",
    "SIMILAR_TO": "Claims share a topic but assert different (non-mutated) facts.",
    "UNRELATED": "Claims are about different events or topics.",
    "DUPLICATE": "Claims are semantically identical or near-identical."
  },
  "fields": ["pair_id","claim_a","claim_b","source_a","source_b","date_a","date_b","label","annotator_confidence","notes"]
}
```

**Step B — Template:**

Create `evaluation/data/claim_pairs/pairs_template.csv` with header row only:
```
pair_id,claim_a,claim_b,source_a,source_b,date_a,date_b,label,annotator_confidence,notes
```

**Step C — Annotation guide:**

Create `evaluation/data/claim_pairs/ANNOTATION_GUIDE.md` containing:
- Full label definitions
- 10 worked examples (5 EVOLVED_FROM, 3 SIMILAR_TO, 2 UNRELATED)
- Instructions to produce 120 labeled pairs minimum:
  - 40 EVOLVED_FROM
  - 30 SIMILAR_TO
  - 30 UNRELATED
  - 20 DUPLICATE
- SQL query to extract candidate pairs from the corpus

**Step D — Evaluator script:**

**File:** `evaluation/scripts/eval_mutation_detection.py`

```bash
python evaluation/scripts/eval_mutation_detection.py \
  --pairs evaluation/data/claim_pairs/pairs_annotated.csv \
  --output evaluation/results/mutation_detection.json \
  --threshold 0.85
```

Script loads annotated pairs, computes BGE-M3 cosine similarity (reusing
`sentence_transformers.util.cos_sim`) for each pair, predicts EVOLVED_FROM
if sim >= threshold, computes precision/recall/F1.

**Required JSON output:**
```json
{
  "threshold": 0.85,
  "n_pairs": 0,
  "precision": 0.0,
  "recall": 0.0,
  "f1": 0.0,
  "confusion_matrix": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
  "label_distribution": {"EVOLVED_FROM": 0, "SIMILAR_TO": 0, "UNRELATED": 0, "DUPLICATE": 0},
  "eval_timestamp": "ISO8601"
}
```

**Done when:** Schema, template, guide, and script all exist. Script runs without error on the template CSV (output will have n_pairs=0).

---

### Task 1.5 — Verdict engine evaluator + ablation script

**File:** `evaluation/scripts/eval_verdict_engine.py`

**Ground truth mapping (FEVER → GMEE bands):**

```
SUPPORTS        → expected: SUPPORTED or PARTIALLY_SUPPORTED
REFUTES         → expected: DISPUTED or PENDING_DISPUTE
NOT ENOUGH INFO → expected: UNRESOLVED
```

**Caveat:** FEVER uses Wikipedia; GMEE uses live web corpus.
This is an approximation. Document this limitation explicitly in the JSON output.

**Required CLI:**
```bash
python evaluation/scripts/eval_verdict_engine.py \
  --data evaluation/data/baselines/fever_dev.jsonl \
  --output evaluation/results/verdict_engine.json \
  --sample-size 300
```

**Computes:**
- Per-class F1 (SUPPORTED, DISPUTED, UNRESOLVED)
- Macro-F1
- Band confusion matrix (3×3)
- Ablation over signals (zero each weight one at a time, rerun combine())

**Ablation: do NOT modify VerdictEngine class.** Call `VerdictEngine.combine()` with
modified signal lists directly in the evaluation script.

**Required JSON output includes:**
```json
{
  "macro_f1": 0.0,
  "ablation": {
    "full_model":                  {"macro_f1": 0.0},
    "without_corroboration":       {"macro_f1": 0.0},
    "without_contradiction":       {"macro_f1": 0.0},
    "without_track_record":        {"macro_f1": 0.0},
    "without_entity_grounding":    {"macro_f1": 0.0},
    "without_language":            {"macro_f1": 0.0}
  },
  "limitation": "FEVER uses Wikipedia evidence; GMEE uses live web corpus. Results are approximate.",
  "eval_timestamp": "ISO8601"
}
```

**Done when:** JSON file exists with all 6 ablation entries.

---

### Task 1.6 — Graph quality evaluator

**File:** `evaluation/scripts/eval_graph_quality.py`

**Queries PostgreSQL directly** via SQLAlchemy + `ClaimRelationship` and `Claim` models.
Does NOT require Neo4j or Docker to be running.

**Metrics:**

1. **Temporal validity rate** — For every `EVOLVED_FROM` edge (A→B), verify
   `B.published_at > A.published_at`. Rate = valid / total edges.

2. **Semantic consistency rate** — For every `EVOLVED_FROM` edge, cosine
   similarity of embeddings must be >= `EVOLUTION_SIMILARITY_THRESHOLD`.

3. **Graph connectivity stats:**
   - Total claim nodes
   - Total EVOLVED_FROM edges
   - Total SIMILAR_TO edges
   - Average out-degree
   - Longest mutation chain (max path length in EVOLVED_FROM subgraph)

**Required CLI:**
```bash
python evaluation/scripts/eval_graph_quality.py \
  --db-url "postgresql+asyncpg://user:pass@host/db" \
  --output evaluation/results/graph_quality.json
```

**Done when:** JSON file exists with all 5 metric categories.

---

### Phase 1 Commit Block

```
git add evaluation/
git commit -m "eval: add evaluation harness — scripts, dataset downloader, annotation scaffold (Phase 1)"
```

---

## PHASE 2 — Run Evaluations and Collect Numbers
### Goal: Populate all result JSON files with real numbers.
### Estimated effort: 3–5 days (includes user annotation session for task 2.2)

**Prerequisites:**
- Phase 1 complete (all scripts exist and are tested with `--help`)
- Docker Compose stack running: `docker compose -f infra/docker-compose.yml up`
- At least 500 articles ingested (trigger collection via POST `/api/v1/collection/trigger`)

---

### Task 2.1 — Run claim extraction eval

```powershell
python evaluation/scripts/download_datasets.py --output evaluation/data/baselines/

python evaluation/scripts/eval_claim_extraction.py `
  --dataset liar `
  --data-path evaluation/data/baselines/liar_test.csv `
  --output evaluation/results/claim_extraction_liar.json `
  --sample-size 500

python evaluation/scripts/eval_claim_extraction.py `
  --dataset claimbuster `
  --data-path evaluation/data/baselines/claimbuster_test.csv `
  --output evaluation/results/claim_extraction_claimbuster.json `
  --sample-size 500
```

**Done when:** Both JSON files exist with `f1 > 0`.

---

### Task 2.2 — Human annotation session

> ⚠️ **THE AI AGENT CANNOT DO THIS TASK.** This is explicitly a human task.
> The agent's only role here is to generate the SQL query below and export
> candidate pairs to CSV upon user request. The agent must NOT assign labels.

**Instructions for the human annotator:**

1. Start Docker Compose and confirm the backend is healthy.
2. Run the following query against PostgreSQL to find candidate pairs:

```sql
SELECT
  c1.id              AS id_a,
  c1.claim_text      AS claim_a,
  c2.id              AS id_b,
  c2.claim_text      AS claim_b,
  cr.relationship_type,
  cr.score,
  a1.published_at    AS date_a,
  a2.published_at    AS date_b,
  s1.domain          AS source_a,
  s2.domain          AS source_b
FROM claim_relationships cr
JOIN claims   c1 ON cr.from_claim_id = c1.id
JOIN claims   c2 ON cr.to_claim_id   = c2.id
JOIN articles a1 ON c1.article_id    = a1.id
JOIN articles a2 ON c2.article_id    = a2.id
JOIN sources  s1 ON a1.source_id     = s1.id
JOIN sources  s2 ON a2.source_id     = s2.id
ORDER BY cr.score DESC
LIMIT 250;
```

3. Copy results to `evaluation/data/claim_pairs/pairs_template.csv`.
4. Fill in the `label` column for each row using the guide in `ANNOTATION_GUIDE.md`.
5. Save as `evaluation/data/claim_pairs/pairs_annotated.csv`.
6. Target: **120 rows minimum**, distribution per guide.

**Done when:** `pairs_annotated.csv` has >= 120 rows with the `label` column filled.

---

### Task 2.3 — Run mutation detection eval

```powershell
python evaluation/scripts/eval_mutation_detection.py `
  --pairs evaluation/data/claim_pairs/pairs_annotated.csv `
  --output evaluation/results/mutation_detection.json `
  --threshold 0.85

# Threshold sensitivity sweep
foreach ($t in @(0.75, 0.80, 0.85, 0.88, 0.90)) {
  python evaluation/scripts/eval_mutation_detection.py `
    --pairs evaluation/data/claim_pairs/pairs_annotated.csv `
    --output "evaluation/results/mutation_detection_t$t.json" `
    --threshold $t
}
```

**Done when:** 6 JSON files exist (1 main + 5 threshold variants).

---

### Task 2.4 — Run verdict engine eval + ablation

```powershell
python evaluation/scripts/eval_verdict_engine.py `
  --data evaluation/data/baselines/fever_dev.jsonl `
  --output evaluation/results/verdict_engine.json `
  --sample-size 300
```

**Done when:** JSON exists with non-zero `ablation.full_model.macro_f1`.

---

### Task 2.5 — Run graph quality eval

```powershell
python evaluation/scripts/eval_graph_quality.py `
  --db-url $env:POSTGRES_URL `
  --output evaluation/results/graph_quality.json
```

**Done when:** JSON exists with `temporal_validity_rate` between 0 and 1.

---

### Task 2.6 — Corpus statistics snapshot

Create `evaluation/results/corpus_stats.json` by querying the running database:

```json
{
  "snapshot_date": "ISO8601",
  "ingestion_sources": ["rss", "reddit", "newsapi"],
  "total_articles": 0,
  "total_claims": 0,
  "total_embedded_claims": 0,
  "total_cluster_runs": 0,
  "total_evolved_from_edges": 0,
  "total_similar_to_edges": 0,
  "longest_mutation_chain": 0,
  "unique_sources": 0,
  "date_range_start": "ISO8601",
  "date_range_end": "ISO8601",
  "embedding_model": "BAAI/bge-m3",
  "embedding_dim": 1024,
  "clustering_algorithm": "BERTopic+UMAP",
  "min_topic_size": 5,
  "evolution_threshold": 0.85,
  "similarity_threshold": 0.75
}
```

**Done when:** File exists with `total_claims > 0`.

---

### Phase 2 Commit Block

```
git add evaluation/data/ evaluation/results/
git commit -m "eval: populate benchmark results, annotation dataset, corpus statistics (Phase 2)"
```

---

## PHASE 3 — Baseline Comparisons
### Goal: Show GMEE performance vs. existing systems on the same tasks.
### Estimated effort: 4–6 days

---

### Task 3.1 — ClaimBuster baseline

**File:** `evaluation/scripts/baseline_claimbuster.py`

Downloads the public ClaimBuster model weights, runs it on the same
500-sample test set as task 1.3, outputs same JSON schema.

**Required output:** `evaluation/results/baseline_claimbuster.json`

---

### Task 3.2 — Sentence-BERT mutation baseline

**File:** `evaluation/scripts/baseline_sbert_mutation.py`

Uses `paraphrase-MiniLM-L6-v2` (small, fast, well-known) on the same
annotated pairs as task 1.4, same threshold, same JSON schema.

**Required output:** `evaluation/results/baseline_sbert_mutation.json`

---

### Task 3.3 — Majority-class verdict baseline

**File:** `evaluation/scripts/baseline_majority_verdict.py`

Predicts the majority class for every FEVER example.
Outputs same JSON schema as task 1.5.

**Required output:** `evaluation/results/baseline_majority_verdict.json`

---

### Task 3.4 — Comparison summary table

**File:** `evaluation/results/COMPARISON_TABLE.md`

| System | Task | Dataset | Precision | Recall | F1 |
|---|---|---|---|---|---|
| GMEE (BGE-M3) | Claim extraction | LIAR test | — | — | — |
| ClaimBuster | Claim extraction | LIAR test | — | — | — |
| GMEE (BGE-M3) | Claim extraction | ClaimBuster | — | — | — |
| GMEE (BGE-M3) | Mutation detection | 120 annotated pairs | — | — | — |
| SBERT-MiniLM | Mutation detection | same | — | — | — |
| GMEE VerdictEngine | Verdict | FEVER dev (300) | — | — | — |
| Majority class | Verdict | same | — | — | — |

**The AI agent fills numbers from the JSON files ONLY.**
**Forbidden:** entering any number that differs from the source JSON files.

---

### Phase 3 Commit Block

```
git add evaluation/scripts/baseline_* evaluation/results/COMPARISON_TABLE.md
git commit -m "eval: baseline comparisons and summary table (Phase 3)"
```

---

## PHASE 4 — Paper Structure and Writing
### Goal: Write a complete, submission-ready paper draft.
### Estimated effort: 10–14 days

---

### Task 4.0 — Paper directory scaffold

Create exactly:

```
paper/
  README.md
  sections/
    00_abstract.md
    01_introduction.md
    02_related_work.md
    03_system.md
    04_evaluation.md
    05_results.md
    06_discussion.md
    07_conclusion.md
  figures/
    fig1_architecture.svg
    fig2_mutation_graph.svg
    fig3_verdict_ablation.svg
  tables/
    tab1_claim_extraction.tex
    tab2_mutation_detection.tex
    tab3_verdict_ablation.tex
    tab4_corpus_stats.tex
  references.bib
  paper_draft.md
```

---

### Task 4.1 — Abstract (`paper/sections/00_abstract.md`)

**Length:** 150–200 words.

**Required structure:**
1. Problem sentence (misinformation mutation is understudied)
2. Gap sentence (no existing system does the full loop end-to-end)
3. Three sentences describing GMEE (pipeline, verdict engine, graph)
4. Key result sentence (include F1 numbers from evaluation results)
5. Availability sentence (open-source, reproducible)

**Forbidden:**
- Citing any paper not in `references.bib`
- Claiming numbers not present in `evaluation/results/`
- Using the word "novel" more than once

---

### Task 4.2 — Introduction (`paper/sections/01_introduction.md`)

**Length:** 500–700 words, 4 paragraphs.

**Paragraph 1 — Hook:**
A concrete example of a real claim mutation drawn from the ingested corpus.
Use actual claim texts from `evaluation/results/corpus_stats.json` date range.

**Paragraph 2 — Problem:**
Misinformation doesn't stay static — claims mutate as they spread.
Cite ≥ 3 papers on mutation/narrative drift. All must be in `references.bib`.

**Paragraph 3 — Gap:**
Existing systems detect OR track, not both. End with:
*"To the best of our knowledge, GMEE is the first open-source system to combine
real-time atomic claim extraction, embedding-based mutation detection,
graph-structured propagation tracking, and probabilistic verification in
a single unified pipeline."*

**Paragraph 4 — Contributions (bulleted list of exactly 4):**
- The GMEE end-to-end pipeline architecture
- The temporal mutation graph with EVOLVED_FROM chains
- The 5-signal transparent Verdict Engine with ablation study
- Open-source code and reproducible evaluation harness

---

### Task 4.3 — Related Work (`paper/sections/02_related_work.md`)

**Length:** 600–900 words, 4 subsections.

#### 2.1 Claim Detection and Extraction
Must cite: ClaimBuster (Arslan et al., 2020, DOI: 10.18653/v1/2020.emnlp-main.639),
ClaimRank (Jaradat et al., 2018), CheckThat! shared task (at least one edition).

#### 2.2 Fact Verification
Must cite: FEVER (Thorne et al., 2018, arXiv:1803.05355),
MultiFC (Augenstein et al., 2019, arXiv:1909.03242),
LIAR (Wang, 2017, arXiv:1705.00648).

#### 2.3 Misinformation Propagation
Must cite: Hoaxy (Shao et al., 2016),
FakeNewsNet (Shu et al., 2020),
CoAID (Cui and Lee, 2020).

#### 2.4 Graph-Based Approaches
Must cite: FactGraph (Luo et al., 2021),
KGAT (Liu et al., 2020),
at least one graph knowledge base survey.

**Forbidden:**
- Citing papers the agent cannot verify exist via web search
- Saying any cited system "fails" or is "wrong"

---

### Task 4.4 — System Description (`paper/sections/03_system.md`)

**Length:** 900–1200 words, 5 subsections.

**3.1 Architecture Overview** — Reference `fig1_architecture.svg`. One paragraph per pipeline stage.

**3.2 Claim Extraction** — Describe both backends (Anthropic Claude / Flan-T5 fallback).
State exact model IDs: `claude-haiku-4-5-20251001` and `google/flan-t5-base`.

**3.3 Embedding and Mutation Detection** — Describe BGE-M3 (1024-d, cite arXiv:2309.07597).
Describe cosine chain algorithm from `mutation_detector.py`. Include threshold table.

**3.4 Verdict Engine** — Describe all 5 signals with weights as a table.
Include log-odds fusion equation in LaTeX. Describe verdict bands.
Explain why `UNSUPPORTED ≠ DISPUTED` epistemically.

**3.5 Propagation Graph** — Describe Neo4j schema. Describe dual-write
(Postgres = system of record, Neo4j = read-optimised for path queries).

---

### Task 4.5 — Evaluation Setup (`paper/sections/04_evaluation.md`)

**Length:** 400–600 words.

**Must include:**
- Dataset descriptions with exact sample sizes from result JSONs
- Hardware specification (CPU model, RAM, GPU if used)
- Reproducibility statement with repo URL
- Explicit limitations of each evaluation (especially FEVER mismatch caveat)

---

### Task 4.6 — Results (`paper/sections/05_results.md`)

**Length:** 500–700 words + tables.

**Tables (reference LaTeX files from `paper/tables/`):**
- Table 1: Claim extraction (GMEE vs. ClaimBuster on LIAR + ClaimBuster datasets)
- Table 2: Mutation detection (GMEE BGE-M3 vs. SBERT + threshold sensitivity)
- Table 3: Verdict Engine ablation (full model vs. minus each signal)
- Table 4: Corpus and graph statistics

**Strict rule: Every number MUST trace verbatim to a file in `evaluation/results/`. No exceptions.**

---

### Task 4.7 — Discussion (`paper/sections/06_discussion.md`)

**Length:** 400–500 words.

**Must cover:**
1. What results confirm about the claim mutation hypothesis
2. Where GMEE outperforms baselines and the mechanism behind it
3. Where GMEE underperforms and why (honest, not defensive)
4. Explicit limitations:
   - English-only corpus (language bias)
   - Flan-T5 NLI is approximate (no training on GMEE corpus)
   - FEVER mismatch (Wikipedia evidence vs. live web)
   - Hand-tuned signal weights (not learned from labeled data)

---

### Task 4.8 — Conclusion (`paper/sections/07_conclusion.md`)

**Length:** 150–200 words.

**Must contain:**
- Mirror of contributions from Introduction (4 bullets)
- One sentence on future work (multi-lingual, learned weights, larger annotation)
- Reproducibility statement
- No new results or claims not discussed earlier in the paper

---

### Task 4.9 — References (`paper/references.bib`)

Every paper cited in sections 01–07 must have a verified BibTeX entry.
Use DBLP (https://dblp.org/) for canonical BibTeX.

**Forbidden:**
- Entries without `doi` or `url` field
- Entries with `year` beyond 2026
- Entries the agent cannot verify exist via web search

---

### Task 4.10 — Full draft assembly (`paper/paper_draft.md`)

Concatenate all sections in order with `---` separators.

Header:
```
**Target venue:** ACL System Demonstrations / EMNLP Findings
**Word count:** XXXX words (excluding references and figure captions)
**Submission deadline:** [USER TO FILL]
**arXiv categories:** cs.CL, cs.IR, cs.SI
```

---

### Phase 4 Commit Block

```
git add paper/
git commit -m "paper: full draft — abstract through conclusion, references, figures (Phase 4)"
```

---

## PHASE 5 — Review, Polish, and arXiv Prep
### Goal: Make the paper submission-ready.
### Estimated effort: 3–5 days

---

### Task 5.1 — Internal consistency check

Agent runs this checklist and writes results to `paper/consistency_check.md`:

- [ ] Every number in `05_results.md` traces to a JSON file in `evaluation/results/`
- [ ] Every citation in text has a BibTeX entry in `references.bib`
- [ ] Every figure referenced exists in `paper/figures/`
- [ ] Every table referenced exists in `paper/tables/`
- [ ] Abstract word count: 150–200
- [ ] Introduction word count: 500–700
- [ ] Total paper word count: 4000–6000
- [ ] No section contains "TODO" or "TBD"
- [ ] No section cites results not yet in `evaluation/results/`
- [ ] `paper/README.md` lists venue, deadline, and page limit

---

### Task 5.2 — Generate LaTeX tables

Convert each markdown table to LaTeX `tabular` with `booktabs` style.

```
paper/tables/tab1_claim_extraction.tex
paper/tables/tab2_mutation_detection.tex
paper/tables/tab3_verdict_ablation.tex
paper/tables/tab4_corpus_stats.tex
```

Numbers must match `evaluation/results/` JSON files verbatim.

---

### Task 5.3 — Generate figures

**`paper/figures/fig1_architecture.svg`:**
Clean SVG pipeline diagram based on `ARCHITECTURE.md`.
Colors: ink `#0a0a14` boxes, white text, data stores in light grey.

**`paper/figures/fig2_mutation_graph.svg`:**
Example mutation graph with 3–5 nodes and 2–4 EVOLVED_FROM edges.
Use real claim text from corpus if available; label "illustrative" if not.

**`paper/figures/fig3_verdict_ablation.svg`:**
Horizontal bar chart of macro-F1: full model vs. each ablated variant.
Numbers from `evaluation/results/verdict_engine.json` ablation section only.

---

### Task 5.4 — arXiv metadata file

Create `paper/arxiv_metadata.json`:

```json
{
  "title": "GMEE: A Real-Time System for Claim Mutation Tracking and Probabilistic Verification",
  "authors": ["[USER FILLS IN]"],
  "abstract": "[copy from 00_abstract.md after user approval]",
  "primary_category": "cs.CL",
  "cross_list": ["cs.IR", "cs.SI"],
  "license": "CC BY 4.0",
  "comments": "System demonstration paper. Code: [repo URL]",
  "submission_date": ""
}
```

---

### Task 5.5 — Add Paper section to README.md

Add ONLY the following section to the root `README.md`, immediately before the
final `## Repository Layout` section. No other changes to `README.md`.

```markdown
## Paper

If you use GMEE in your research, please cite:

\`\`\`bibtex
@misc{gmee2026,
  title={GMEE: A Real-Time System for Claim Mutation Tracking and Probabilistic Verification},
  author={[authors]},
  year={2026},
  eprint={[arXiv ID after submission]},
  archivePrefix={arXiv},
  primaryClass={cs.CL}
}
\`\`\`
```

---

### Phase 5 Commit Block

```
git add paper/ README.md
git commit -m "paper: polish, LaTeX tables, SVG figures, arXiv metadata (Phase 5)"
```

---

## PHASE 6 — Submission
### Goal: Submit to arXiv and target venue.
### Estimated effort: 1–2 days (human-driven)

---

### Task 6.1 — Pre-submission checklist (human + agent verify together)

- [ ] All Phase 1–5 tasks marked `[x]`
- [ ] Backend test suite: 80 passed, 0 failures (run `pytest tests/ -q`)
- [ ] Frontend lint: 0 errors, 0 warnings (run `npm run lint`)
- [ ] Frontend build: clean exit 0 (run `npm run build`)
- [ ] `paper/consistency_check.md`: all items green
- [ ] User has read and approved the full draft
- [ ] Repo is public (or will go public on arXiv submission date)
- [ ] `.gitignore` covers `.env`, secrets, and model weight files
- [ ] `evaluation/data/baselines/` CSV files are committed (no model weights committed)

---

### Task 6.2 — arXiv submission (HUMAN ONLY — agent cannot do this)

1. Convert `paper/paper_draft.md` to PDF (Pandoc or LaTeX).
2. Create account at https://arxiv.org if needed.
3. Upload PDF + source. Fill metadata from `paper/arxiv_metadata.json`.
4. Submit to `cs.CL`, cross-list `cs.IR`, `cs.SI`.
5. Record arXiv ID. Update `paper/arxiv_metadata.json` and README.md citation.

---

### Task 6.3 — Venue submission (HUMAN ONLY)

Recommended venues (check official sites for current deadlines):

| Venue | Page Limit | Track |
|---|---|---|
| ACL System Demonstrations | 6 + refs | System Demo |
| EMNLP Findings | 8 + refs | Findings |
| CIKM Full Paper | 9 + refs | Research |
| ECIR Short Paper | 12 + refs | Short Paper |
| COLING | 8 + refs | Main |

---

### Phase 6 Commit Block

```
git add paper/arxiv_metadata.json README.md
git commit -m "paper: record arXiv ID and finalize submission metadata (Phase 6)"
```

---

## ══════════════════════════════════════════
## SECTION 3 — TASK CHECKLIST (LIVING DOCUMENT)
## ══════════════════════════════════════════

Update this checklist as tasks complete. The current active phase is the
first phase with any `[ ]` unchecked.

**NEVER mark `[x]` without the task's done-condition satisfied.**

### Phase 1 — Evaluation Infrastructure
- [x] 1.1 Directory scaffold created (`evaluation/` tree exists)
- [x] 1.2 Dataset download script working; all 4 datasets present with manifest
- [x] 1.3 Claim extraction evaluator script complete and tested
- [x] 1.4 Mutation detection evaluator + annotation template + guide complete
- [x] 1.5 Verdict engine evaluator + ablation script complete and tested
- [x] 1.6 Graph quality evaluator complete and tested

### Phase 2 — Run Evaluations
- [ ] 2.1 Claim extraction JSON results exist for LIAR and ClaimBuster (`f1 > 0`)
- [ ] 2.2 120+ claim pairs annotated by human — **AI CANNOT DO THIS**
- [ ] 2.3 Mutation detection JSON results + 5 threshold sweep files exist
- [ ] 2.4 Verdict engine JSON results with ablation exist (non-zero macro_f1)
- [ ] 2.5 Graph quality JSON results exist
- [ ] 2.6 `corpus_stats.json` exists with `total_claims > 0`

### Phase 3 — Baseline Comparisons
- [ ] 3.1 ClaimBuster baseline script complete; results JSON exists
- [ ] 3.2 SBERT mutation baseline script complete; results JSON exists
- [ ] 3.3 Majority-class verdict baseline script complete; results JSON exists
- [ ] 3.4 `COMPARISON_TABLE.md` populated with real numbers from JSON files

### Phase 4 — Paper Writing
- [ ] 4.0 `paper/` directory scaffold created
- [ ] 4.1 Abstract written (150–200 words, no fabricated numbers)
- [ ] 4.2 Introduction written (500–700 words, 4 paragraphs, real example in P1)
- [ ] 4.3 Related Work written (600–900 words, all citations verified)
- [ ] 4.4 System Description written (900–1200 words, 5 subsections)
- [ ] 4.5 Evaluation Setup written (400–600 words, limitations included)
- [ ] 4.6 Results written (all numbers traced to JSON files)
- [ ] 4.7 Discussion written (400–500 words, 4 explicit limitations)
- [ ] 4.8 Conclusion written (150–200 words, no new claims)
- [ ] 4.9 `references.bib` complete (all citations verified, doi/url present)
- [ ] 4.10 `paper_draft.md` assembled with word count header

### Phase 5 — Polish and arXiv Prep
- [ ] 5.1 `consistency_check.md` written; all items pass
- [ ] 5.2 LaTeX tables generated (4 `.tex` files, numbers from JSON)
- [ ] 5.3 SVG figures generated (fig1, fig2, fig3)
- [ ] 5.4 `arxiv_metadata.json` created
- [ ] 5.5 `README.md` Paper section added (no other README changes)

### Phase 6 — Submission
- [ ] 6.1 Pre-submission checklist all green
- [ ] 6.2 arXiv submitted — **HUMAN TASK**
- [ ] 6.3 Venue submitted — **HUMAN TASK**

---

## ══════════════════════════════════════════
## SECTION 4 — QUICK REFERENCE CARD FOR AI AGENTS
## ══════════════════════════════════════════

```
MANDATORY FIRST STEPS (every session):
  1. Read this file top to bottom.
  2. Read HANDOFF.md.
  3. Read ARCHITECTURE.md.
  4. Find the first phase with unchecked [ ] tasks.
  5. State which single task you will work on.
  6. If ambiguous, ask the user before proceeding.

HARD STOPS (never do these):
  ✗ Modify backend/app/** unless the task explicitly names the file.
  ✗ Modify frontend/src/** at all.
  ✗ Run git push.
  ✗ Run git commit without user instruction.
  ✗ Fabricate evaluation numbers.
  ✗ Mark a task [x] before its done-condition is satisfied.
  ✗ Start Phase N+1 before Phase N is fully complete.
  ✗ Add packages to pyproject.toml or package.json.
  ✗ Cite a paper you cannot verify exists via web search.
  ✗ Annotate claim pairs (task 2.2 is a human task, always).
  ✗ Change signal weights in VerdictEngine during evaluation.

ALWAYS DO:
  ✓ Run pytest (must stay at 80 passed) before and after code changes.
  ✓ Use the exact file paths specified in each task.
  ✓ Write evaluation results to JSON — not stdout only.
  ✓ Document every sample-size reduction with reason.
  ✓ Ask the user when plan is silent on an implementation choice.
  ✓ Update Section 3 checklist after completing each task.
```

---

*Document version: 1.0*
*Created: 2026-09-17*
*Current phase: Phase 2 — Run Evaluations and Collect Numbers*
*Next action: Begin task 2.1 — run claim extraction eval*
