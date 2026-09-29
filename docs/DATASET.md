# GMEE Dataset & Ingestion Specifications

This document defines the database schemas, ingestion pipelines, entity relationships, and empirical volume statistics for the Global Misinformation Early-Warning Engine (GMEE).

---

## 1. High-Level Architecture & Stores

GMEE operates a polyglot persistence architecture separating relational storage, vector indexing, graph topology, and transient cache/coordination:

1. **PostgreSQL 16 + pgvector (`gmee`):**
   - Serves as the primary source of truth for all structured tabular data, users, raw ingested content, extracted claims, and audit logs.
   - Houses 768-dimensional normalized embeddings (`all-mpnet-base-v2`) on articles and claims.
   - Employs an HNSW (Hierarchical Navigable Small World) cosine index on `claims.embedding` (`claims_embedding_hnsw_cosine_idx`) and an IVFFlat index on `articles.embedding`.
2. **Neo4j 5.20+ Community / Enterprise:**
   - Propagation topology graph capturing `Article`, `Claim`, `Source`, `Entity`, and `Domain` nodes.
   - Traverses relationship edges (`SIMILAR_TO`, `EVOLVED_FROM`, `PUBLISHED_BY`, `MENTIONS`, `FROM_DOMAIN`, `DUPLICATE_OF`).
3. **Redis 7:**
   - Ingest deduplication bloom filters/sets, sliding-window rate limit counters, distributed leader election locks for the collection scheduler, and short-lived session caches.

---

## 2. Relational Schemas (PostgreSQL)

All relational models inherit from SQLAlchemy declarative base. The production PostgreSQL schema includes the following primary tables:

### `articles`
Represents ingested news and discussion articles from external feeds.
- `id` (UUID, Primary Key)
- `source_id` (UUID, Foreign Key referencing `sources.id`)
- `title` (VARCHAR, Non-null)
- `url` (VARCHAR, Non-null, Unique Index)
- `content` (TEXT, Raw ingested body text)
- `cleaned_content` (TEXT, Sanitized markup-free body text)
- `published_at` (TIMESTAMPTZ)
- `author` (VARCHAR)
- `raw_metadata` (JSONB, Collector metadata payload)
- `content_hash` (VARCHAR, SHA256 of lowercase `title + ":" + content`)
- `collected_at` (TIMESTAMPTZ, Timestamp of ingestion)
- `language` (VARCHAR, ISO code e.g. `en`)
- `processing_status` (ENUM: `pending`, `processed`, `skipped_non_english`, `skipped_duplicate`, `failed`)
- `canonical_article_id` (UUID, Foreign Key referencing `articles.id` for near-duplicates)
- `word_count` (INTEGER)
- `domain` (VARCHAR, Extracted publisher host, indexed)
- `processed_at` (TIMESTAMPTZ)
- `nlp_status` (ENUM: `pending`, `completed`, `skipped`, `failed`)
- `embedding` (`vector(768)`, Sentence-BERT vector of title + cleaned body)

### `claims`
Extracted atomic factual statements derived from processed articles.
- `id` (UUID, Primary Key)
- `article_id` (UUID, Foreign Key referencing `articles.id`, On Delete Cascade)
- `claim_text` (TEXT, Normalized atomic assertion)
- `confidence` (FLOAT, Extraction confidence score 0.0–1.0)
- `embedding` (`vector(768)`, HNSW cosine index `claims_embedding_hnsw_cosine_idx`)
### `claim_entities`
Named entities extracted from claims via spaCy NER for grounding verification.
- `id` (UUID, Primary Key)
- `claim_id` (UUID, Foreign Key referencing `claims.id`, On Delete Cascade, Indexed)
- `entity_text` (VARCHAR, The surface form of the named entity)
- `entity_type` (VARCHAR, e.g. `PERSON`, `ORG`, `GPE`, `DATE`, `MONEY`, `EVENT`)
- `start_char` (INTEGER, Span start in `claim_text`)
- `end_char` (INTEGER, Span end in `claim_text`)

### `claim_relationships`
Directed semantic relationships between claims.
- `id` (UUID, Primary Key)
- `from_claim_id` (UUID, Foreign Key referencing `claims.id`, On Delete Cascade, Indexed)
- `to_claim_id` (UUID, Foreign Key referencing `claims.id`, On Delete Cascade, Indexed)
- `relationship_type` (ENUM: `SIMILAR_TO`, `EVOLVED_FROM`)
- `score` (FLOAT, Cosine similarity or temporal mutation score)
- `created_at` (TIMESTAMPTZ)
- *Constraints:* `UniqueConstraint(from_claim_id, to_claim_id, relationship_type)` enforces one edge per directional pair and type.

### `claim_cluster_runs` & `claim_cluster_assignments`
Clustering runs executed by the Evolution Engine using HDBSCAN / community detection.
- `claim_cluster_runs`: `id` (UUID, PK), `run_at` (TIMESTAMPTZ), `algorithm_params` (JSONB), `claims_in_corpus` (INT)
- `claim_cluster_assignments`: `id` (UUID, PK), `claim_id` (UUID, FK `claims.id`), `cluster_run_id` (UUID, FK `claim_cluster_runs.id`), `cluster_id` (INT)

