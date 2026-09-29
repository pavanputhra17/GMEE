# GMEE Algorithmic & Hardware Limitations

This document provides a transparent and rigorous technical accounting of the architectural boundaries, algorithmic trade-offs, heuristic approximations, and hardware constraints inherent in the Global Misinformation Early-Warning Engine (GMEE).

---

## 1. Algorithmic Bounds & Heuristics

### 1.1 Vector Similarity & Threshold Window
- **Embedding Space:** GMEE relies on `sentence-transformers/all-mpnet-base-v2` producing dense 768-dimensional normalized vector embeddings.
- **Near-Neighbor Window (`VERDICT_NEAR_MIN=0.60`, `VERDICT_NEAR_MAX=0.97`):**
  - Cross-outlet reporting of identical real-world events rarely matches verbatim phrasing. Semantic similarity between legitimate independent articles typically occupies the `0.55–0.75` cosine band.
  - Setting a threshold above `0.80` causes catastrophic false-negative rates in corroboration discovery (collapsing over 90% of claims to `UNSUPPORTED`).
  - Conversely, an upper bound of `0.97` excludes exact duplicate syndications or scraping clones to prevent artificial corroboration inflation.
- **Topological Edge Truncation:**
  - Graph edge construction in Neo4j caps neighbors per article at `TOP_K=3` with a threshold cutoff ($\ge 0.82$) to keep relationship graph density manageable ($O(N \cdot K)$ rather than $O(N^2)$).

### 1.2 Natural Language Inference (NLI) Stance Verification
- **Model:** `google/flan-t5-base` wrapped as a sequence-to-sequence entailment classifier.
- **Prompt Formulation:** `"premise: <neighbor_text> hypothesis: <claim_text> Does the premise entail the hypothesis?"`
- **Output Classes:** Truncated beam generation checking for exact tokens `yes` (entailment), `no` (contradiction), or `neutral`.
- **Heuristic Caveats:**
  - `flan-t5-base` (~250M parameters) can miss subtle irony, satirical phrasing, hyperbole, or nuanced temporal conditionality ("The minister said X on Monday, but reversed it on Tuesday").
  - Token input truncation is enforced at 512 tokens (with hypothesis/premise strings clipped at 300 characters), which may lose qualifying subordinate clauses at the ends of long journalistic sentences.

### 1.3 Probabilistic Verdict Scoring Model
- **Non-Binary Truth Philosophy:** GMEE never issues absolute verdicts ("TRUE" or "FALSE"). It outputs a Bayesian posterior probability $P(\text{supported} \mid \text{evidence}) \in [0, 1]$.
- **Signal Weighting:**
  $$\text{Score} = 0.40 \cdot S_{\text{corrob}} + 0.20 \cdot S_{\text{contra}} + 0.15 \cdot S_{\text{track}} + 0.15 \cdot S_{\text{entity}} + 0.10 \cdot S_{\text{language}}$$
- **Disputed Override Rule:** `DISPUTED` is an explicit override, not a mere numerical probability band. It strictly requires an observed NLI contradiction *and* $P(\text{supported}) < 0.45$.
- **Cold-Start Bias in Source Priors:**
  - An outlet's prior starts at a neutral prior ($0.50$). While Bayesian Laplace smoothing prevents single articles from skewing an outlet to $0.0$ or $1.0$, outlets with sparse historical data will reflect this uninformative prior.

### 1.4 Evolution & Mutation Tracking
- **Graph Lineage Diffs:** Claim evolution is tracked through word-level Myers diffing and timestamp sequencing across `EVOLVED_FROM` relationships.
- **Assumed Temporal Lineage:** If two claims match above threshold and originate from different timestamps, the older claim is hypothesized as the parent. In breaking news, earlier reporting can often be less accurate than subsequent retractions, leading to inverted directionality in narrative authority.
- **Clustering Debounce & Scale:** HDBSCAN and topic-clustering jobs are debounced (`force=false`) to avoid thrashing on high-frequency streaming ingest. Minimum corpus size guards require sufficient claim density before triggering cluster re-partitioning.

---

## 2. Hardware Boundaries & Resource Footprint

### 2.1 CPU vs. GPU Inference
- **Embedding Generation (`all-mpnet-base-v2`):**
  - Requires ~420MB RAM for model weights.
  - On a modern multi-core CPU (AVX2), embedding throughput averages 30–50 claims/sec.
  - On an NVIDIA GPU (CUDA), throughput reaches 400–600 claims/sec.
- **NLI Stance Scoring (`flan-t5-base`):**
  - Model weights occupy ~990MB memory.
  - Autoregressive text generation without batched GPU inference takes ~80–120ms per pair on CPU. Batching and in-memory stance caching (`STANCE_CACHE`) are used to protect live request latency.
- **NER Extraction (`spaCy en_core_web_sm`):**
  - Lightweight CPU pipeline (~15MB RAM), parsing claims in sub-millisecond durations.

### 2.2 Storage & Index Scaling (PostgreSQL / pgvector / Neo4j)
- **HNSW Index Parameters:**
  - `claims_embedding_hnsw_cosine_idx` uses standard HNSW graph construction (`m=16`, `ef_construction=64`).
  - While lookup latency is typically 5–15ms for $K=10$, building and updating HNSW graphs under heavy concurrent write loads consumes significant CPU and RAM.
- **Memory Consumption:**
  - PostgreSQL 16: Minimum 2GB RAM recommended for active working buffers and pgvector maintenance.
  - Neo4j 5: Heap and pagecache recommended minimum 2GB RAM for graphs up to $100\text{k}$ nodes and $500\text{k}$ edges.
  - Redis 7: Operational memory footprint stays under 50MB for session caches and rate limiters.
- **Total Local Deployment Minimums:**
  - **RAM:** 8GB minimum, 16GB recommended (to comfortably host PostgreSQL, Neo4j, Redis, and PyTorch models simultaneously).
  - **Disk:** 20GB SSD storage for database volumes and PyTorch Hugging Face cache.

---

## 3. Epistemic & Operating Constraints

1. **Language Scope:** Current production pipeline models (`all-mpnet-base-v2`, `flan-t5-base`, `en_core_web_sm`) are optimized for English-language text. Ingested non-English documents are filtered out during preprocessing (`skipped_non_english`).
2. **Corroboration vs. Truth:** A falsehood amplified identically by ten syndicated outlets will register high corroboration scores ($S_{\text{corrob}}$). The engine mitigates this via domain-level deduplication and historical outlet track records, but coordinated multi-outlet disinformation campaigns remain an adversarial threat vector.
3. **Evaluation Sample Size:** The gold-standard evaluation harness (`eval_report.json`) computes rigorous statistical metrics (AUROC bootstrap CIs, McNemar tests, ECE), but requires $\ge 100$ human consensus labels before results reach full statistical significance.