### `alerts`
Persistent early-warning signals detected across the network.
- `id` (UUID, Primary Key)
- `kind` (VARCHAR, e.g. `INGESTION_SPIKE`, `DISPUTED_SURGE`, `MUTATION_DETECTED`, `CLUSTER_BURST`)
- `severity` (VARCHAR, e.g. `CRITICAL`, `WARNING`, `INFO`)
- `subject_key` (VARCHAR, Deduplication hash/key per event subject)
- `title` (VARCHAR)
- `body` (TEXT)
- `payload` (JSONB)
- `claim_id` (UUID, Nullable FK `claims.id`)
- `acknowledged_at` (TIMESTAMPTZ, Nullable)
- `first_seen_at` (TIMESTAMPTZ)
- `last_seen_at` (TIMESTAMPTZ)

### `eval_pairs` & `eval_pair_labels`
Gold-standard evaluation dataset for retrieval and fact-checking baselines.
- `eval_pairs`: `id` (UUID, PK), `claim_a_id` (UUID, FK `claims.id`), `claim_b_id` (UUID, FK `claims.id`), `bucket` (VARCHAR: `b95`, `b85`, `b75`, `b60`, `b40`, `b00`), `sim_score` (FLOAT), `sampled_at` (TIMESTAMPTZ)
- `eval_pair_labels`: `id` (UUID, PK), `pair_id` (UUID, FK `eval_pairs.id`), `annotator` (VARCHAR), `label` (VARCHAR: `SAME_STORY`, `EVOLVED`, `DISTINCT`), `created_at` (TIMESTAMPTZ)

### `verdict_feedback`
Human-in-the-loop audit logs and crowd feedback.
- `id` (UUID, Primary Key)
- `claim_id` (UUID, FK `claims.id`, Indexed)
- `client_hash` (VARCHAR, Anonymized sha256 client fingerprint)
- `vote` (VARCHAR: `AGREE`, `DISAGREE`)
- `corrected_verdict` (VARCHAR, Nullable)
- `comment` (TEXT, Nullable)
- `created_at` (TIMESTAMPTZ)

- `extracted_at` (TIMESTAMPTZ)
- `verdict` (VARCHAR, One of `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNRESOLVED`, `WEAKLY_CORROBORATED`, `UNSUPPORTED`, `DISPUTED`)
- `verdict_probability` (FLOAT, Posterior probability $P(\text{supported} \mid \text{evidence})$)
- `verdict_rationale` (TEXT, Human-readable breakdown of contributing signals)
- `verdict_evidence` (JSONB, Neighbors inspected, stances, entity overlap)

---

## 3. Graph Schemas (Neo4j)

The Neo4j propagation graph maintains a typed property topology:

### Node Labels
- `Article`: `{id, title, url, domain, published_at, word_count}`
- `Claim`: `{id, claim_text, confidence, verdict, verdict_probability, extracted_at}`
- `Source` / `Domain`: `{id, name, domain, credibility_score}`
- `Entity`: `{id, text, type}`

### Edge Relationships
- `(:Claim)-[:PUBLISHED_BY]->(:Source)` (9,950 edges)
- `(:Article)-[:FROM_DOMAIN]->(:Domain)` (6,395 edges)
- `(:Article)-[:MENTIONS]->(:Entity)` / `(:Claim)-[:MENTIONS]->(:Entity)` (24,665 edges)
- `(:Claim)-[:SIMILAR_TO {score}]->(:Claim)` (37,630 edges)
- `(:Claim)-[:EVOLVED_FROM {score, lag_seconds}]->(:Claim)` (648 edges)
- `(:Article)-[:SIMILAR {score}]->(:Article)` (806 edges)
- `(:Article)-[:DUPLICATE_OF]->(:Article)` (13 edges)

---

## 4. Current Dataset Volume Statistics

Empirical counts from the production database instance:

| Entity / Table | Count | Description |
|---|---|---|
| **Sources** | 16 | Registered ingestion feeds (RSS, Reddit, NewsAPI) |
| **Articles** | 8,688 | Total articles ingested into PostgreSQL |
| **Articles Processed** | 8,626 | Preprocessed clean articles (62 skipped non-English) |
| **Articles Embedded** | 8,626 | Articles with 768-D embeddings in `articles.embedding` |
| **Claims** | 9,950 | Atomic extracted factual statements |
| **Claims Embedded** | 9,950 | 100% vector coverage in `claims.embedding` (HNSW indexed) |
| **Claim Entities** | 25,092 | Grounded named entities linked to claims |
| **Claim Relationships** | 38,335 | Persisted relational edges (37,666 `SIMILAR_TO`, 669 `EVOLVED_FROM`) |
| **Cluster Runs** | 85 | Historical HDBSCAN topic-evolution cycles executed |
| **Cluster Assignments**| 304,091 | Claim-to-cluster trajectory records across runs |
| **Neo4j Nodes** | 27,132 | Graph nodes across Article, Claim, Entity, and Source |
| **Neo4j Relationships**| 80,107 | Propagation, evolution, and attribution links |
| **Alerts Persisted** | 40 | Deduped early-warning records in `alerts` table |
| **Eval Pairs Sampled** | 761 | Stratified similarity pairs for gold-standard benchmarking |
| **Eval Labels Logged** | 13 | Human consensus gold labels collected via Eval Lab |
| **Verdict Feedback** | 4 | Human-in-the-loop verdict validations |

### Verdict Distribution Breakdown
- `UNSUPPORTED`: 6,034 claims (single-source assertions lacking corroborating coverage)
- `UNRESOLVED`: 3,461 claims (ambiguous or borderline evidence, $0.38 \le P < 0.55$)
- `PARTIALLY_SUPPORTED`: 34 claims ($0.55 \le P < 0.72$)
- `SUPPORTED`: 56 claims ($P \ge 0.72$)
- `WEAKLY_CORROBORATED`: 2 claims
- Unscored / Pending: 363 claims


---

## 5. Ingestion & Seeding Pipelines

GMEE data is populated and maintained through modular scripts in `backend/scripts/`:

```
Raw Content Feeds (RSS / Reddit / NewsAPI / CSV)
       │
       ▼  `backend/scripts/import_articles.py`
  [articles] (Postgres)
       │
       ▼  `backend/scripts/run_nlp_cycle.py` (NLP Orchestrator)
  [claims] + [claim_entities] + [claims.embedding]
       │
       ├────────────────────────────────────────┐
       ▼ `backend/scripts/embed_articles.py`     ▼ `backend/scripts/run_verdicts.py`
  [articles.embedding]                     [claims.verdict_*] (Bayesian 5-Signal Engine)
       │                                        │
       ▼ `backend/scripts/build_link_graph.py`   ▼ `backend/scripts/run_alerts.py`
  Neo4j Article/Claim Topology             [alerts] table (Ingestion & Disputed Surges)
       │                                        │
       └────────────────────────────────────────┴──► `backend/scripts/sample_eval_pairs.py`
                                                     `backend/scripts/run_eval.py`
```

### Pipeline Execution Guide

1. **Initial Source Seeding:**
   Sources are seeded automatically on backend boot via `app.services.seeder.seed_sources()` if `sources` is empty (defaulting to BBC News RSS, NewsAPI misinformation query, and Reddit r/science).

2. **Article Bulk Import (`scripts/import_articles.py`):**
   ```bash
   python scripts/import_articles.py /path/to/articles_export.csv
   ```
   - Ingests structured article feeds from exported CSV corpora.
   - Computes deterministic SHA256 `content_hash` matching the collector convention.
   - Idempotent upsert via `ON CONFLICT (url) DO NOTHING`.

3. **NLP Processing & Claim Extraction (`scripts/run_nlp_cycle.py`):**
   ```bash
   python scripts/run_nlp_cycle.py 50
   ```
   - Batches pending articles through language filtering and text cleanup.
   - Runs heuristic and LLM claim extraction (`Flan-T5` / Claude / OpenAI).
   - Generates 768-D sentence vectors via `sentence-transformers/all-mpnet-base-v2`.
   - Extracts named entity spans via spaCy `en_core_web_sm`.

4. **Article Vector Backfill (`scripts/embed_articles.py`):**
   ```bash
   python scripts/embed_articles.py
   ```
   - Embeds article `title + cleaned_content` into `articles.embedding`.
   - Creates/verifies vector indexes on `articles`.

5. **Link Graph Assembly (`scripts/build_link_graph.py`):**
   ```bash
   python scripts/build_link_graph.py
   ```
   - Computes cosine similarity matrix across article vectors.
   - Emits `SIMILAR` edges for top-K pairs exceeding threshold ($\ge 0.82$).
   - Creates `DUPLICATE_OF` edges on exact `content_hash` collisions.
   - Persists node and relationship topologies to Neo4j via Bolt driver.

6. **Verdict Scoring Cycle (`scripts/run_verdicts.py`):**
   ```bash
   python scripts/run_verdicts.py 500
   ```
   - Evaluates claims across the 5 verification signals (Corroboration, Contradiction, Outlet Prior, Entity Grounding, Linguistic Hedges).
   - Uses pgvector KNN with cross-domain filtering and FLAN-T5 NLI entailment checking.
   - Persists probabilistic scores and rationales to `claims.verdict_*`.

7. **Evaluation Benchmark Harness (`scripts/sample_eval_pairs.py` & `scripts/run_eval.py`):**
   ```bash
   python scripts/sample_eval_pairs.py 50 1500
   python scripts/run_eval.py
   ```
   - `sample_eval_pairs.py`: Samples stratified claim pairs across 6 similarity buckets (`b95` through `b00`).
   - Pairs are served blinded to human annotators via the **Eval Lab** dashboard.
   - `run_eval.py`: Computes AUROC with 95% bootstrap CI, best-F1, Brier score, ECE, and McNemar significance tests against TF-IDF and SBERT baselines, writing results to `eval_report.json`.

